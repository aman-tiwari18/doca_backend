# ---------------------------- Required Libraries ----------------------------
from fastapi import APIRouter, Request, Depends
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from sqlalchemy.orm import Session
from typing import Annotated
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
import pandas as pd
import json
import sys
from pathlib import Path
import requests
import time
from pydantic import BaseModel, Field
from typing import List, Dict, Tuple
from repository import database
from router.authentication import get_current_user
import anthropic
from openai import OpenAI

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")



# ---------------------------- Custom Modules ----------------------------
from repository.semantic_search import semanticSearch
from repository.keyword_search import keywordSearch
from repository.categoryAlert import categoryWiseAlerts


# ---------------------------- Path Management ----------------------------
# Move up 3 levels to reach `/xyz/resources`
resources_dir = Path(__file__).resolve().parents[2] / "resources"
sys.path.append(str(resources_dir))

# ---------------------------- Import Internal Modules ----------------------------
from utility import load_config, getES, getEmbed

# ---------------------------- Initialize Services ----------------------------
config = load_config()
ES = getES()
EMBED = getEmbed()

# oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

router = APIRouter(
    tags=['Analysis of Grievance Categories']
)


CATEGORIES_WITH_PROMPT_PATH = resources_dir / Path(config["CATEGORIES_WITH_PROMPT_PATH"]).name

with open(CATEGORIES_WITH_PROMPT_PATH, 'r') as f:
    categories_with_prompt = json.load(f)

categories_with_prompt = categories_with_prompt["ConsumerGrievanceCategories"]


@router.get("/get_all_categories")
async def all_static_categories(token : Annotated[str, Depends(oauth2_scheme)], db: Session = Depends(database.get_db)):
    # with open(resources_dir / "priority_count.json", "r") as f:
    #     critical_categories = json.load(f)

    # return critical_categories

    user = await get_current_user(token, db)
    user = user.username.lower()
    return categories_with_prompt


# LLaMA API request template (Deprecated)
# LLAMA_REQUEST_BODY_TEMPLATE = {
#     "input": {
#         "prompt": ""
#     }
# }

def call_gpt_api(prompt: str) -> str:
    """Call OpenAI GPT API"""

    api_key = config.get("OPENAI_API_KEY", "")
    if not api_key:
        print("Error: OPENAI_API_KEY not found in config")
        return "ERROR_LABEL"

    client = OpenAI(api_key=api_key)

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "user", "content": prompt}
            ],
            max_tokens=4096,
            temperature=0.2  # lower = more deterministic JSON
        )

        return response.choices[0].message.content

    except Exception as e:
        print(f"Error calling GPT API: {e}")
        return "ERROR_LABEL"

class GenerateAISubCategoriesRequest(BaseModel):
    """
    Request model for generating topic labels for complaints.
    """
    input_prompt: str = Field(..., description="input text containing subcategories and examples")
    max_retries: int = Field(3, description="Maximum number of retry attempts to get valid JSON from Claude")


def clean_json_response(response: str) -> str:
    """Clean and extract JSON from the response"""
    response = response.strip()
    
    # Remove markdown code blocks if present
    if response.startswith('```json'):
        response = response[7:]  # Remove ```json
    if response.startswith('```'):
        response = response[3:]   # Remove ```
    if response.endswith('```'):
        response = response[:-3]  # Remove closing ```
        
    # Find JSON object boundaries
    start_idx = response.find('{')
    end_idx = response.rfind('}')
    
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        response = response[start_idx:end_idx + 1]
    
    return response.strip()


