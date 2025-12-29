import argparse
import json
import os
import re
import time
import urllib3
from datetime import datetime
from typing import Dict, Any, Optional, List, Set, Tuple
import numpy as np
import matplotlib.pyplot as plt
from scipy.interpolate import interp1d
import requests
import pandas as pd
from elasticsearch8 import Elasticsearch
from elasticsearch8.helpers import bulk
from sentence_transformers import SentenceTransformer
from tabulate import tabulate

# --- Configuration ---
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

LLAMA_API_KEY = "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"
LLAMA_API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL_NAME = "meta-llama/llama-3-70b-instruct"

def call_openrouter_api(prompt: str):
    headers = {
        "Authorization": f"Bearer {LLAMA_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": "You are an expert query analysis system."},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 1024,
        "temperature": 0.1
    }

    try:
        response = requests.post(LLAMA_API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        response_data = response.json()
        if "choices" in response_data and len(response_data["choices"]) > 0:
            return response_data["choices"][0]["message"]["content"]
        else:
            print(f"❌ Unexpected API response structure: {response_data}")
            return None
    except requests.exceptions.HTTPError as http_err:
        print(f"❌ HTTP error occurred: {http_err}")
        try:
            error_details = response.json()
            print(f"API error details: {error_details}")
        except ValueError:
            print(f"Response content: {response.text}")
        return None
    except requests.exceptions.RequestException as req_err:
        print(f"❌ Request error occurred: {req_err}")
        return None

ELASTICSEARCH_HOST = "https://localhost:9200"
ELASTICSEARCH_AUTH = ("elastic", "KwO1IHXN4OB0DZu*V2mm")
REGISTRATIONS_INDEX = "complaints"  # Updated from "registrations" to match schema3
EXAMPLES_INDEX = "es_examples"
QUERY_LOGS_INDEX = "query_logs"
RAG_SIMILARITY_THRESHOLD = 0.80
VISUALIZATION_DIR = "visualizations"

# Global client variables
es_client: Optional[Elasticsearch] = None
embedding_model: Optional[SentenceTransformer] = None

# Updated ENTITY_KEYWORDS for schema3 and dataset3
ENTITY_KEYWORDS = {
    "status": [0, 1],  # 0 = Open, 1 = Closed (based on dataset context)
    "complaintType": [
        "Delayed Service", "Overcharging", "Misleading Advertisement", "Defective Product",
        "Warranty Issue", "Refund not processed", "Service Denial", "Fraudulent Activity"
    ],
    "complaintMode": [
        "Email", "Phone", "Website", "NCHAPP"
    ],
    "companyStatus": [
        "Pending", "Resolved", "Fraud", "Escalated", "Responded"
    ],
    "complaintStatus": [
        "Open", "Closed", "Escalated", "In Progress"
    ],
    "userType": [
        "Consumer", "Wholesaler", "Retailer"
    ],
    "country": [
        "India"
    ],
    "columns": [
        "id", "complaintDetails", "userId", "fullName", "CityName", "stateName", "country",
        "userType", "status", "complaintRegDate", "updationDate", "complaintType",
        "complaintMode", "categoryCode", "companyName", "complaintStatus", "companyStatus",
        "lastUpdationDate"
    ]
}

# Query intent patterns for better classification
INTENT_PATTERNS = {
    "count": ["count", "how many", "number of", "total", "sum", "min", "max", "avg", "average"],
    "list": ["list", "show", "get", "find", "retrieve", "display"],
    "aggregate": ["group by", "breakdown", "distribution", "by company", "by type"],
    "distinct": ["unique", "distinct", "different", "all possible"],
    "sort": ["sort", "order", "arrange", "ranked", "top", "bottom"],
    "filter": ["from", "in", "where", "with", "having", "contains"],
    "columns": ["show only", "select", "display only", "columns", "fields"]
}

def initialize_clients():
    """Initialize Elasticsearch and embedding model clients."""
    global es_client, embedding_model
    try:
        print("🔄 Initializing Elasticsearch client...")
        es_client = Elasticsearch(
            ELASTICSEARCH_HOST, basic_auth=ELASTICSEARCH_AUTH,
            verify_certs=False, request_timeout=60
        )

        if not es_client.ping():
            raise ConnectionError("Could not connect to Elasticsearch.")
        print(f"✅ Connected to Elasticsearch cluster: {es_client.info()['cluster_name']}")

        print("🔄 Loading embedding model (all-MiniLM-L6-v2)...")
        embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        print("✅ Embedding model loaded.")

        return True
    except Exception as e:
        print(f"❌ Initialization Failed: {e}")
        return False

def get_database_schema() -> Dict[str, Any]:
    """Return the schema matching dataset3.json and schema3.json."""
    schema_path = "schema3.json"  # Ensure this path is correct

    if not os.path.exists(schema_path):
        raise FileNotFoundError(f"Schema file not found: {schema_path}")

    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)

    # Return schema using the key expected elsewhere in the code
    return {REGISTRATIONS_INDEX: schema["complaints"]}

