import sys
from pathlib import Path
from fastapi import APIRouter
import pandas as pd
router = APIRouter(tags=["Basic Features"])
import json
from sqlalchemy.sql import text
from openai import OpenAI
import time

# ---------------------------- Path Management ----------------------------
resources_dir = Path(__file__).resolve().parents[2] / "resources"
sys.path.append(str(resources_dir))
# ---------------------------- Import External Utilities ----------------------------
from utility import getES, getEmbed, load_config, connectDB_alchemy, connectDB, closeDB
config = load_config()
# ---------------------------- Constants ----------------------------



MAPPING_STATE_ID_TO_NAME_PATH = resources_dir / Path(config["MAPPING_STATE_ID_TO_NAME_PATH"]).name
MAPPING_CITY_ID_TO_NAME_PATH = resources_dir / Path(config["MAPPING_CITY_ID_TO_NAME_PATH"]).name

with open(MAPPING_STATE_ID_TO_NAME_PATH, 'r') as f:
    MAPPING_STATE = json.load(f)
with open(MAPPING_CITY_ID_TO_NAME_PATH, 'r') as f:
    MAPPING_CITY = json.load(f)

MAPPING_STATE_NAME_TO_ID_PATH = resources_dir / Path(config["MAPPING_STATE_NAME_TO_ID_PATH"]).name
MAPPING_CITY_NAME_TO_ID_PATH = resources_dir / Path(config["MAPPING_CITY_NAME_TO_ID_PATH"]).name

with open(MAPPING_STATE_NAME_TO_ID_PATH, 'r') as f:
    MAPPING_STATE_NAME_TO_ID = json.load(f)
with open(MAPPING_CITY_NAME_TO_ID_PATH, 'r') as f:
    MAPPING_CITY_NAME_TO_ID = json.load(f)

MAPPING_CATEGORY_ID_TO_NAME_PATH = resources_dir / Path(config["MAPPING_CATEGORY_ID_TO_NAME_PATH"]).name
MAPPING_CATEGORY_NAME_TO_ID_PATH = resources_dir / Path(config["MAPPING_CATEGORY_NAME_TO_ID_PATH"]).name
MAPPING_SECTOR_ID_TO_NAME_PATH = resources_dir / Path(config["MAPPING_SECTOR_ID_TO_NAME_PATH"]).name
MAPPING_SECTOR_NAME_TO_ID_PATH = resources_dir / Path(config["MAPPING_SECTOR_NAME_TO_ID_PATH"]).name

with open(MAPPING_CATEGORY_ID_TO_NAME_PATH, 'r') as f:
    MAPPING_CATEGORY = json.load(f)
with open(MAPPING_CATEGORY_NAME_TO_ID_PATH, 'r') as f:
    MAPPING_CATEGORY_NAME_TO_ID = json.load(f)
with open(MAPPING_SECTOR_ID_TO_NAME_PATH, 'r') as f:
    MAPPING_SECTOR = json.load(f)
with open(MAPPING_SECTOR_NAME_TO_ID_PATH, 'r') as f:
    MAPPING_SECTOR_NAME_TO_ID = json.load(f)

# Load Summary Mappings
CATEGORY_SUMMARY_MAPPING_PATH = resources_dir / "category_id_to_summary_mapping.json"
CATEGORY_PROMPTS_PATH = resources_dir / "categories_with_prompt_new.json"

with open(CATEGORY_SUMMARY_MAPPING_PATH, 'r') as f:
    raw_summary_mapping = json.load(f)

# Invert mapping: ID -> Summary Name
CATEGORY_ID_TO_SUMMARY_MAPPING = {}
for summary_name, ids in raw_summary_mapping.items():
    for cat_id in ids:
        CATEGORY_ID_TO_SUMMARY_MAPPING[str(cat_id)] = summary_name

with open(CATEGORY_PROMPTS_PATH, 'r') as f:
    CATEGORY_SUMMARY_INFO = json.load(f)


