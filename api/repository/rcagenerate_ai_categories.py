import json
from collections import defaultdict, Counter
import requests
import random
import time
import re
import pandas as pd
import sys
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Dict, Tuple

# ---------------------------- Color Codes for Terminal Output ----------------------------

RED = '\033[91m'
GREEN = '\033[92m'
BLUE = '\033[94m'
YELLOW = '\033[93m'
RESET = '\033[0m'

# ---------------------------- Path Management ----------------------------
# Move up 3 levels to reach `/xyz/resources`
resources_dir = Path(__file__).resolve().parents[2] / "resources"
sys.path.append(str(resources_dir))

# ---------------------------- Import Internal Modules ----------------------------
from utility import load_config, connectDB_alchemy, closeDB, getES, getEmbed

# Initialize Elasticsearch and Embedding Model
env = load_config()
es = getES()

labels = {}

# LLaMA API request template
LLAMA_REQUEST_BODY_TEMPLATE = {
    "input": {
        "prompt": ""
    }
}

class GenerateAICategoriesRequest(BaseModel):
    """
    Request model for generating topic labels for complaints.
    """
    startdate: str = Field(..., description="Start date for filtering complaints.")
    enddate: str = Field(..., description="End date for filtering complaints.")
    ministry: str = Field(default="DOCAF", description="Ministry for which the topics are being generated.") 
    rcadata: dict = Field(..., description="Tree structure of complaint categories.")


def call_llama_api(prompt: str) -> str:
    """Call LLaMA API with improved error handling and debugging"""
    request_body = dict(LLAMA_REQUEST_BODY_TEMPLATE)
    request_body["input"]["prompt"] = prompt

    try:
        response = requests.post(
            env["LLAMA_API_SERVER_URL"],
            headers={"Content-Type": "application/json"},
            json=request_body,
            timeout=60  # Increased timeout for larger requests
        )
        response.raise_for_status()
        result = response.json()
        api_output = result.get("output", "").strip()
        
        # Debug: Print first few characters of response
        print(f"{BLUE}API Response Preview: {api_output[:100]}...{RESET}")
        
        return api_output
    
    except requests.RequestException as e:
        print(f"{YELLOW}API Error: {e}{RESET}")
        return "ERROR_LABEL"


def preprocess_complaints(complaints: List[str]) -> List[str]:
    """Clean and preprocess complaint text"""
    processed = []
    for complaint in complaints:
        if not complaint or len(complaint.strip()) < 10:
            continue
        
        # Basic cleaning
        clean_text = re.sub(r'[^\w\s\-\.,]', ' ', complaint)
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        
        # Remove very long complaints (likely duplicates or malformed)
        if len(clean_text) > 500:
            clean_text = clean_text[:500] + "..."
        
        processed.append(clean_text)
    
    return processed


def extract_keywords(complaints: List[str], top_k: int = 10) -> List[str]:
    """Extract most common keywords from complaints"""
    word_freq = Counter()
    stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'been', 'be', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can', 'cant', 'wont', 'dont', 'doesnt', 'didnt', 'havent', 'hasnt', 'hadnt', 'isnt', 'arent', 'wasnt', 'werent'}
    
    for complaint in complaints:
        words = re.findall(r'\b[a-zA-Z]{3,}\b', complaint.lower())
        for word in words:
            if word not in stop_words:
                word_freq[word] += 1
    
    return [word for word, _ in word_freq.most_common(top_k)]