def setup_indices(json_file_path: str) -> bool:
    """Set up Elasticsearch indices with mappings for schema3."""
    if not es_client: 
        return False

    print("\n--- Setting up Elasticsearch Indices ---")
    try:
        if es_client.indices.exists(index=REGISTRATIONS_INDEX):
            es_client.indices.delete(index=REGISTRATIONS_INDEX)
            print(f"Deleted existing data index '{REGISTRATIONS_INDEX}'.")

        # Updated mappings to align with the provided structure
        mappings = {
            "properties": {
                "id": {"type": "keyword"},
                "complaintDetails": {
                    "type": "text",
                    "analyzer": "standard"
                },
                "complaintDetails_embedding": {
                    "type": "dense_vector",
                    "dims": 384,
                    "index": True,
                    "similarity": "cosine"
                },
                "userId": {"type": "integer"},
                "fullName": {
                    "type": "text",
                    "analyzer": "standard",
                    "fields": {"keyword": {"type": "keyword"}}
                },
                "CityName": {
                    "type": "text",
                    "analyzer": "standard",
                    "fields": {"keyword": {"type": "keyword"}}
                },
                "stateName": {
                    "type": "text",
                    "analyzer": "standard",
                    "fields": {"keyword": {"type": "keyword"}}
                },
                "country": {
                    "type": "keyword",
                    "normalizer": "lowercase_normalizer"
                },
                "userType": {
                    "type": "keyword",
                    "normalizer": "lowercase_normalizer"
                },
                "status": {"type": "integer"},
                "complaintRegDate": {"type": "date"},
                "updationDate": {"type": "date"},
                "complaintType": {
                    "type": "keyword",
                    "normalizer": "lowercase_normalizer"
                },
                "complaintMode": {
                    "type": "keyword",
                    "normalizer": "lowercase_normalizer"
                },
                "categoryCode": {"type": "integer"},
                "companyName": {
                    "type": "text",
                    "analyzer": "standard",
                    "fields": {"keyword": {"type": "keyword"}}
                },
                "complaintStatus": {
                    "type": "keyword",
                    "normalizer": "lowercase_normalizer"
                },
                "companyStatus": {
                    "type": "keyword",
                    "normalizer": "lowercase_normalizer"
                },
                "lastUpdationDate": {"type": "keyword"}
            }
        }

        settings = {
            "index.max_ngram_diff": 8,
            "analysis": {
                "normalizer": {
                    "lowercase_normalizer": {
                        "type": "custom",
                        "filter": ["lowercase", "trim"]
                    }
                },
                "analyzer": {
                    "ngram_analyzer": {
                        "type": "custom",
                        "tokenizer": "standard",
                        "filter": ["lowercase", "ngram_filter"]
                    }
                },
                "filter": {
                    "ngram_filter": {
                        "type": "ngram",
                        "min_gram": 2,
                        "max_gram": 10
                    }
                }
            }
        }

        index_config = {
            "settings": settings,
            "mappings": mappings
        }

        es_client.indices.create(index=REGISTRATIONS_INDEX, body=index_config)
        print(f"✅ Created data index '{REGISTRATIONS_INDEX}' with enhanced mappings.")

        # Ingest data
        ingest_data_from_json(json_file_path)

        # Setup examples index
        examples_mapping = {
            "properties": {
                "original_query": {"type": "text"},
                "es_query": {"type": "keyword", "index": False},
                "embedding": {"type": "dense_vector", "dims": 384, "index": True, "similarity": "cosine"},
                "timestamp": {"type": "date"},
                "intent": {"type": "keyword"},
                "entities": {"type": "object"}
            }
        }

        if not es_client.indices.exists(index=EXAMPLES_INDEX):
            es_client.indices.create(index=EXAMPLES_INDEX, body={"mappings": examples_mapping})
            print(f"✅ Created RAG examples index '{EXAMPLES_INDEX}'.")
        else:
            print(f"✅ RAG examples index '{EXAMPLES_INDEX}' exists.")

        # Create visualizations directory if it doesn't exist
        if not os.path.exists(VISUALIZATION_DIR):
            os.makedirs(VISUALIZATION_DIR)
            print(f"✅ Created visualizations directory: {VISUALIZATION_DIR}")

        return True
    except Exception as e:
        print(f"❌ Index setup failed: {e}")
        return False