@router.post("/get_ai_subcategory_gpt")
async def get_subcategories_json_from_gpt(
    token : Annotated[str, Depends(oauth2_scheme)],
   GenerateAISubCategoriesRequest: GenerateAISubCategoriesRequest,
    db: Session = Depends(database.get_db)
) -> dict:
    """
    Sends a prompt to Anthropic Claude to extract subcategories and
    generate specific search prompts for them, retrying on invalid JSON or errors.

    Args:
        input_prompt (str): The main prompt text containing subcategories and examples.
        max_retries (int): The maximum number of times to retry the API call.

    Returns:
        dict: A dictionary representing the JSON output as specified, or an empty dict
              if a valid JSON response cannot be obtained after all retries.
    """

    user = await get_current_user(token, db)
    user = user.username.lower()

    llm_prompt_template = f"""You are an expert text analyst and a prompt engineering assistant. Your task is to analyze the provided 'Input Text' and identify all distinct critical subcategories, along with their associated keywords and examples. For each identified subcategory, you must then formulate a *concise and effective search prompt* that specifically targets grievances related to that subcategory, incorporating its keywords and examples.

The output must be a valid JSON object. The keys of this JSON object should be the names of the identified subcategories. The value for each subcategory key should be an object containing a single key: 'prompt', whose value is the newly generated search prompt for that subcategory.

**Input Text:**
\"\"\"
{GenerateAISubCategoriesRequest.input_prompt}
\"\"\"

**Instructions:**
1.  Read the "Input Text" carefully to understand the main topic and its detailed breakdown.
2.  Identify all distinct subcategories mentioned.
3.  For each subcategory, gather all associated keywords, specific examples, and relevant phrases. Include terms in all languages if present.
4.  Formulate a dedicated, concise search prompt for each subcategory. This prompt should aim to accurately capture grievances specific to that subcategory using its defining terms.
5.  If there are general or overarching keywords that don't fit a specific subcategory but are broadly relevant (e.g., 'fire', 'smoke', 'damage'), you can include them in an 'Overall_Contextual_Terms' subcategory or similar if it makes sense to generate a prompt for it.
6.  Ensure the output is a valid JSON object as specified below.

**Output JSON Format Example:**
```json
{{
  "property fires": {{
    "prompt": "Find grievances related to property fires, including incidents at houses, shops, factories, buildings, apartments, slums, markets, hospitals, schools, offices, hotels, malls, colonies, temples, mosques, or church fires."
  }},
  "vehicle fires": {{
    "prompt": "Search for grievances concerning vehicle fires, specifically car, bus, truck, or school bus fires."
  }}
}}
"""
    
    for attempt in range(GenerateAISubCategoriesRequest.max_retries):
        print(f"Attempt {attempt + 1}/{GenerateAISubCategoriesRequest.max_retries} to get JSON from Claude...")
        try:
            generated_content = call_gpt_api(
                prompt=llm_prompt_template
            )

            # Try to parse the generated content as JSON
            try:
                generated_content = clean_json_response(generated_content)
                final_json_output = json.loads(generated_content)
                print("Successfully received and parsed JSON.")
                return final_json_output # Success! Return the JSON
            except json.JSONDecodeError as e:
                print(f"Warning: Ollama did not return valid JSON on attempt {attempt + 1}. Error: {e}")
                # print(f"Raw Ollama response that failed parsing: {generated_content}")
                # Fallback: Attempt to extract JSON from a markdown block if present
                if generated_content.startswith('```json') and generated_content.endswith('```'):
                    json_string = generated_content[len('```json'):-len('```')].strip()
                    try:
                        final_json_output = json.loads(json_string)
                        print(f"Successfully extracted and parsed JSON from markdown block on attempt {attempt + 1}.")
                        return final_json_output # Success from fallback
                    except json.JSONDecodeError as inner_e:
                        print(f"Error parsing extracted JSON string from markdown block: {inner_e}")
                        print(f"Problematic JSON string: {json_string}")
                # If neither direct nor markdown block parsing works, continue to next retry

        except requests.exceptions.RequestException as e:
            print(f"Error communicating with Ollama on attempt {attempt + 1}: {e}")
        except Exception as e:
            print(f"An unexpected error occurred on attempt {attempt + 1}: {e}")

        # if attempt < max_retries - 1:
        #     print(f"Retrying in {retry_delay_seconds} seconds...")
        #     time.sleep(retry_delay_seconds)
        # else:
        #     print(f"Max retries ({max_retries}) reached. Could not obtain valid JSON.")

    return {} # Return empty dict if all retries fail