def create_improved_prompt(complaints: List[str], node: str, is_leaf: bool = True, child_summaries: List[str] = None) -> str:
    """Create an improved prompt for label generation"""
    
    if is_leaf:
        # For leaf nodes, analyze actual complaints
        keywords = extract_keywords(complaints, top_k=10)
        
        # Show more complaints but limit individual length
        display_complaints = []
        for i, complaint in enumerate(complaints[:10]):  # Show up to 10 complaints
            if len(complaint) > 120:
                display_complaints.append(f"{i+1}. {complaint[:120]}...")
            else:
                display_complaints.append(f"{i+1}. {complaint}")
        
        prompt = f"""Analyze these {len(complaints)} customer complaints and create a specific category label.

SAMPLE COMPLAINTS:
{chr(10).join(display_complaints)}

FREQUENT KEYWORDS: {', '.join(keywords)}

Create a focused category label that captures the main complaint theme. Avoid generic terms.

STRICT OUTPUT FORMAT (exactly as shown):
Title: [specific category name in 2-4 words]
Description: [clear explanation of what this category covers in 15-25 words]

EXAMPLE:
Title: Passport Renewal Delays
Description: Complaints about slow processing times and delays in passport renewal applications and document verification services.

YOUR RESPONSE:"""

    else:
        # For internal nodes, synthesize from child categories
        child_info = "\n".join([f"• {summary}" for summary in child_summaries[:5]])  # Limit child summaries
        
        prompt = f"""Create a parent category from these child categories:

CHILD CATEGORIES:
{child_info}

Find the common theme and create a broader parent category.

STRICT OUTPUT FORMAT (exactly as shown):
Title: [parent category name in 2-4 words]
Description: [broader category description covering all children in 15-25 words]

YOUR RESPONSE:"""

    return prompt


def smart_sampling(complaints: List[str], max_samples: int = None) -> List[str]:
    """Sample complaints intelligently when needed"""
    if max_samples is None or len(complaints) <= max_samples:
        return complaints
    
    # If we need to sample, use stratified sampling
    short = [c for c in complaints if len(c) < 50]
    medium = [c for c in complaints if 50 <= len(c) < 150]
    long = [c for c in complaints if len(c) >= 150]
    
    # Proportional sampling
    total = len(complaints)
    short_ratio = len(short) / total if total > 0 else 0
    medium_ratio = len(medium) / total if total > 0 else 0
    long_ratio = len(long) / total if total > 0 else 0
    
    short_samples = min(len(short), max(1, int(max_samples * short_ratio)))
    medium_samples = min(len(medium), max(1, int(max_samples * medium_ratio)))
    long_samples = min(len(long), max_samples - short_samples - medium_samples)
    
    sampled = (random.sample(short, short_samples) if short else []) + \
              (random.sample(medium, medium_samples) if medium else []) + \
              (random.sample(long, long_samples) if long_samples > 0 and long else [])
    
    return sampled


def generate_label_with_retry(complaints: List[str], node: str, is_leaf: bool = True, child_summaries: List[str] = None) -> str:
    """Generate label with improved retry mechanism and progressive sampling"""
    max_attempts = 3
    
    for attempt in range(max_attempts):
        try:
            if is_leaf:
                # Progressive sampling - start with reasonable amounts, then reduce
                if attempt == 0:
                    # First attempt: reasonable sample
                    if len(complaints) >= 2000:
                        sample_complaints = smart_sampling(complaints, max_samples=200)
                    elif len(complaints) > 100:
                        sample_complaints = smart_sampling(complaints, max_samples=100)
                    else:
                        sample_complaints = complaints
                elif attempt == 1:
                    # Second attempt: smaller sample
                    sample_complaints = smart_sampling(complaints, max_samples=100)
                else:
                    # Third attempt: very small sample
                    sample_complaints = smart_sampling(complaints, max_samples=50)
                
                processed_complaints = preprocess_complaints(sample_complaints)
                
                if not processed_complaints:
                    print(f"{YELLOW}No valid complaints for node {node}{RESET}")
                    return "Title: Empty Category\nDescription: No complaints found in this category"
                
                print(f"{BLUE}Node {node} (attempt {attempt + 1}): Processing {len(processed_complaints)} complaints{RESET}")
                prompt = create_improved_prompt(processed_complaints, node, is_leaf=True)
            else:
                # For internal nodes
                prompt = create_improved_prompt([], node, is_leaf=False, child_summaries=child_summaries)
                print(f"{BLUE}Node {node} (attempt {attempt + 1}): Synthesizing from {len(child_summaries)} child categories{RESET}")
            
            label = call_llama_api(prompt)
            
            # Better validation of response
            if ("ERROR_LABEL" not in label and 
                len(label.strip()) > 20 and 
                "Title:" in label and 
                "Description:" in label):
                print(f"{GREEN}✓ Successfully labeled node {node}{RESET}")
                return label
            
            print(f"{YELLOW}Retry {attempt+1}/3 for node {node} - inadequate response{RESET}")
            if attempt < max_attempts - 1:
                time.sleep(2)  # Pause between retries
            
        except Exception as e:
            print(f"{YELLOW}Attempt {attempt+1} failed for node {node}: {e}{RESET}")
            if attempt < max_attempts - 1:
                time.sleep(2)
            continue
    
    print(f"{RED}✗ All attempts failed for node {node}{RESET}")
    return f"Title: Category {node}\nDescription: Failed to generate proper label after multiple attempts for this complaint category."