def ingest_data_from_json(json_file_path: str):
    """Enhanced data ingestion adapted for schema3 structure."""
    if not embedding_model:
        print("❌ Embedding model not loaded. Cannot ingest data.")
        return

    if not os.path.exists(json_file_path):
        print(f"❌ File not found: {json_file_path}")
        return

    with open(json_file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    actions = []
    date_fields = {'complaintRegDate', 'updationDate'}  # Updated date fields for schema3

    print("⏳ Generating embeddings and preparing documents for ingestion...")

    for i, record in enumerate(data):
        try:
            # Process date fields for schema3
            for field in date_fields:
                if field in record and record[field]:
                    try:
                        # Handle different date formats in dataset3
                        if field == 'updationDate' and isinstance(record[field], str):
                            # Handle format "2025-10-18 08:23:55"
                            if ' ' in record[field]:
                                record[field] = record[field].split(' ')[0] + 'T' + record[field].split(' ')[1]
                        record[field] = pd.to_datetime(record[field]).isoformat()
                    except (ValueError, TypeError):
                        record[field] = None

            # Calculate processing time using new date fields
            reg_date, upd_date = record.get('complaintRegDate'), record.get('updationDate')
            if reg_date and upd_date:
                try:
                    reg_dt = pd.to_datetime(reg_date)
                    upd_dt = pd.to_datetime(upd_date)
                    record['processing_time_days'] = int((upd_dt - reg_dt).days)
                except Exception:
                    record['processing_time_days'] = None
            else:
                record['processing_time_days'] = None

            # Generate embeddings for complaintDetails (updated field name)
            if 'complaintDetails' in record and record['complaintDetails']:
                try:
                    embedding = embedding_model.encode(record['complaintDetails']).tolist()
                    record['complaintDetails_embedding'] = embedding
                except Exception as e:
                    print(f"⚠️ Could not generate embedding for record {i}: {e}")

            actions.append({"_index": REGISTRATIONS_INDEX, "_source": record})

        except Exception as e:
            print(f"⚠️ Error processing record {i}: {e}")
            continue

    if actions:
        try:
            success, failed = bulk(es_client, actions, chunk_size=100, request_timeout=60)
            print(f"📈 Ingested {success} documents. Failed: {len(failed)}.")
        except Exception as e:
            print(f"❌ Bulk ingestion failed: {e}")
def classify_query_intent(user_query: str) -> str:
    """Classify query intent using pattern matching."""
    lower_query = user_query.lower()
    if any(pattern in lower_query for pattern in INTENT_PATTERNS["count"]):
        return "aggregate_data"
    if any(pattern in lower_query for pattern in INTENT_PATTERNS["distinct"]):
        return "list_distinct_values"
    if any(pattern in lower_query for pattern in INTENT_PATTERNS["sort"]):
        return "filter_data_sorted"
    if any(pattern in lower_query for pattern in INTENT_PATTERNS["columns"]):
        return "filter_data_columns"
    return "filter_data"

def normalize_query(query: str) -> str:
    """Normalize query to handle different word orders and phrasings."""
    query = query.lower().strip()
    patterns = [
        (r'\bdata from company (.+)', r'data from \1 company'),
        (r'\bfrom company (.+)', r'from \1 company'),
        (r'\bcompany (.+) data', r'data from \1 company'),
        (r'\bshow (.+) from (.+)', r'show data from \2 for \1'),
        (r'\bget (.+) from (.+)', r'show data from \2 for \1'),
        (r'\blist (.+) from (.+)', r'show data from \2 for \1'),
    ]

    for pattern, replacement in patterns:
        query = re.sub(pattern, replacement, query)
    return query

def extract_entities_with_disambiguation(text: str) -> Dict[str, Any]:
    """Extract entities based on schema3 fields."""
    entities = {}
    lower_text = text.lower()

    # Extract keyword-based entities for schema3
    for field, keywords in ENTITY_KEYWORDS.items():
        if field == "columns":
            continue
        found_keywords = []
        for kw in keywords:
            # Check for exact match (case-insensitive)
            if isinstance(kw, str):
                if re.search(r'\b' + re.escape(kw.lower()) + r'\b', lower_text):
                    found_keywords.append(kw)
                # Check for partial multi-word matches
                elif len(str(kw).split()) > 1 and any(part.lower() in lower_text for part in str(kw).split()):
                    found_keywords.append(kw)
            else:
                # Handle integer values like status
                if str(kw) in lower_text:
                    found_keywords.append(kw)

        if found_keywords:
            entities[field] = list(set(found_keywords))

    # Extract dates, numbers, and comparisons
    date_patterns = [r'\b\d{4}-\d{2}-\d{2}\b', r'\b\d{2}/\d{2}/\d{4}\b', r'\b\d{1,2}-\d{1,2}-\d{4}\b']
    dates = []
    for pattern in date_patterns:
        dates.extend(re.findall(pattern, lower_text))
    if dates:
        entities['dates'] = dates

    numbers = re.findall(r'\b\d+\b', lower_text)
    ranges = re.findall(r'(\d+)\s*-\s*(\d+)', lower_text)
    if numbers:
        entities['numbers'] = numbers
    if ranges:
        entities['ranges'] = ranges

    comparisons = []
    gt_match = re.search(r'\b(more than|greater than|above|over)\s+(\d+)', lower_text)
    if gt_match:
        comparisons.append(('gt', gt_match.group(2)))
    lt_match = re.search(r'\b(less than|under|below)\s+(\d+)', lower_text)
    if lt_match:
        comparisons.append(('lt', lt_match.group(2)))
    if comparisons:
        entities['comparisons'] = comparisons

    # Detect logical operators
    logical_operators = {
        'and': ['and', '&', 'plus', 'also'],
        'or': ['or', '|', 'either'],
        'not': ['not', 'except', 'excluding', 'but not', 'without']
    }

    detected_operators = []
    for op_type, keywords in logical_operators.items():
        for keyword in keywords:
            if keyword in lower_text:
                detected_operators.append(op_type)
                break
    if detected_operators:
        entities['logical_operators'] = list(set(detected_operators))

    return entities

def ensure_conditional_columns(result, query):
    """Helper function to ensure conditional columns are included only when appropriate."""
    filters = result.get("filters", [])
    columns = result.get("columns", [])
    valid_columns = [col['name'] for col in get_database_schema()[REGISTRATIONS_INDEX]['columns'] if 'embedding' not in col['name']]

    # Only add filter fields to columns for filter_data_columns intent
    if result.get("intent") == "filter_data_columns":
        for f in filters:
            field = f.get("field")
            if field in valid_columns and field not in columns:
                columns.append(field)

    # Ensure columns is empty for "show all" or "show data" queries without column specifiers
    lower_query = query.lower().strip()
    if lower_query.startswith("show all") or (lower_query.startswith("show data") and not any(p in lower_query for p in INTENT_PATTERNS["columns"])):
        columns = []

    result["columns"] = columns
    return result

def parse_intent_and_entities_enhanced(user_query: str) -> Optional[Dict[str, Any]]:
    """Enhanced intent parsing adapted for schema3 with column selection and conditional column inclusion."""
    try:
        lower_query = user_query.strip().lower()

        # Handle "show all" queries explicitly
        if lower_query.startswith("show all") or lower_query.startswith("list all"):
            normalized_query = normalize_query(user_query)
            entities = extract_entities_with_disambiguation(normalized_query)
            filters = []

            for field, values in entities.items():
                if field in ["status", "complaintType", "complaintMode", "companyStatus", "complaintStatus", "userType"]:
                    for value in values:
                        filters.append({"field": field, "value": value, "operator": "term"})
                elif field == "dates":
                    for date in values:
                        filters.append({"field": "complaintRegDate", "value": date, "operator": "range"})

            # Handle content-based filters (e.g., "regarding network issues")
            content_indicators = ["regarding", "about", "concerning"]
            for indicator in content_indicators:
                if indicator in lower_query:
                    topic = lower_query.split(indicator, 1)[1].strip()
                    if topic:
                        filters.append({"field": "complaintDetails", "value": topic, "operator": "match"})

            result = {"intent": "filter_data", "filters": filters, "columns": []}
            return ensure_conditional_columns(result, user_query)

        # Handle simple queries first
        if user_query.strip().lower() in ["get all", "fetch everything"]:
            result = {"intent": "filter_data", "filters": [], "columns": []}
            return ensure_conditional_columns(result, user_query)

        # Normalize the query
        normalized_query = normalize_query(user_query)

        # Extract entities with disambiguation
        entities = extract_entities_with_disambiguation(normalized_query)

        # Enhanced LLM prompt with column selection support (aligned to schema3.json)
        schema_info = get_database_schema()[REGISTRATIONS_INDEX]['columns']
        field_descriptions = {
            'id': 'Unique ID for each complaint record',
            'complaintDetails': 'Detailed description of the complaint',
            'userId': 'User ID of the complainant',
            'fullName': 'Full name of the complainant',
            'CityName': 'City name of the complainant',
            'stateName': 'State name of the complainant',
            'country': 'Country of the complainant',
            'userType': 'Type of user (Consumer, Wholesaler, Retailer)',
            'status': 'Complaint status as integer (0=Open, 1=Closed)',
            'complaintRegDate': 'Date when complaint was registered',
            'updationDate': 'Date when complaint was last updated',
            'complaintType': 'Type/category of the complaint',
            'complaintMode': 'Mode of complaint submission (Email, Phone, Website, NCHAPP)',
            'categoryCode': 'Numeric category code for the complaint',
            'companyName': 'Name of the company against which complaint was filed',
            'complaintStatus': 'Current status of complaint processing',
            'companyStatus': 'Company response status',
            'lastUpdationDate': 'Last update timestamp as string'
        }

        field_info = "\n".join([
            f"- {col['name']}: {field_descriptions.get(col['name'], 'No description')}"
            for col in schema_info
        ])

        prompt = f"""You are an expert query analysis system that converts natural language queries into structured JSON for Elasticsearch.

## Configuration

**Available Fields:**
{field_info}

**Intent Types:** filter_data, filter_data_columns, aggregate_data, list_distinct_values

**Output Format:** JSON only (no explanations, comments, or additional text)

## Critical Rules

### Column Selection
- When phrases like "show only", "select", "display only", "columns", "fields", or singular/plural field names are used, include only those fields in the "columns" array.
- If no columns are specified or query starts with "show all"/"list all", return an empty columns array for `filter_data`.
- Invalid column names should be ignored.
- Column names must match schema fields exactly.
- **Include the field used in a filter in the `columns` array only for `filter_data_columns` intent, not for `filter_data`.**

### Intent Detection
| Query Pattern | Intent | Notes |
|---------------|--------|-------|
| count, how many, total, chart, graph, plot, visualize, min, max, avg, average | aggregate_data | Group by relevant field, include stats if min/max/avg mentioned |
| list unique, distinct, show all unique | list_distinct_values | Return unique values for the specified field |
| show, find, get, display, fetch | filter_data | If no columns specified; use filter_data_columns if columns are present |
| show only, select, display only, columns, fields, or field names | filter_data_columns | Filter and return specified columns |
| top N, top X | aggregate_data | Limit aggregation to top N results |

### Field Mapping Rules
| Query Context | Field | Operator | Notes |
|---------------|-------|----------|-------|
| Company name | companyName | match | Use match (for full-text search) |
| Date ranges | complaintRegDate/updationDate | range | Use ISO format (YYYY-MM-DD) |
| Complaint type | complaintType | match | Use match for full-text search |
| Complaint mode | complaintMode | match | Use match for full-text search |
| Complaint details | complaintDetails | match | Use match (full-text search) |
| Status | status | term | Use integer values (0 or 1) |
| Complaint status | complaintStatus | term | Exact match |
| Company status | companyStatus | term | Exact match |
| User type | userType | term | Exact match |
| Full name | fullName | match | Use match for full-text search |
| City/State | CityName/stateName | match | Use match for full-text search |

### Date Processing
- "after 2024 May" → `{{"gte": "2024-05-01"}}`
- "before March 2024" → `{{"lt": "2024-03-01"}}`
- "last 30 days" → `{{"gte": "now-30d"}}`
- "2024" → `{{"gte": "2024-01-01", "lt": "2025-01-01"}}`

### Sorting & Pagination
- Add `sort_order` for explicit sorting requests.
- Default `size: 10` for filter queries.
- Use `asc` for chronological/numerical order, `desc` for recent-first.
- For 'top N' in aggregate_data, set `size` in terms aggregation to N.

## Output Schema
```json
{{
"intent": "filter_data|filter_data_columns|aggregate_data|list_distinct_values",
"filters": [
{{
"field": "field_name",
"value": "search_value",
"operator": "match|term|range"
}}
],
"columns": ["field_name1", "field_name2"], // Only for filter_data_columns
"group_by_field": "field_name", // Only for aggregate_data
"sort_order": {{
"field": "field_name",
"order": "asc|desc"
}},
"size": 10, // For filter queries; for aggregate_data, use in terms aggregation
"top_n": N, // Optional for aggregate_data to limit to top N results
"include_stats": true // Include stats aggregation for min/max/avg
}}
```

## Examples
Q: "show all complaints by phone"
A: {{"intent": "filter_data", "filters": [{{"field": "complaintMode", "value": "Phone", "operator": "match"}}], "columns": []}}

Q: "show only id and status for email complaints"
A: {{"intent": "filter_data_columns", "filters": [{{"field": "complaintMode", "value": "Email", "operator": "match"}}], "columns": ["id", "status", "complaintMode"]}}

Q: "count complaints by companyStatus"
A: {{"intent": "aggregate_data", "group_by_field": "companyStatus", "columns": []}}

Q: "show complaintDetails, fullName for open complaints"
A: {{"intent": "filter_data_columns", "filters": [{{"field": "status", "value": 0, "operator": "term"}}], "columns": ["complaintDetails", "fullName", "status"]}}

Q: "list unique values of userType"
A: {{"intent": "list_distinct_values", "field": "userType", "columns": []}}

Q: "show all complaints from Flipkart"
A: {{"intent": "filter_data", "filters": [{{"field": "companyName", "value": "Flipkart", "operator": "match"}}], "columns": []}}

Q: "count complaints received after January 2024"
A: {{"intent": "aggregate_data", "filters": [{{"field": "complaintRegDate", "value": {{"gte": "2024-01-01"}}, "operator": "range"}}], "group_by_field": "complaintType", "columns": []}}

Q: "show id, complaintRegDate for closed complaints sorted by date"
A: {{"intent": "filter_data_columns", "filters": [{{"field": "status", "value": 1, "operator": "term"}}], "columns": ["id", "complaintRegDate", "status"], "sort_order": {{"field": "complaintRegDate", "order": "asc"}}}}

Query: {user_query}

Output:""".strip()

        try:
            output = call_openrouter_api(prompt)
            if not output:
                print("❌ LLM returned no valid output. Falling back to rule-based parsing.")
                return fallback_parse_intent(normalized_query, entities, user_query)

            try:
                result = json.loads(output)
                if not isinstance(result, dict) or "intent" not in result:
                    raise ValueError("Invalid LLM response structure")
                result = ensure_conditional_columns(result, user_query)
                return result
            except (json.JSONDecodeError, ValueError):
                json_match = re.search(r'{.*}', output, re.DOTALL)
                if json_match:
                    try:
                        result = json.loads(json_match.group(0))
                        if isinstance(result, dict) and "intent" in result:
                            result = ensure_conditional_columns(result, user_query)
                            return result
                    except json.JSONDecodeError:
                        pass

                print(f"❌ LLM returned invalid JSON: {output}")
                return fallback_parse_intent(normalized_query, entities, user_query)

        except Exception as e:
            print(f"Error calling LLM: {e}")
            return fallback_parse_intent(normalized_query, entities, user_query)

    except Exception as e:
        print(f"Error in parse_intent_and_entities_enhanced: {e}")
        try:
            normalized_query = normalize_query(user_query)
            entities = extract_entities_with_disambiguation(normalized_query)
            return fallback_parse_intent(normalized_query, entities, user_query)
        except Exception as fallback_error:
            print(f"Fallback parsing also failed: {fallback_error}")
            return None
def fallback_parse_intent(user_query: str, entities: Dict[str, Any], original_query: str) -> Dict[str, Any]:
    """Enhanced fallback rule-based intent parsing adapted for schema3."""
    try:
        lower_query = user_query.lower().strip()
        valid_columns = [col['name'] for col in get_database_schema()[REGISTRATIONS_INDEX]['columns'] if 'embedding' not in col['name']]

        # Handle column specifications (e.g., "show company names, userType, status")
        columns = []
        column_patterns = [
            r'\b(show only|select|display only|columns|fields)\s+([\w\s,]+)', # e.g., "show only name, status"
            r'\bcolumns\s*:\s*([\w\s,]+)', # e.g., "columns: name, status"
            r'\b(show|list)\s+(names?|types?|statuses?)\b', # e.g., "show types"
            r'\b([\w\s,]+)\s+from\b' # e.g., "companyName, userType from complaints"
        ]

        for pattern in column_patterns:
            match = re.search(pattern, lower_query)
            if match:
                if pattern == column_patterns[2]: # Handle plural forms like "types"
                    column_str = match.group(2).rstrip('s')
                    if column_str in valid_columns:
                        columns = [column_str]
                else:
                    column_str = match.group(2 if pattern != column_patterns[3] else 1)
                    potential_columns = [c.strip().replace(' ', '_') for c in column_str.split(',')]
                    columns = [c for c in potential_columns if c in valid_columns]
                break

        # Additional check for direct column mentions
        if not columns:
            for col in valid_columns:
                if f'\\b{col.replace("_", " ")}\\b' in lower_query:
                    columns.append(col)

        # Initialize filters
        filters = []

        # Enhanced date parsing for schema3 date fields
        month_map = {
            "january": "01", "jan": "01", "february": "02", "feb": "02", "march": "03", "mar": "03",
            "april": "04", "apr": "04", "may": "05", "june": "06", "jun": "06", "july": "07", "jul": "07",
            "august": "08", "aug": "08", "september": "09", "sep": "09", "october": "10", "oct": "10",
            "november": "11", "nov": "11", "december": "12", "dec": "12"
        }

        # Handle "after ", "from ", "since "
        date_after_match = re.search(r'\\b(after|from|since)\\s+(january|jan|february|feb|march|mar|april|apr|may|june|jun|july|jul|august|aug|september|sep|october|oct|november|nov|december|dec)\\s+(\\d{4})\\b', lower_query)
        if date_after_match:
            _, month, year = date_after_match.groups()
            month_num = month_map.get(month.lower(), "01")
            filters.append({
                "field": "complaintRegDate",  # Updated for schema3
                "value": {"gte": f"{year}-{month_num}-01"},
                "operator": "range"
            })

        # Handle "before "
        date_before_match = re.search(r'\\bbefore\\s+(january|jan|february|feb|march|mar|april|apr|may|june|jun|july|jul|august|aug|september|sep|october|oct|november|nov|december|dec)\\s+(\\d{4})\\b', lower_query)
        if date_before_match:
            month, year = date_before_match.groups()
            month_num = month_map.get(month.lower(), "01")
            filters.append({
                "field": "complaintRegDate",  # Updated for schema3
                "value": {"lt": f"{year}-{month_num}-01"},
                "operator": "range"
            })

        # Handle exact date patterns
        exact_date_patterns = [r'\\b\\d{4}-\\d{2}-\\d{2}\\b', r'\\b\\d{2}/\\d{2}/\\d{4}\\b', r'\\b\\d{1,2}-\\d{1,2}-\\d{4}\\b']
        for pattern in exact_date_patterns:
            date_matches = re.findall(pattern, lower_query)
            for date in date_matches:
                try:
                    parsed_date = pd.to_datetime(date, errors='coerce').strftime('%Y-%m-%d')
                    if parsed_date and not pd.isna(parsed_date):
                        filters.append({
                            "field": "complaintRegDate",  # Updated for schema3
                            "value": {"gte": parsed_date, "lte": parsed_date},
                            "operator": "range"
                        })
                except:
                    continue

        # Handle relative dates
        relative_date_match = re.search(r'\\blast\\s+(\\d+)\\s+days\\b', lower_query)
        if relative_date_match:
            days = relative_date_match.group(1)
            filters.append({
                "field": "complaintRegDate",  # Updated for schema3
                "value": {"gte": f"now-{days}d"},
                "operator": "range"
            })

        # Parse entities from schema3 fields
        for field, values in entities.items():
            if field in ["status", "complaintType", "complaintMode", "companyStatus", "complaintStatus", "userType"]:
                for value in values:
                    if field == "status":
                        # Handle status as integer for schema3
                        operator = "term"
                        if isinstance(value, str):
                            value = 0 if value.lower() in ["open", "0"] else 1
                    else:
                        operator = "match" if field in ["complaintType", "complaintMode"] else "term"
                    filters.append({"field": field, "value": value, "operator": operator})

        # Handle company name searches (updated field name)
        company_patterns = [
            r'\\bfrom\\s+([\w\s]+?)\\s+(company|corp|ltd|inc)',
            r'\\bcompany\\s+([\w\s]+)',
            r'\\b([\w\s]+?)\\s+complaints?\\b'
        ]

        for pattern in company_patterns:
            match = re.search(pattern, lower_query)
            if match:
                company = match.group(1).strip()
                if len(company) > 2:  # Avoid single letters
                    filters.append({"field": "companyName", "value": company, "operator": "match"})
                break

        # Determine intent based on query patterns
        intent = "filter_data"
        group_by_field = None

        if any(kw in lower_query for kw in ["count", "how many", "number of", "total"]):
            intent = "aggregate_data"
            # Default group by field for schema3
            if "by company" in lower_query or "by companyName" in lower_query:
                group_by_field = "companyName"
            elif "by type" in lower_query or "by complaintType" in lower_query:
                group_by_field = "complaintType"
            elif "by status" in lower_query:
                group_by_field = "status"
            elif "by mode" in lower_query or "by complaintMode" in lower_query:
                group_by_field = "complaintMode"
            else:
                group_by_field = "complaintType"  # Default grouping

        elif any(kw in lower_query for kw in ["unique", "distinct"]):
            intent = "list_distinct_values"
            # Determine field for distinct values
            for field in valid_columns:
                if field in lower_query:
                    group_by_field = field
                    break
            if not group_by_field:
                group_by_field = "companyName"  # Default

        if columns:
            intent = "filter_data_columns"

        # Build result
        result = {
            "intent": intent,
            "filters": filters,
            "columns": columns,
            "size": 10
        }

        if group_by_field:
            result["group_by_field"] = group_by_field

        # Add sorting if requested
        if any(kw in lower_query for kw in ["sort", "order", "arranged"]):
            if "date" in lower_query or "time" in lower_query:
                result["sort_order"] = {"field": "complaintRegDate", "order": "desc"}
            elif "name" in lower_query:
                result["sort_order"] = {"field": "fullName", "order": "asc"}

        return result

    except Exception as e:
        print(f"❌ Fallback parsing failed: {e}")
        return {
            "intent": "filter_data",
            "filters": [],
            "columns": [],
            "size": 10
        }

def construct_elasticsearch_query(parsed_query: Dict[str, Any]) -> Dict[str, Any]:
    """Construct Elasticsearch query adapted for schema3 structure."""
    intent = parsed_query.get("intent", "filter_data")
    filters = parsed_query.get("filters", [])

    # Define case-insensitive fields for lowercase normalization
    case_insensitive_fields = {
        "companyStatus",
        "complaintStatus",
        "userType",
        "complaintType",
        "complaintMode",
        "country",
    }

    # Build base query structure
    if intent == "aggregate_data":
        query = {"size": 0, "query": {"bool": {"must": []}}}

        # Add filters to the query
        for filter_item in filters:
            field = filter_item["field"]
            value = filter_item["value"]
            operator = filter_item["operator"]

            # Normalize value to lowercase if field is in the case-insensitive set
            if field in case_insensitive_fields and isinstance(value, str):
                value = value.lower()

            # Continue building the ES clause with this possibly lowercased value
            if operator == "match":
                query["query"]["bool"]["must"].append({"match": {field: value}})
            elif operator == "term":
                query["query"]["bool"]["must"].append({"term": {field: value}})
            elif operator == "range":
                query["query"]["bool"]["must"].append({"range": {field: value}})

        # Add aggregations
        group_by_field = parsed_query.get("group_by_field", "companyName")
        agg_size = parsed_query.get("top_n", 20)

        query["aggs"] = {
            "grouped_data": {
                "terms": {
                    "field": f"{group_by_field}.keyword" if group_by_field in ["companyName", "fullName", "CityName", "stateName", "complaintType", "complaintMode"] else group_by_field,
                    "size": agg_size
                }
            }
        }

        if parsed_query.get("include_stats"):
            query["aggs"]["stats"] = {"stats": {"field": "userId"}}

    elif intent == "list_distinct_values":
        field = parsed_query.get("group_by_field", parsed_query.get("field", "companyName"))
        query = {
            "size": 0,
            "query": {"match_all": {}},
            "aggs": {
                "distinct_values": {
                    "terms": {
                        "field": f"{field}.keyword" if field in ["companyName", "fullName", "CityName", "stateName", "complaintType", "complaintMode"] else field,
                        "size": 1000
                    }
                }
            }
        }

    else:  # filter_data or filter_data_columns
        size = parsed_query.get("size", 10)

        # Use match_all if no filters
        if not filters:
            query = {
                "size": size,
                "query": {"match_all": {}},
                "_source": True
            }
        else:
            bool_query = {"must": []}
            for filter_item in filters:
                field = filter_item["field"]
                value = filter_item["value"]
                operator = filter_item["operator"]

                # Normalize value to lowercase if field is in the case-insensitive set
                if field in case_insensitive_fields and isinstance(value, str):
                    value = value.lower()

                # Continue building the ES clause with this possibly lowercased value
                if operator == "match":
                    bool_query["must"].append({"match": {field: value}})
                elif operator == "term":
                    bool_query["must"].append({"term": {field: value}})
                elif operator == "range":
                    bool_query["must"].append({"range": {field: value}})

            query = {
                "size": size,
                "query": {"bool": bool_query},
                "_source": True
            }

        if intent == "filter_data_columns":
            columns = parsed_query.get("columns", [])
            if columns:
                query["_source"] = columns

        if "sort_order" in parsed_query:
            sort_field = parsed_query["sort_order"]["field"]
            sort_order = parsed_query["sort_order"]["order"]
            query["sort"] = [{sort_field: {"order": sort_order}}]

    return query



def execute_elasticsearch_query(es_query: Dict[str, Any]) -> Tuple[bool, Any]:
    """Execute Elasticsearch query with error handling."""
    try:
        if not es_client:
            return False, "Elasticsearch client not initialized"

        response = es_client.search(index=REGISTRATIONS_INDEX, body=es_query, request_timeout=30)
        return True, response
    except Exception as e:
        print(f"❌ Elasticsearch query execution failed: {e}")
        return False, str(e)
def format_results(response: Dict[str, Any], intent: str, user_query: str) -> str:
    """Format Elasticsearch results for display, adapted for schema3."""
    try:
        if intent == "aggregate_data":
            if "aggregations" in response and "grouped_data" in response["aggregations"]:
                buckets = response["aggregations"]["grouped_data"]["buckets"]
                if not buckets:
                    return "No data found for the specified criteria."

                headers = ["Value", "Count"]
                rows = []
                for bucket in buckets:
                    rows.append([bucket["key"], bucket["doc_count"]])

                # Add stats if available
                stats_info = ""
                if "stats" in response.get("aggregations", {}):
                    stats = response["aggregations"]["stats"]
                    stats_info = f"\n\nStatistics: Min: {stats.get('min', 'N/A')}, Max: {stats.get('max', 'N/A')}, Avg: {stats.get('avg', 'N/A'):.2f}"

                return f"**Aggregation Results:**\n```\n{tabulate(rows, headers=headers, tablefmt='grid')}\n```{stats_info}"
            else:
                return "No aggregation data found."

        elif intent == "list_distinct_values":
            if "aggregations" in response and "distinct_values" in response["aggregations"]:
                buckets = response["aggregations"]["distinct_values"]["buckets"]
                if not buckets:
                    return "No distinct values found."

                values = [bucket["key"] for bucket in buckets]
                return f"**Distinct Values ({len(values)} total):**\n" + "\n".join([f"• {value}" for value in values[:50]])
            else:
                return "No distinct values found."

        else:  # filter_data or filter_data_columns
            hits = response.get("hits", {}).get("hits", [])
            if not hits:
                return "No results found for your query."

            total = response.get("hits", {}).get("total", {})
            if isinstance(total, dict):
                total_count = total.get("value", 0)
            else:
                total_count = total

            # Format results based on the data structure
            headers = []
            rows = []

            # Get first hit to determine available fields
            first_hit = hits[0]["_source"]

            # Show all fields from the source for full visibility
            headers = list(first_hit.keys())
            # Remove embedding field from display as it's not human-readable
            headers = [h for h in headers if 'embedding' not in h.lower()]

            for hit in hits[:20]:  # Limit to 20 results for display
                source = hit["_source"]
                row = []
                for header in headers:
                    value = source.get(header, "N/A")
                    # Format specific fields
                    if header in ["complaintRegDate", "updationDate"] and value:
                        try:
                            value = pd.to_datetime(value).strftime("%Y-%m-%d")
                        except:
                            pass
                    elif header == "status":
                        value = "Open" if value == 0 else "Closed" if value == 1 else value
                    elif isinstance(value, str) and len(value) > 50:
                        value = value[:47] + "..."
                    row.append(str(value))
                rows.append(row)

            table = tabulate(rows, headers=headers, tablefmt="grid", maxcolwidths=[None] * len(headers))

            return f"**Query Results** (Showing {len(rows)} of {total_count} total results):\n```\n{table}\n```"

    except Exception as e:
        print(f"❌ Error formatting results: {e}")
        return f"Error formatting results: {str(e)}"

def save_query_example(user_query: str, es_query: Dict[str, Any], intent: str, entities: Dict[str, Any]):
    """Save successful query examples for RAG learning."""
    try:
        if not embedding_model:
            return

        embedding = embedding_model.encode(user_query).tolist()

        example_doc = {
            "original_query": user_query,
            "es_query": json.dumps(es_query),
            "embedding": embedding,
            "timestamp": datetime.now().isoformat(),
            "intent": intent,
            "entities": entities
        }

        es_client.index(index=EXAMPLES_INDEX, body=example_doc)
        print("✅ Query example saved for future learning.")
    except Exception as e:
        print(f"⚠️ Could not save query example: {e}")

def process_user_query(user_query: str, save_example: bool = True) -> str:
    """Main function to process user queries end-to-end, adapted for schema3."""
    try:
        print(f"\n🔍 Processing query: {user_query}")

        # Parse intent and entities
        parsed_query = parse_intent_and_entities_enhanced(user_query)
        if not parsed_query:
            return "❌ Could not understand your query. Please try rephrasing."

        print(f"📋 Parsed intent: {parsed_query.get('intent')}")
        print(f"🎯 Filters: {len(parsed_query.get('filters', []))}")

        # Construct Elasticsearch query
        es_query = construct_elasticsearch_query(parsed_query)
        print("🔧 Executing Elasticsearch query:")
        import json
        print(json.dumps(es_query, indent=2))

        # Execute query
        success, response = execute_elasticsearch_query(es_query)
        if not success:
            return f"❌ Query execution failed: {response}"

        # Log query and ES query JSON into dedicated logs index for analytics
        try:
            from datetime import datetime
            log_doc = {
                "user_query": user_query,
                "es_query": es_query,
                "timestamp": datetime.utcnow().isoformat()
            }
            es_client.index(index=QUERY_LOGS_INDEX, body=log_doc)
            print("✅ Logged query and ES JSON for analysis.")
        except Exception as e:
            print(f"⚠️ Failed to log query example: {e}")

        # Format results
        formatted_results = format_results(response, parsed_query["intent"], user_query)

        # Save successful example for RAG learning
        if save_example and success:
            save_query_example(user_query, es_query, parsed_query["intent"], parsed_query.get("entities", {}))

        return formatted_results

    except Exception as e:
        print(f"❌ Error processing query: {e}")
        return f"Error processing your query: {str(e)}"

def interactive_mode():
    """Interactive query mode for testing."""
    print("\n" + "="*60)
    print("="*60)
    print("Enter your queries below. Type 'quit' or 'exit' to stop.")
    print("• 'show all complaints from Flipkart'")
    print("• 'count complaints by status'")
    print("• 'show id, fullName for open complaints'")
    print("• 'list unique userType values'")
    print("-"*60)

    while True:
        try:
            user_input = input("\n📝 Your query: ").strip()

            if user_input.lower() in ['quit', 'exit', 'q']:
                print("👋 Goodbye!")
                break

            if not user_input:
                continue

            start_time = time.time()
            result = process_user_query(user_input)
            end_time = time.time()

            print(f"\n{result}")
            print(f"\n⏱️ Query processed in {end_time - start_time:.2f} seconds")

        except KeyboardInterrupt:
            print("\n\n👋 Interrupted. Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ An error occurred: {e}")

def main():
    """Main function with argument parsing."""
    parser = argparse.ArgumentParser(description="Enhanced Elasticsearch Query System for Schema3 & Dataset3")
    parser.add_argument("--json-file", default="dataset3.json", help="Path to JSON data file")
    parser.add_argument("--setup-indices", action="store_true", help="Set up Elasticsearch indices")
    parser.add_argument("--interactive", action="store_true", help="Start interactive query mode")
    parser.add_argument("--query", type=str, help="Single query to execute")

    args = parser.parse_args()

    # Set interactive mode as default if no other arguments are provided
    if not any([args.interactive, args.query, args.setup_indices]):
        args.interactive = True

    # Initialize clients
    if not initialize_clients():
        print("❌ Failed to initialize. Exiting.")
        return

    # Setup indices if requested
    if args.setup_indices:
        if setup_indices(args.json_file):
            print("✅ Indices setup completed successfully.")
        else:
            print("❌ Index setup failed.")
            return

    
    if args.query:
        result = process_user_query(args.query)
        print(f"\n{result}")
        return

    
    if args.interactive:
        interactive_mode()
        return

    
    parser.print_help()

if __name__ == "__main__":
    main()