def semanticSearchCompanyCount(
    es_client,
    query: str,
    start_date: str,
    end_date: str,
    index_name: str,
    companyName: str = "All",
    complaint_numbers: list = ["NA"],
    skip: int = 0,
    limit: int = 10
):
    must_clauses = []
    filter_clauses = []

    # 1️⃣ Date range filter
    if start_date and end_date:
        must_clauses.append({
            "range": {
                "complaintRegDate": {"gte": start_date, "lte": end_date}
            }
        })

    # 2️⃣ Text query on complaint details
    if query and query.strip():
        must_clauses.append({
            "match": {"complaintDetails": query}
        })

    if not must_clauses:
        must_clauses.append({"match_all": {}})

    # 3️⃣ Company filter (exact match on indexed field)
    if companyName != "All":
        filter_clauses.append({"term": {"converganceCompanyName": companyName}})

    # 4️⃣ Complaint numbers filter
    if complaint_numbers and complaint_numbers != ["NA"]:
        filter_clauses.append({
            "terms": {
                "complainNumber": [x.strip() for x in complaint_numbers]
            }
        })

    # ✅ Final ES query
    # Fetch more items to account for potential filtering of "None" or "Unknown"
    fetch_size = skip + limit + 20 
    
    es_query = {
        "size": 0,  # aggregation only
        "query": {
            "bool": {
                "must": must_clauses,
                "filter": filter_clauses
            }
        },
        "aggs": {
            "company_distribution": {
                "terms": {
                    "field": "converganceCompanyId",  # Use ID for aggregation
                    "size": fetch_size,
                    "order": {"_count": "desc"}
                },
                "aggs": {
                    "company_name": {
                        "top_hits": {
                            "size": 1,
                            "_source": ["converganceCompanyName", "categoryCode", "sectorCode"]
                        }
                    }
                }
            }
        }
    }

    response = es_client.search(index=index_name, body=es_query)

    buckets = response["aggregations"]["company_distribution"]["buckets"]

    result = []
    for b in buckets:
        name = "Unknown"
        category_name = "Unknown"
        sector_name = "Unknown"
        
        hits = b.get("company_name", {}).get("hits", {}).get("hits", [])
        if hits:
            source = hits[0]["_source"]
            name = source.get("converganceCompanyName", "Unknown")
            
            # Extract codes
            cat_code = str(source.get("categoryCode", ""))
            sec_code = str(source.get("sectorCode", ""))
            
            # Clean codes (remove decimals if float string)
            if "." in cat_code:
                cat_code = cat_code.split(".")[0]
            if "." in sec_code:
                sec_code = sec_code.split(".")[0]
                
            # Map to names
            category_name = MAPPING_CATEGORY.get(cat_code, "Unknown") or "Unknown"
            sector_name = MAPPING_SECTOR.get(sec_code, "Unknown") or "Unknown"

        if name and str(name).strip().lower() != "none" and str(name).strip().lower() != "unknown":
            result.append({
                "companyName": name, 
                "count": b["doc_count"],
                "categoryName": category_name,
                "sectorName": sector_name
            })

    # Slice the final filtered result for pagination
    return result[skip : skip + limit]