# Recursively generate labels (post-order traversal)
def generate_label_for_node(node):
    """Generate labels using post-order traversal with improved logic"""
    if node not in tree:
        # Leaf node - process actual complaints
        doc_ids = doc_ids_mapping.get(node, [])
        
        if not doc_ids:
            labels[node] = "Title: Empty Category\nDescription: No complaints found in this category"
            return labels[node]

        total_entries = len(doc_ids)
        print(f"{BLUE}Processing leaf node {node} with {total_entries} documents{RESET}")
        
        # Smart sampling for Elasticsearch retrieval
        if total_entries >= 2000:
            selected_ids = random.sample(doc_ids, 200)
        elif total_entries > 100:
            selected_ids = random.sample(doc_ids, 100)
        else:
            selected_ids = doc_ids

        # Fetch complaints for the selected document IDs
        try:
            response = es.mget(
                index=env["ES"]["INDEX_NAME"],
                body={"ids": [selected_id.replace('/', '_') for selected_id in selected_ids]},
            )
            
            # Extract 'complaintDetails' attribute from found documents
            complaints = [
                doc["_source"]["complaintDetails"]
                for doc in response["docs"]
                if doc.get("found") and "complaintDetails" in doc["_source"]
            ]
            
            if not complaints:
                labels[node] = "Title: Invalid Data\nDescription: No valid complaint data available"
                return labels[node]
            
            label = generate_label_with_retry(complaints, node, is_leaf=True)
            labels[node] = label
            return label
            
        except Exception as e:
            print(f"{RED}Error fetching data for node {node}: {e}{RESET}")
            labels[node] = f"Title: Data Error\nDescription: Error retrieving complaint data for this category"
            return labels[node]
    
    # Internal node - generate labels for children first, then synthesize
    child_labels = []
    child_summaries = []
    
    for child in tree[node]:
        child_label = generate_label_for_node(child)
        child_labels.append(child_label)
        
        # Extract description for synthesis
        if isinstance(child_label, str) and "Description:" in child_label:
            desc_match = re.search(r"Description:\s*(.*)", child_label, re.DOTALL)
            if desc_match:
                child_summaries.append(desc_match.group(1).strip())
        else:
            child_summaries.append(str(child_label))
    
    # Generate parent label
    label = generate_label_with_retry([], node, is_leaf=False, child_summaries=child_summaries)
    labels[node] = label
    return label


def clean_string(text):
    """Clean text of unwanted characters"""
    if not isinstance(text, str):
        return str(text)
    
    cleaned = text.replace("*", "").replace("\n", " ").replace("\r", " ")
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned.strip()


def make_markdown(text) -> Dict[str, str]:
    """Convert API response to structured format with robust parsing"""
    if isinstance(text, dict):
        return text
    
    if not isinstance(text, str):
        return {
            "Title": "Invalid Response",
            "Description": "API returned non-string response"
        }
    
    # Clean the text first
    text = text.strip()
    
    # Try standard format parsing
    title_match = re.search(r"Title:\s*([^\n\r]+)", text, re.IGNORECASE)
    desc_match = re.search(r"Description:\s*([^\n\r]+(?:\n[^\n\r]+)*)", text, re.IGNORECASE)
    
    if title_match and desc_match:
        title = title_match.group(1).strip()
        description = desc_match.group(1).strip()
        
        # Clean extracted text
        title = re.sub(r'[^\w\s\-&]', '', title).strip()
        description = re.sub(r'\s+', ' ', description).strip()
        
        return {
            "Title": title[:60] if title else "Untitled Category",
            "Description": description[:150] if description else "No description available"
        }
    
    # Try alternative parsing
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    if len(lines) >= 2:
        potential_title = lines[0]
        potential_desc = ' '.join(lines[1:])
        
        # Clean up prefixes
        potential_title = re.sub(r'^(Title:|title:)\s*', '', potential_title, flags=re.IGNORECASE)
        potential_desc = re.sub(r'^(Description:|description:)\s*', '', potential_desc, flags=re.IGNORECASE)
        
        if len(potential_title) > 0 and len(potential_desc) > 0:
            return {
                "Title": potential_title[:60],
                "Description": potential_desc[:150]
            }
    
    # Fallback
    print(f"{YELLOW}Failed to parse response: {text[:100]}...{RESET}")
    return {
        "Title": "Parsing Failed",
        "Description": "Could not extract title and description from API response"
    }