class CategoryAlertRequest(BaseModel):
    last_days: int = Field(84, description="Number of days to look back for trend analysis")
    given_date: str = Field("2025-09-01", description="The reference date for analysis in YYYY-MM-DD format")
    value: int = Field(1, description="Type of Search: 1-Semantic, 2-Keyword, 3-Hybrid")
    CityName: str = Field("All", description="Filter by city name")
    stateName: str = Field("All", description="Filter by state name")
    complaintType: str = Field("All", description="Filter by complaint type")
    complaintMode: str = Field("All", description="Filter by complaint mode")
    companyName: str = Field("All", description="Filter by company name")
    complaintStatus: str = Field("All", description="Filter by complaint status")
    threshold: float = Field(1.3, description="Relevance threshold for search results")
    complaint_numbers: List[str] = Field(["NA"], description="List of specific complaint numbers to include")


@router.post("/get_category_alert")
async def get_category_alert(
    token : Annotated[str, Depends(oauth2_scheme)],
    CategoryAlertRequest: CategoryAlertRequest,
    db: Session = Depends(database.get_db)
):
    '''
    A function to get category wise alert, suppose there is a spike in a particular category it may above 10% of previous day or week or month
    then it should be alerted to the user.
    Parameters
    ----------
    1) es: Elasticsearch client
    2) query: string
    3) value: int -> Represent Type of Search 1-Semantic 2-Keyword 3-hybrid search
    4) skiprecord: int
    5) size: int
    6) threshold: float-> relevance
    Returns
    -------
    A list of dictionaries containing category, subcategory and % increase
    '''
    # iterate all the categories from categories_with_prompt and call categoryWiseAlerts function for each category
    # and append the result to a list and return the list

    #  check if 

    user = await get_current_user(token, db)
    user = user.username.lower()

    results = []

    for category in categories_with_prompt:
        query = category["categoryPrompt"]

        alerts = categoryWiseAlerts(
            query=query,
            last_days=CategoryAlertRequest.last_days,
            given_date=CategoryAlertRequest.given_date,
            value=CategoryAlertRequest.value,
            CityName=CategoryAlertRequest.CityName,
            stateName=CategoryAlertRequest.stateName,
            complaintType=CategoryAlertRequest.complaintType,
            complaintMode=CategoryAlertRequest.complaintMode,
            companyName=CategoryAlertRequest.companyName,
            complaintStatus=CategoryAlertRequest.complaintStatus,
            threshold=CategoryAlertRequest.threshold,
            complaint_numbers=CategoryAlertRequest.complaint_numbers
        )

        if alerts:
            alerts["category"] = category["category"]
            results.append(alerts)

    return results

# get the individual category alerts for a given category
@router.post("/get_individual_category_alert/{category_name}")
async def get_individual_category_alert(
    token : Annotated[str, Depends(oauth2_scheme)],
    category_name: str,
    CategoryAlertRequest: CategoryAlertRequest,
    db: Session = Depends(database.get_db)
):
    user = await get_current_user(token, db)
    user = user.username.lower()

    alerts = categoryWiseAlerts(
        query=category_name,
        last_days=CategoryAlertRequest.last_days,
        given_date=CategoryAlertRequest.given_date,
        value=CategoryAlertRequest.value,
        CityName=CategoryAlertRequest.CityName,
        stateName=CategoryAlertRequest.stateName,
        complaintType=CategoryAlertRequest.complaintType,
        complaintMode=CategoryAlertRequest.complaintMode,
        companyName=CategoryAlertRequest.companyName,
        complaintStatus=CategoryAlertRequest.complaintStatus,
        threshold=CategoryAlertRequest.threshold,
        complaint_numbers=CategoryAlertRequest.complaint_numbers
    )

    if alerts:
        alerts["category"] = category_name

    return alerts