def keywordSearchCompanyCount(
    es_client,
    query: str,
    start_date: str,
    end_date: str,
    index_name: str,
    companyName: str = "All",
    complaint_numbers: list = ["NA"],
    skip: int = 0,
    limit: int = 10
):
    must_clauses = []
    filter_clauses = []

    # 1️⃣ Date range filter
    if start_date and end_date:
        must_clauses.append({
            "range": {
                "complaintRegDate": {"gte": start_date, "lte": end_date}
            }
        })

    # 2️⃣ Keyword search across multiple fields
    if query and query.strip():
        must_clauses.append({
            "multi_match": {
                "query": query,
                "fields": [
                    "complaintDetails^3",
                    "converganceCompanyName^2",
                ],
                "type": "best_fields",
                "operator": "and"
            }
        })

    if not must_clauses:
        must_clauses.append({"match_all": {}})

    # 3️⃣ Company filter (exact match)
    if companyName != "All":
        filter_clauses.append({"term": {"converganceCompanyName": companyName}})

    # 4️⃣ Complaint numbers filter
    if complaint_numbers and complaint_numbers != ["NA"]:
        filter_clauses.append({"terms": {"complainNumber.keyword": complaint_numbers}})

    # ✅ Final ES query
    # Fetch more items to account for potential filtering of "None" or "Unknown"
    fetch_size = skip + limit + 20

    es_query = {
        "size": 0,
        "query": {
            "bool": {
                "must": must_clauses,
                "filter": filter_clauses
            }
        },
        "aggs": {
            "company_distribution": {
                "terms": {
                    "field": "converganceCompanyId",  # Use ID for aggregation
                    "size": fetch_size,
                    "order": {"_count": "desc"}
                },
                "aggs": {
                    "company_name": {
                        "top_hits": {
                            "size": 1,
                            "_source": ["converganceCompanyName", "categoryCode", "sectorCode"]
                        }
                    }
                }
            }
        }
    }

    response = es_client.search(index=index_name, body=es_query)

    buckets = response["aggregations"]["company_distribution"]["buckets"]

    result = []
    for b in buckets:
        name = "Unknown"
        category_name = "Unknown"
        sector_name = "Unknown"

        hits = b.get("company_name", {}).get("hits", {}).get("hits", [])
        if hits:
            source = hits[0]["_source"]
            name = source.get("converganceCompanyName", "Unknown")
            
            # Extract codes
            cat_code = str(source.get("categoryCode", ""))
            sec_code = str(source.get("sectorCode", ""))
            
            # Clean codes (remove decimals if float string)
            if "." in cat_code:
                cat_code = cat_code.split(".")[0]
            if "." in sec_code:
                sec_code = sec_code.split(".")[0]
                
            # Map to names
            category_name = MAPPING_CATEGORY.get(cat_code, "Unknown") or "Unknown"
            sector_name = MAPPING_SECTOR.get(sec_code, "Unknown") or "Unknown"

        if name and str(name).strip().lower() != "none" and str(name).strip().lower() != "unknown":
            result.append({
                "companyName": name, 
                "count": b["doc_count"],
                "categoryName": category_name,
                "sectorName": sector_name
            })

    # Slice the final filtered result for pagination
    return result[skip : skip + limit]