# def generate_ai_categories(request: GenerateAICategoriesRequest):
#     """
#     Generate AIRCA topic labels for complaints based on the provided request.
    
#     Args:
#         request (GenerateAICategoriesRequest): The request containing start date, end date, ministry, and tree structure.
    
#     Returns:
#         dict: A dictionary containing the generated topic labels.
#     """
#     try:
#         # Extract parameters from the request
#         start_date = request.startdate
#         end_date = request.enddate
#         ministry = request.ministry
#         rcadata = request.rcadata

#         # Build the tree from rcadata
#         global tree, doc_ids_mapping, data
#         words = rcadata["words"]
#         count = rcadata["count"]
#         doc_ids_mapping = rcadata["doc_ids"]
#         print(f"{BLUE}Starting AIRCA topic generation...{RESET}")
        
#         # Build the tree
#         tree = defaultdict(list)
#         for node in words:
#             if '.' in node:
#                 parent = '.'.join(node.split('.')[:-1])
#                 tree[parent].append(node)

#         initial_time = time.time()
#         print(f"{BLUE}Tree structure loaded with {len(tree)} nodes{RESET}")
        
#         # Start label generation
#         generate_label_for_node("0")

#         # Clean and format the labels
#         formatted_labels = {}
#         for node, text in labels.items():
#             processed_label = make_markdown(text)
#             formatted_labels[node] = {
#                 "Title": clean_string(processed_label.get("Title", "")),
#                 "Description": clean_string(processed_label.get("Description", ""))
#             }

#         print(f"{BLUE}Label generation completed in {time.time() - initial_time:.2f} seconds{RESET}")
#         print(f"{GREEN}Total labels generated: {len(formatted_labels)}{RESET}")
        
#         # Print statistics
#         successful_labels = sum(1 for label in formatted_labels.values() 
#                               if label.get('Title', '') not in ['Parsing Failed', 'Invalid Response', 'Empty Category'])
#         print(f"{GREEN}Successfully labeled: {successful_labels}/{len(formatted_labels)} nodes{RESET}")

#         rcadata["labels"] = formatted_labels

#         result = {}
#         result["start_date"] = start_date
#         result["end_date"] = end_date
#         result["ministry"] = ministry
#         result["rcadata"] = rcadata
#         # result["rcadata"] = rcadata.encode().decode('unicode_escape')
#         df = pd.DataFrame([result])

#         con = connectDB_alchemy()
#         df.to_sql("rcaaicategories", con, if_exists="append", index=False)
#         # closeDB(con)

#         print(f"{GREEN}Labels saved to database successfully.{RESET}")

#         return {"result": result}

#     except Exception as e:
#         print(f"{RED}Error during AIRCA topic generation: {e}{RESET}")
        
#         # Try to save partial results
#         try:
#             if 'labels' in globals() and labels:
#                 partial_labels = {}
#                 for node, text in labels.items():
#                     partial_labels[node] = make_markdown(text)
                
#                 print(f"{BLUE}Saving partial results with {len(partial_labels)} labels{RESET}")
                
#                 # Still try to save to database with partial results
#                 if 'rcadata' in locals():
#                     rcadata["labels"] = partial_labels
#                     result = {
#                         "start_date": start_date if 'start_date' in locals() else "",
#                         "end_date": end_date if 'end_date' in locals() else "",
#                         "ministry": ministry if 'ministry' in locals() else "",
#                         "rcadata": json.dumps(rcadata)
#                     }
                    
#                     df = pd.DataFrame([result])
#                     con = connectDB_alchemy()
#                     df.to_sql("rcaaicategories", con, if_exists="append", index=False)
#                     print(f"{BLUE}Partial results saved to database{RESET}")
                    
#         except Exception as e2:
#             print(f"{RED}Failed to save partial results: {e2}{RESET}")
        
#         return {"error": str(e)}


def generate_ai_categories(request: GenerateAICategoriesRequest):
    """
    Generate AIRCA topic labels for complaints based on the provided request.
    
    Args:
        request (GenerateAICategoriesRequest): The request containing start date, end date, ministry, and tree structure.
    
    Returns:
        dict: A dictionary containing the generated topic labels.
    """
    try:
        # Extract parameters from the request
        start_date = request.startdate
        end_date = request.enddate
        ministry = request.ministry
        rcadata = request.rcadata

        # Validate rcadata structure to prevent hardcoded data generation
        if not isinstance(rcadata, dict):
            raise ValueError("rcadata must be a dictionary")
        
        required_keys = ["words", "count", "doc_ids"]
        missing_keys = [key for key in required_keys if key not in rcadata]
        if missing_keys:
            raise ValueError(f"rcadata missing required keys: {missing_keys}")
        
        # Validate that rcadata is not empty or contains only default/hardcoded values
        if not rcadata.get("words") or not rcadata.get("count"):
            raise ValueError("rcadata contains empty or invalid data")
        
        # Check if rcadata appears to be hardcoded/static data
        words_data = rcadata.get("words", {})
        if isinstance(words_data, dict) and "0" in words_data:
            # Additional validation to ensure this is dynamic data, not hardcoded
            if len(words_data) == 1 and words_data.get("0") == "root":
                raise ValueError("rcadata appears to contain only root node - insufficient data")

        # Build the tree from rcadata
        global tree, doc_ids_mapping, data
        words = rcadata["words"]
        count = rcadata["count"]
        doc_ids_mapping = rcadata["doc_ids"]
        
        print(f"{BLUE}Starting AIRCA topic generation...{RESET}")
        
        # Validate tree structure
        if not isinstance(words, dict) or not isinstance(count, dict):
            raise ValueError("Invalid structure: words and count must be dictionaries")
        
        # Build the tree
        tree = defaultdict(list)
        for node in words:
            if '.' in node:
                parent = '.'.join(node.split('.')[:-1])
                tree[parent].append(node)

        initial_time = time.time()
        print(f"{BLUE}Tree structure loaded with {len(tree)} nodes{RESET}")
        
        # Validate tree has sufficient nodes for processing
        if len(tree) < 2:  # Should have at least root and some children
            raise ValueError("Insufficient tree structure for label generation")
        
        # Start label generation
        generate_label_for_node("0")

        # Clean and format the labels
        formatted_labels = {}
        for node, text in labels.items():
            processed_label = make_markdown(text)
            formatted_labels[node] = {
                "Title": clean_string(processed_label.get("Title", "")),
                "Description": clean_string(processed_label.get("Description", ""))
            }

        print(f"{BLUE}Label generation completed in {time.time() - initial_time:.2f} seconds{RESET}")
        print(f"{GREEN}Total labels generated: {len(formatted_labels)}{RESET}")
        
        # Print statistics
        successful_labels = sum(1 for label in formatted_labels.values() 
                              if label.get('Title', '') not in ['Parsing Failed', 'Invalid Response', 'Empty Category'])
        print(f"{GREEN}Successfully labeled: {successful_labels}/{len(formatted_labels)} nodes{RESET}")

        # Create a copy of rcadata to avoid modifying the original
        result_rcadata = rcadata.copy()
        result_rcadata["labels"] = formatted_labels

        result = {
            "start_date": start_date,
            "end_date": end_date,
            "ministry": ministry,
            "rcadata": result_rcadata  # Use the copy instead of modifying original
        }
        
        # Save to database
        df = pd.DataFrame([result])
        con = connectDB_alchemy()
        
        # Convert rcadata to JSON string for database storage if needed
        df_for_db = df.copy()
        df_for_db['rcadata'] = df_for_db['rcadata'].apply(lambda x: json.dumps(x) if isinstance(x, dict) else x)
        
        df_for_db.to_sql("rcaaicategories", con, if_exists="append", index=False)
        
        print(f"{GREEN}Labels saved to database successfully.{RESET}")

        return {"result": result}

    except ValueError as ve:
        print(f"{RED}Validation Error: {ve}{RESET}")
        return {"error": f"Validation failed: {str(ve)}"}
    
    except Exception as e:
        print(f"{RED}Error during AIRCA topic generation: {e}{RESET}")
        
        # Try to save partial results only if we have valid initial data
        try:
            if 'labels' in globals() and labels and 'rcadata' in locals():
                partial_labels = {}
                for node, text in labels.items():
                    try:
                        partial_labels[node] = make_markdown(text)
                    except Exception as markdown_error:
                        print(f"{RED}Error processing label for node {node}: {markdown_error}{RESET}")
                        partial_labels[node] = {"Title": "Processing Failed", "Description": str(text)}
                
                print(f"{BLUE}Saving partial results with {len(partial_labels)} labels{RESET}")
                
                # Create partial result
                partial_rcadata = rcadata.copy()
                partial_rcadata["labels"] = partial_labels
                
                result = {
                    "start_date": start_date if 'start_date' in locals() else "",
                    "end_date": end_date if 'end_date' in locals() else "",
                    "ministry": ministry if 'ministry' in locals() else "",
                    "rcadata": json.dumps(partial_rcadata),
                    "status": "partial_success",
                    "error": str(e)
                }
                
                df = pd.DataFrame([result])
                con = connectDB_alchemy()
                df.to_sql("rcaaicategories", con, if_exists="append", index=False)
                print(f"{BLUE}Partial results saved to database{RESET}")
                
                return {"result": result, "warning": "Partial results saved due to error"}
                    
        except Exception as e2:
            print(f"{RED}Failed to save partial results: {e2}{RESET}")
        
        return {"error": str(e)}