def semanticSearchAlltypeCompanyCount(
    es_client,
    query: str,
    start_date: str,
    end_date: str,
    index_name: str,
    companyName: str = "All",
    complaint_numbers: list = ["NA"],
    skip: int = 0,
    limit: int = 10
):
    must_clauses = []
    filter_clauses = []

    # 1️⃣ Date range filter
    if start_date and end_date:
        must_clauses.append({
            "range": {
                "complaintRegDate": {"gte": start_date, "lte": end_date}
            }
        })

    # 2️⃣ Text query on complaint details
    if query and query.strip():
        must_clauses.append({
            "match": {"complaintDetails": query}
        })

    if not must_clauses:
        must_clauses.append({"match_all": {}})

    # 3️⃣ Company filter (Search in both fields)
    if companyName != "All":
        filter_clauses.append({
            "bool": {
                "should": [
                    {"match_phrase": {"converganceCompanyName": companyName}},
                    {"match_phrase": {"nonCoverganeceCompanyName": companyName}}
                ],
                "minimum_should_match": 1
            }
        })

    # 4️⃣ Complaint numbers filter
    if complaint_numbers and complaint_numbers != ["NA"]:
        filter_clauses.append({
            "terms": {
                "complainNumber": [x.strip() for x in complaint_numbers]
            }
        })

    # ✅ Final ES query
    fetch_size = skip + limit + 20 
    
    es_query = {
        "size": 0,  # aggregation only
        "query": {
            "bool": {
                "must": must_clauses,
                "filter": filter_clauses
            }
        },
        "aggs": {
            "converged_distribution": {
                "filter": {"exists": {"field": "converganceCompanyId"}},
                "aggs": {
                    "companies": {
                        "terms": {
                            "field": "converganceCompanyId", 
                            "size": fetch_size,
                            "order": {"_count": "desc"}
                        },
                        "aggs": {
                             "company_details": {
                                "top_hits": {
                                    "size": 1,
                                    "_source": ["converganceCompanyName", "categoryCode", "sectorCode"]
                                }
                            },
                            "disposed_count": {
                                "filter": {
                                    "terms": {
                                        "companyStatus": ["Resolved", "Disposed", "Closed", "resolved", "disposed off", "closed", "Disposed off"]
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "non_converged_distribution": {
                 "filter": {
                     "bool": {
                        "must": [
                            {"exists": {"field": "nonCoverganeceCompanyCode"}}
                        ],
                        "must_not": [{"exists": {"field": "converganceCompanyId"}}]
                     }
                 },
                 "aggs": {
                    "companies": {
                        "terms": {
                            "script": {
                                "source": """
                                    String name = doc.containsKey('nonCoverganeceCompanyName') && doc['nonCoverganeceCompanyName'].size() != 0 
                                        ? doc['nonCoverganeceCompanyName'].value 
                                        : '';
                                    if (name == null || name.trim().isEmpty()) {
                                        return 'Unknown';
                                    }
                                    return name;
                                """,
                                "lang": "painless"
                            },
                            "size": fetch_size,
                            "order": {"_count": "desc"}
                        },
                        "aggs": {
                             "company_details": {
                                "top_hits": {
                                    "size": 1,
                                    "_source": ["nonCoverganeceCompanyName", "categoryCode", "sectorCode", "nonCoverganeceCompanyCode"]
                                }
                            },
                            "disposed_count": {
                                "filter": {
                                    "terms": {
                                        "companyStatus": ["Resolved", "Disposed", "Closed", "resolved", "disposed off", "closed", "Disposed off"]
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    response = es_client.search(index=index_name, body=es_query)

    converged_buckets = response["aggregations"]["converged_distribution"]["companies"]["buckets"]
    non_converged_buckets = response["aggregations"]["non_converged_distribution"]["companies"]["buckets"]

    converged_result = []
    non_converged_result = []

    # Process Converged Companies
    for b in converged_buckets:
        name = "Unknown"
        category_name = "Unknown"
        sector_name = "Unknown"
        
        hits = b.get("company_details", {}).get("hits", {}).get("hits", [])
        if hits:
            source = hits[0]["_source"]
            name = source.get("converganceCompanyName", "Unknown")
            
            # Extract codes
            cat_code = str(source.get("categoryCode", ""))
            sec_code = str(source.get("sectorCode", ""))
            
            # Clean codes
            if "." in cat_code:
                cat_code = cat_code.split(".")[0]
            if "." in sec_code:
                sec_code = sec_code.split(".")[0]
                
            # Map to names
            category_name = MAPPING_CATEGORY.get(cat_code, "Unknown") or "Unknown"
            sector_name = MAPPING_SECTOR.get(sec_code, "Unknown") or "Unknown"

        # Calculate disposal rate
        total_count = b["doc_count"]
        disposed_count = b.get("disposed_count", {}).get("doc_count", 0)
        disposal_rate = round((disposed_count / total_count * 100), 2) if total_count > 0 else 0.0

        if name and str(name).strip().lower() != "none" and str(name).strip().lower() != "unknown":
            converged_result.append({
                "companyName": name, 
                "count": total_count,
                "disposedCount": disposed_count,
                "disposalRate": disposal_rate,
                "categoryName": category_name,
                "sectorName": sector_name
            })

    # Process Non-Converged Companies
    for b in non_converged_buckets:
        company_name_key = b["key"]  # This is the company name from aggregation
        name = company_name_key if company_name_key != "Unknown" else "Unknown"
        category_name = "Unknown"
        sector_name = "Unknown"
        company_code = "N/A"
        
        hits = b.get("company_details", {}).get("hits", {}).get("hits", [])
        if hits:
            source = hits[0]["_source"]
            
            # Get company code if available
            code_raw = source.get("nonCoverganeceCompanyCode")
            if code_raw is not None and code_raw != 0:
                company_code = str(code_raw)
            
            # Extract codes
            cat_code = str(source.get("categoryCode", ""))
            sec_code = str(source.get("sectorCode", ""))
            
            # Clean codes
            if "." in cat_code:
                cat_code = cat_code.split(".")[0]
            if "." in sec_code:
                sec_code = sec_code.split(".")[0]
                
            # Map to names
            category_name = MAPPING_CATEGORY.get(cat_code, "Unknown") or "Unknown"
            sector_name = MAPPING_SECTOR.get(sec_code, "Unknown") or "Unknown"

        # Calculate disposal rate
        total_count = b["doc_count"]
        disposed_count = b.get("disposed_count", {}).get("doc_count", 0)
        disposal_rate = round((disposed_count / total_count * 100), 2) if total_count > 0 else 0.0

        # Include all companies
        non_converged_result.append({
            "companyName": name, 
            "companyCode": company_code,
            "count": total_count,
            "disposedCount": disposed_count,
            "disposalRate": disposal_rate,
            "categoryName": category_name,
            "sectorName": sector_name
        })

    # Return structured result with pagination
    return {
        "converged": converged_result[skip : skip + limit],
        "non_converged": non_converged_result[skip : skip + limit]
    }


def keywordSearchAlltypeCompanyCount(
    es_client,
    query: str,
    start_date: str,
    end_date: str,
    index_name: str,
    companyName: str = "All",
    complaint_numbers: list = ["NA"],
    skip: int = 0,
    limit: int = 10
):
    must_clauses = []
    filter_clauses = []

    # 1️⃣ Date range filter
    if start_date and end_date:
        must_clauses.append({
            "range": {
                "complaintRegDate": {"gte": start_date, "lte": end_date}
            }
        })

    # 2️⃣ Keyword search
    if query and query.strip():
        must_clauses.append({
            "multi_match": {
                "query": query,
                "fields": [
                    "complaintDetails^3",
                    "converganceCompanyName^2",
                    "nonCoverganeceCompanyName^2"
                ],
                "type": "best_fields",
                "operator": "and"
            }
        })

    if not must_clauses:
        must_clauses.append({"match_all": {}})

    # 3️⃣ Company filter
    if companyName != "All":
        filter_clauses.append({
            "bool": {
                "should": [
                    {"term": {"converganceCompanyName": companyName}},
                    {"term": {"nonCoverganeceCompanyName": companyName}}
                ],
                "minimum_should_match": 1
            }
        })

    # 4️⃣ Complaint numbers filter
    if complaint_numbers and complaint_numbers != ["NA"]:
        filter_clauses.append({"terms": {"complainNumber.keyword": complaint_numbers}})

    # ✅ Final ES query
    fetch_size = skip + limit + 20 
    
    es_query = {
        "size": 0,  # aggregation only
        "query": {
            "bool": {
                "must": must_clauses,
                "filter": filter_clauses
            }
        },
        "aggs": {
            "company_distribution": {
                "terms": {
                    "script": {
                        "source": """
                            if (doc['converganceCompanyId'].size() != 0) {
                                return 'C_' + doc['converganceCompanyId'].value;
                            }
                            if (doc['nonCoverganeceCompanyCode'].size() != 0) {
                                String name = doc.containsKey('nonCoverganeceCompanyName') && doc['nonCoverganeceCompanyName'].size() != 0 
                                    ? doc['nonCoverganeceCompanyName'].value 
                                    : '';
                                if (name == null || name.trim().isEmpty()) {
                                    return 'N_Unknown';
                                }
                                return 'N_' + name;
                            }
                            return 'Unknown';
                        """,
                        "lang": "painless"
                    },
                    "size": fetch_size,
                    "order": {"_count": "desc"}
                },
                "aggs": {
                    "company_details": {
                        "top_hits": {
                            "size": 1,
                            "_source": ["converganceCompanyName", "nonCoverganeceCompanyName", "categoryCode", "sectorCode", "nonCoverganeceCompanyCode"]
                        }
                    },
                    "disposed_count": {
                        "filter": {
                            "terms": {
                                "companyStatus": ["Resolved", "Disposed", "Closed", "resolved", "disposed off", "closed", "Disposed off"]
                            }
                        }
                    }
                }
            }
        }
    }

    response = es_client.search(index=index_name, body=es_query)

    buckets = response["aggregations"]["company_distribution"]["buckets"]

    converged_result = []
    non_converged_result = []
    
    for b in buckets:
        name_key = b["key"]
        
        # Determine if converged or non-converged based on ID prefix
        is_converged = name_key.startswith("C_")
        is_non_converged = name_key.startswith("N_")
        
        name = "Unknown"
        category_name = "Unknown"
        sector_name = "Unknown"
        company_code = "N/A"
        
        hits = b.get("company_details", {}).get("hits", {}).get("hits", [])
        if hits:
            source = hits[0]["_source"]
            
            if is_converged:
                company_name_raw = source.get("converganceCompanyName")
                if company_name_raw and str(company_name_raw).strip():
                    name = company_name_raw
                company_code = name_key.replace("C_", "")  # Extract convergence ID
            elif is_non_converged:
                # Extract name from key (remove N_ prefix)
                extracted_name = name_key.replace("N_", "", 1)
                name = extracted_name if extracted_name != "Unknown" else "Unknown"
                
                # Get company code if available
                code_raw = source.get("nonCoverganeceCompanyCode")
                if code_raw is not None and code_raw != 0:
                    company_code = str(code_raw)

            # Extract codes
            cat_code = str(source.get("categoryCode", ""))
            sec_code = str(source.get("sectorCode", ""))
            
            # Clean codes
            if "." in cat_code:
                cat_code = cat_code.split(".")[0]
            if "." in sec_code:
                sec_code = sec_code.split(".")[0]
                
            # Map to names
            category_name = MAPPING_CATEGORY.get(cat_code, "Unknown") or "Unknown"
            sector_name = MAPPING_SECTOR.get(sec_code, "Unknown") or "Unknown"

        # Calculate disposal rate
        total_count = b["doc_count"]
        disposed_count = b.get("disposed_count", {}).get("doc_count", 0)
        disposal_rate = round((disposed_count / total_count * 100), 2) if total_count > 0 else 0.0

        # Include all companies
        item = {
            "companyName": name, 
            "companyCode": company_code,
            "count": total_count,
            "disposedCount": disposed_count,
            "disposalRate": disposal_rate,
            "categoryName": category_name,
            "sectorName": sector_name
        }
        if is_converged:
            converged_result.append(item)
        else:
            non_converged_result.append(item)

    # Return structured result with pagination
    return {
        "converged": converged_result[skip : skip + limit],
        "non_converged": non_converged_result[skip : skip + limit]
    }



def getComplaintDistributionES(
    attribute,
    start_date,
    end_date,
    stateName="All",
    sectorName="All",
    categoryName="All",
    skip=0,
    limit=20
):
    """
    ES-based distribution for ONLY:
      - stateName
      - categoryName
    """

    if attribute not in ["stateName", "categoryName"]:
        return {"error": "Only 'stateName' and 'categoryName' are supported in ES version."}

    try:
        es_client = getES()
        index_name = config["ES"]["INDEX_NAME"]

        FIELD_MAPPING = {
            "stateName": "stateCode",
            "categoryName": "categoryCode"
        }

        es_field = FIELD_MAPPING[attribute]

        must_filters = []

        # -------- Filters --------
        if stateName != "All":
            if stateName in MAPPING_STATE_NAME_TO_ID:
                must_filters.append({
                    "term": {"stateCode": MAPPING_STATE_NAME_TO_ID[stateName]}
                })
            else:
                return {"error": f"Invalid state name: {stateName}"}

        if sectorName != "All":
            if sectorName in MAPPING_SECTOR_NAME_TO_ID:
                must_filters.append({
                    "term": {"sectorCode": MAPPING_SECTOR_NAME_TO_ID[sectorName]}
                })
            else:
                return {"error": f"Invalid sector name: {sectorName}"}

        if categoryName != "All":
            if categoryName in MAPPING_CATEGORY_NAME_TO_ID:
                must_filters.append({
                    "term": {"categoryCode": MAPPING_CATEGORY_NAME_TO_ID[categoryName]}
                })
            else:
                return {"error": f"Invalid category name: {categoryName}"}

        if start_date and end_date:
            must_filters.append({
                "range": {
                    "complaintRegDate": {
                        "gte": start_date,
                        "lte": end_date
                    }
                }
            })

        # -------- Aggregation --------
        fetch_all = (attribute == "categoryName")
        size_for_terms = 10_000 if fetch_all else skip + limit

        body = {
            "size": 0,
            "query": {
                "bool": {
                    "filter": must_filters
                }
            },
            "aggs": {
                "distribution": {
                    "terms": {
                        "field": es_field,
                        "size": size_for_terms,
                        "order": {"_count": "desc"}
                    }
                }
            }
        }

        resp = es_client.search(index=index_name, body=body)
        buckets = resp["aggregations"]["distribution"]["buckets"]

        # -------- categoryName special handling --------
        if attribute == "categoryName":
            summary_results = {}

            for b in buckets:
                category_code = str(b["key"])
                count = int(b["doc_count"])

                summary_category = CATEGORY_ID_TO_SUMMARY_MAPPING.get(
                    category_code,
                    MAPPING_CATEGORY.get(category_code, "Others")
                )

                if summary_category in summary_results:
                    summary_results[summary_category]["count"] += count
                else:
                    category_info = CATEGORY_SUMMARY_INFO.get(summary_category, {})
                    category_prompt = category_info.get("categoryPrompt", "")

                    summary_results[summary_category] = {
                        "category": summary_category,
                        "count": count,
                        "categoryPrompt": category_prompt
                    }

            result = sorted(
                summary_results.values(),
                key=lambda x: x["count"],
                reverse=True
            )

            result = result[skip: skip + limit]

        # -------- stateName handling --------
        else:  # stateName
            result = []
            for b in buckets[skip: skip + limit]:
                state_code = str(b["key"])
                count = int(b["doc_count"])

                state_label = MAPPING_STATE.get(state_code, "Unknown")

                result.append({
                    "attribute_value": state_label,
                    "count": count
                })

        es_client.close()
        return {"distribution": result}

    except Exception as e:
        print(f"[ERROR] ES getComplaintDistribution: {e}")
        return {"error": f"Failed to get complaint distribution: {e}"}


# ===================== NEW FUNCTION FOR MERGED API =====================

def call_gpt_api(prompt: str) -> str:
    """Call OpenAI GPT API"""
    
    api_key = config.get("OPENAI_API_KEY", "")
    if not api_key:
        print("Error: OPENAI_API_KEY not found in config")
        return "ERROR_LABEL"
    
    client = OpenAI(api_key=api_key)
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
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


# Global cache for GPT responses (simple in-memory cache)
_GPT_CACHE = {}

def getSubcategoryWithCounts(
    input_prompt: str,
    value: int,
    start_date: str,
    end_date: str,
    threshold: float,
    CityName: str,
    stateName: str,
    complaintType: str,
    complaintMode: str,
    companyName: str,
    complaintStatus: str,
    complaint_numbers: list,
    max_retries: int,
    max_subcategories: int = 15,
    max_workers: int = 10,
    enable_cache: bool = True,
    es_client = None,
    embed_model = None,
    index_name: str = None
):
    """
    Merged function: Generate subcategories using GPT and fetch counts + complaint numbers for each.
    
    OPTIMIZATIONS APPLIED:
    1. ✅ Parallel processing of subcategories (ThreadPoolExecutor)
    2. ✅ Caching of GPT responses
    3. ✅ Configurable limits (max_subcategories, max_workers)
    
    Steps:
    1. Call GPT to generate subcategories with prompts from input_prompt (with caching)
    2. For each subcategory, call semantic/keyword RCA IN PARALLEL
    3. Return combined results sorted by count
    """
    from repository.semantic_search import semanticSearchBasic
    from repository.keyword_search import keywordSearchBasic
    import hashlib
    
    # Step 1: Generate subcategories using GPT (with caching)
    cache_key = None
    if enable_cache:
        # Create a hash of the input prompt for caching
        cache_key = hashlib.md5(input_prompt.encode()).hexdigest()
        if cache_key in _GPT_CACHE:
            print(f"✓ Using cached GPT response for prompt hash: {cache_key[:8]}...")
            subcategories_json = _GPT_CACHE[cache_key]
        else:
            subcategories_json = None
    else:
        subcategories_json = None
    
    # Generate if not cached or cache disabled
    if subcategories_json is None:
        llm_prompt_template = f"""You are an expert text analyst and a prompt engineering assistant. Your task is to analyze the provided 'Input Text' and identify all distinct critical subcategories, along with their associated keywords and examples. For each identified subcategory, you must then formulate a *concise and effective search prompt* that specifically targets grievances related to that subcategory, incorporating its keywords and examples.

The output must be a valid JSON object. The keys of this JSON object should be the names of the identified subcategories. The value for each subcategory key should be an object containing a single key: 'prompt', whose value is the newly generated search prompt for that subcategory.

**Input Text:**
\"\"\"
{input_prompt}
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
        
        subcategories_json = {}
        
        # Try to get valid JSON from GPT with retries
        for attempt in range(max_retries):
            print(f"Attempt {attempt + 1}/{max_retries} to get JSON from GPT...")
            try:
                generated_content = call_gpt_api(prompt=llm_prompt_template)
                
                # Try to parse the generated content as JSON
                try:
                    generated_content = clean_json_response(generated_content)
                    subcategories_json = json.loads(generated_content)
                    print(f"Successfully received and parsed JSON with {len(subcategories_json)} subcategories.")
                    
                    # Cache the result if caching is enabled
                    if enable_cache and cache_key:
                        _GPT_CACHE[cache_key] = subcategories_json
                        print(f"✓ Cached GPT response with key: {cache_key[:8]}...")
                    
                    break  # Success! Break the retry loop
                except json.JSONDecodeError as e:
                    print(f"Warning: GPT did not return valid JSON on attempt {attempt + 1}. Error: {e}")
                    # If neither direct nor markdown block parsing works, continue to next retry
                    
            except Exception as e:
                print(f"An unexpected error occurred on attempt {attempt + 1}: {e}")
        
        # If we couldn't get valid JSON after all retries, return empty result
        if not subcategories_json:
            print(f"Max retries ({max_retries}) reached. Could not obtain valid JSON from GPT.")
            return []
    
    # Limit number of subcategories if needed
    if len(subcategories_json) > max_subcategories:
        print(f"⚠ Limiting subcategories from {len(subcategories_json)} to {max_subcategories}")
        # Take first max_subcategories items
        subcategories_json = dict(list(subcategories_json.items())[:max_subcategories])
    
    # Step 2: For each subcategory, call semantic/keyword RCA IN PARALLEL
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    def process_single_subcategory(subcategory_name, subcategory_data):
        """Process a single subcategory - designed for parallel execution"""
        prompt = subcategory_data.get("prompt", "")
        
        if not prompt:
            print(f"Skipping subcategory '{subcategory_name}' - no prompt found")
            return None
        
        print(f"Processing subcategory: {subcategory_name}")
        
        try:
            # Call semantic or keyword search based on value
            if value == 1:  # Semantic search
                rca_result = semanticSearchBasic(
                    es_client=es_client,
                    query=prompt,
                    start_date=start_date,
                    end_date=end_date,
                    embed_model=embed_model,
                    index_name=index_name,
                    CityName=CityName,
                    stateName=stateName,
                    complaintType=complaintType,
                    complaintMode=complaintMode,
                    companyName=companyName,
                    complaintStatus=complaintStatus,
                    threshold=threshold,
                    complaint_numbers=complaint_numbers
                )
            elif value == 2:  # Keyword search
                rca_result = keywordSearchBasic(
                    es_client=es_client,
                    query=prompt,
                    start_date=start_date,
                    end_date=end_date,
                    index_name=index_name,
                    CityName=CityName,
                    stateName=stateName,
                    complaintType=complaintType,
                    complaintMode=complaintMode,
                    companyName=companyName,
                    complaintStatus=complaintStatus,
                    complaint_numbers=complaint_numbers
                )
            else:
                print(f"Invalid search value: {value}. Skipping subcategory '{subcategory_name}'")
                return None
            
            # Combine the results
            result = {
                "subcategory": subcategory_name,
                "prompt": prompt,
                "count": rca_result.get("total_counts", 0),
                "complaintNumbers": rca_result.get("complaintNumbers", [])
            }
            
            print(f"Subcategory '{subcategory_name}': Found {rca_result.get('total_counts', 0)} complaints")
            return result
            
        except Exception as e:
            print(f"Error processing subcategory '{subcategory_name}': {e}")
            # Still add the subcategory but with zero counts
            return {
                "subcategory": subcategory_name,
                "prompt": prompt,
                "count": 0,
                "complaintNumbers": [],
                "error": str(e)
            }
    
    # Use ThreadPoolExecutor for parallel processing
    results = []
    workers = min(max_workers, len(subcategories_json))  # Use configured max_workers
    
    print(f"Processing {len(subcategories_json)} subcategories in parallel with {workers} workers...")
    
    with ThreadPoolExecutor(max_workers=workers) as executor:
        # Submit all tasks
        future_to_subcategory = {
            executor.submit(process_single_subcategory, name, data): name
            for name, data in subcategories_json.items()
        }
        
        # Collect results as they complete
        for future in as_completed(future_to_subcategory):
            subcategory_name = future_to_subcategory[future]
            try:
                result = future.result()
                if result is not None:
                    results.append(result)
            except Exception as e:
                print(f"Exception occurred for subcategory '{subcategory_name}': {e}")
                results.append({
                    "subcategory": subcategory_name,
                    "prompt": "",
                    "count": 0,
                    "complaintNumbers": [],
                    "error": str(e)
                })
    
    # Sort results by count (descending)
    results.sort(key=lambda x: x["count"], reverse=True)
    
    return results