# Additional helper function to validate rcadata structure
def validate_rcadata_structure(rcadata):
    """
    Validate that rcadata has the proper structure and is not hardcoded data.
    
    Args:
        rcadata (dict): The rcadata dictionary to validate
        
    Returns:
        tuple: (is_valid, error_message)
    """
    if not isinstance(rcadata, dict):
        return False, "rcadata must be a dictionary"
    
    required_keys = ["words", "count", "doc_ids"]
    for key in required_keys:
        if key not in rcadata:
            return False, f"Missing required key: {key}"
    
    words = rcadata.get("words", {})
    count = rcadata.get("count", {})
    doc_ids = rcadata.get("doc_ids", {})
    
    # Check if data structures are valid
    if not isinstance(words, dict) or not isinstance(count, dict):
        return False, "words and count must be dictionaries"
    
    # Check for empty data
    if not words or not count:
        return False, "words and count cannot be empty"
    
    # Check if word keys match count keys
    if set(words.keys()) != set(count.keys()):
        return False, "words and count must have matching keys"
    
    # Check for suspicious hardcoded patterns
    if len(words) == 1 and "0" in words and words["0"] == "root":
        return False, "Data appears to be minimal/hardcoded"
    
    # Validate hierarchical structure
    root_nodes = [key for key in words.keys() if '.' not in key]
    if len(root_nodes) != 1:
        return False, "Must have exactly one root node"
    
    # Check for reasonable data distribution
    total_count = sum(count.values())
    if total_count < 10:  # Minimum threshold for meaningful analysis
        return False, "Insufficient data volume for analysis"
    
    return True, "Valid rcadata structure"


# Example usage with validation
def safe_generate_ai_categories(request: GenerateAICategoriesRequest):
    """
    Wrapper function that validates rcadata before processing.
    """
    try:
        # Pre-validate rcadata
        is_valid, error_msg = validate_rcadata_structure(request.rcadata)
        if not is_valid:
            return {"error": f"Invalid rcadata: {error_msg}"}
        
        # Proceed with generation if validation passes
        return generate_ai_categories(request)
        
    except Exception as e:
        return {"error": f"Validation failed: {str(e)}"}
