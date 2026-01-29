import json
import pandas as pd
from fastapi import HTTPException
from elasticsearch import Elasticsearch
from repository.basicdetails import process_grievance_data
from datetime import datetime
from sqlalchemy.orm import Session




def semanticSearch(
    es_client,
    query: str,
    start_date: str,
    end_date: str,
    embed_model,
    skip: int,
    size: int,
    index_name: str,
    CityName: str = "All",
    stateName: str = "All",
    complaintType: str = "All",
    complaintMode: str = "All",
    companyName: str = "All",
    complaintStatus: str = "All",
    threshold: float = 0.5,
    complaint_numbers: list = ["NA"]
) -> list:
    """
    Perform semantic search in Elasticsearch using vector embeddings.

    Parameters
    ----------
    es_client : Elasticsearch
        Instance of Elasticsearch client.
    query : str
        User query string.
    embed_model : Any
        Embedding model 
    skip : int
        Number of records to skip (for pagination).
    size : int
        Number of records to retrieve.
    index_name : str
        Name of the Elasticsearch index.
    threshold : float, optional
        Minimum score threshold for search results, by default 0.5.

    Returns
    -------
    list
        List containing total hits and document IDs (processed).
    """

    # Encode the query to get the vector representation
    query_vector = embed_model.encode([query], show_progress_bar=False, convert_to_numpy=True)[0].tolist()

    search_body = {
        "from": skip,
        "size": size,
        "min_score": threshold,
        "query": {
            "script_score": {
                "query": {
                    "bool": {
                        "filter": [
                            {"range": {"complaintRegDate": {"gte": start_date, "lte": end_date}}}
                        ],
                        "must": []  # Initialize must array for additional filters
                    }
                },
                "script": {
                    "source": "cosineSimilarity(params.query_vector, 'complaintDetails_vector') + 1.0",
                    "params": {"query_vector": query_vector}
                }
            }
        }
    }

    # # Add filters conditionally
    # if CityName != "All":
    #     search_body["query"]["script_score"]["query"]["bool"]["must"].append({
    #         "term": {"cityName": CityName}
    #     })

    # location filter
    if stateName != "All":
        search_body["query"]["script_score"]["query"]["bool"]["must"].append({
            "term": {"stateName": stateName}
        })

        if CityName != "All":
            # Ensure cityName is within the specified stateName
            search_body["query"]["script_score"]["query"]["bool"]["must"].append({
                "term": {"stateName": stateName}
            })

    if complaintType != "All":
        search_body["query"]["script_score"]["query"]["bool"]["must"].append({
            "term": {"complaintType": complaintType}
        })

    if complaintMode != "All":
        search_body["query"]["script_score"]["query"]["bool"]["must"].append({
            "term": {"complaintMode": complaintMode}
        })

    if companyName != "All":
        search_body["query"]["script_score"]["query"]["bool"]["must"].append({
            "multi_match": {
                "query": companyName,
                "fields": ["converganceCompanyName", "nonCoverganeceCompanyName"]
            }
        })

    if complaintStatus != "All":
        search_body["query"]["script_score"]["query"]["bool"]["must"].append({
            "term": {"complaintStatus": complaintStatus}
        })

    if complaint_numbers != ["NA"]:
        formatted_ids = [num.replace("/", "_") for num in complaint_numbers]
        search_body["query"]["script_score"]["query"]["bool"]["must"].append({
            "ids": {"values": formatted_ids}
        })

    try:
        response = es_client.search(index=index_name, body=search_body, request_timeout=600)
    except Exception as e:
        print(f"Error during search: {e}")
        return []

    with open("semantic_search_debug.txt", "w") as debug_file:
        debug_file.write(json.dumps(search_body, indent=2))
        debug_file.write("\n\n")
        # Write the response to the debug file not as a json
        debug_file.write(str(response))

    # Process results
    total_hits = str(response.get('hits', {}).get('total', {}).get('value', 0))
    results = []
    for hit in response.get('hits', {}).get('hits', []):
        result = {
            "id": hit['_id'].replace("_", "/"),
            "complaintDetails": hit['_source'].get('complaintDetails', ''),
            "userId": hit['_source'].get('userId', ''),
            "stateCode": hit['_source'].get('stateCode', ''),
            "complaintType": hit['_source'].get('complaintType', ''),
            "complaintMode": hit['_source'].get('complaintMode', ''),
            "categoryCode": hit['_source'].get('categoryCode', ''),
            "companyName": hit['_source'].get('converganceCompanyName', '') or hit['_source'].get('nonCoverganeceCompanyName', ''),
            "complaintStatus": hit['_source'].get('complaintStatus', ''),
            "companyStatus": hit['_source'].get('companyStatus', ''),
            "complaintRegDate": hit['_source'].get('complaintRegDate', ''),
            "lastUpdationDate": hit['_source'].get('lastUpdationDate', '')
        }
        results.append(result)

    print(f"Semantic search found {total_hits} hits.")
    
    with open("semantic_search_results_debug.txt", "w") as results_file:
        results_file.write(json.dumps(results, indent=2))

    grievanceData=results
    updated_grievanceData=process_grievance_data(grievanceData)
    print(f"After processing, {len(updated_grievanceData)} records found.")

    return updated_grievanceData



def semanticSearchCount(
    es_client,
    query: str,
    start_date: str,
    end_date: str,
    embed_model,
    index_name: str,
    CityName: str = "All",
    stateName: str = "All",
    complaintType: str = "All",
    complaintMode: str = "All",
    companyName: str = "All",
    complaintStatus: str = "All",
    threshold: float = 0.5,
    complaint_numbers: list = ["NA"]
):
    """
    Perform semantic search count in Elasticsearch
    """
    search_type = 'complaintDetails_vector'
    query_vector = embed_model.encode([query], show_progress_bar=False, convert_to_numpy=True)[0].tolist()

    # Construct the search query
    search_query = {
        "size": 0,
        "track_total_hits": True,
        "min_score": threshold,
        "query": {
            "script_score": {
                "query": {
                    "bool": {
                        "must": [
                            {"exists": {"field": search_type}},
                            {"range": {"complaintRegDate": {"gte": start_date, "lte": end_date}}}
                        ]
                    }
                },
                "script": {
                    "source": f"cosineSimilarity(params.query_vector, '{search_type}') + 1.0",
                    "params": {"query_vector": query_vector}
                }
            }
        }
    }

    # Add filters conditionally
    if CityName != "All":
        search_query["query"]["script_score"]["query"]["bool"]["must"].append({
            "term": {"cityName": CityName}
        })

    if stateName != "All":
        search_query["query"]["script_score"]["query"]["bool"]["must"].append({
            "term": {"stateName": stateName}
        })

    if complaintType != "All":
        search_query["query"]["script_score"]["query"]["bool"]["must"].append({
            "term": {"complaintType": complaintType}
        })

    if complaintMode != "All":
        search_query["query"]["script_score"]["query"]["bool"]["must"].append({
            "term": {"complaintMode": complaintMode}
        })

    if companyName != "All":
        search_query["query"]["script_score"]["query"]["bool"]["must"].append({
            "multi_match": {
                "query": companyName,
                "fields": ["converganceCompanyName", "nonCoverganeceCompanyName"]
            }
        })

    if complaintStatus != "All":
        search_query["query"]["script_score"]["query"]["bool"]["must"].append({
            "term": {"complaintStatus": complaintStatus}
        })

    if complaint_numbers != ["NA"]:
        formatted_ids = [num.replace("/", "_") for num in complaint_numbers]
        search_query["query"]["script_score"]["query"]["bool"]["must"].append({
            "ids": {"values": formatted_ids}
        })

    with open("semantic_search_count_debug.txt", "w") as debug_file:
        debug_file.write(json.dumps(search_query, indent=2))

    try:
        response = es_client.search(
            index=index_name, 
            body=search_query,
            request_timeout=600
        )
        return {"total_count":response["hits"]["total"]["value"]}
    except Exception as e:
        print(f"Error during search count: {e}")
        return 0

def semanticSearchCompanyCount(
    es_client,
    query: str,
    start_date: str,
    end_date: str,
    index_name: str,
    companyName: str = "All",
    complaint_numbers: list = ["NA"]
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
        filter_clauses.append({"terms": {"complainNumber.keyword": complaint_numbers}})

    # ✅ Final ES query
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
                    "field": "converganceCompanyName",  # indexed keyword field
                    "size": 10,
                    "order": {"_count": "desc"}
                }
            }
        }
    }

    response = es_client.search(index=index_name, body=es_query)

    buckets = response["aggregations"]["company_distribution"]["buckets"]

    result = [
        {"companyName": b["key"], "count": b["doc_count"]}
        for b in buckets
        if b["key"] and str(b["key"]).strip().lower() != "none"
    ]

    return result


def keywordSearchCompanyCount(
    es_client,
    query: str,
    start_date: str,
    end_date: str,
    index_name: str,
    companyName: str = "All",
    complaint_numbers: list = ["NA"]
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
                    "field": "converganceCompanyName",  # indexed keyword field
                    "size": 10,
                    "order": {"_count": "desc"}
                }
            }
        }
    }

    response = es_client.search(index=index_name, body=es_query)

    buckets = response["aggregations"]["company_distribution"]["buckets"]

    result = [
        {"companyName": b["key"], "count": b["doc_count"]}
        for b in buckets
        if b["key"] and str(b["key"]).strip().lower() != "none"
    ]

    return result


def semanticSearchByComplaintNumbers(
    es_client,
    query: str,
    start_date: str,
    end_date: str,
    embed_model,
    skip: int,
    size: int,
    index_name: str,
    CityName: str = "All",
    stateName: str = "All",
    complaintType: str = "All",
    complaintMode: str = "All",
    companyName: str = "All",
    complaintStatus: str = "All",
    threshold: float = 0.5,
    complaint_numbers: list = ["NA"]
) -> dict:
    """
    Perform semantic search within specific complaint numbers in Elasticsearch.
    """
    search_type = 'complaintDetails_vector'
    query_vector = embed_model.encode([query], show_progress_bar=False, convert_to_numpy=True)[0].tolist()
    
    # Construct the search query
    search_body = {
        "from": skip,
        "size": size,
        "min_score": threshold,
        "track_total_hits": True,
        "query": {
            "script_score": {
                "query": {
                    "bool": {
                        "must": [
                            {"exists": {"field": search_type}},
                            {"range": {"complaintRegDate": {"gte": start_date, "lte": end_date}}}
                        ]
                    }
                },
                "script": {
                    "source": f"cosineSimilarity(params.query_vector, '{search_type}') + 1.0",
                    "params": {"query_vector": query_vector}
                }
            }
        }
    }

    # Add complaint numbers filter if provided
    if complaint_numbers != ["NA"]:
        formatted_ids = [num.replace("/", "_") for num in complaint_numbers]
        search_body["query"]["script_score"]["query"]["bool"]["must"].append({
            "ids": {"values": formatted_ids}
        })

    # Add filters conditionally
    if CityName != "All":
        search_body["query"]["script_score"]["query"]["bool"]["must"].append({
            "term": {"cityName": CityName}
        })

    if stateName != "All":
        search_body["query"]["script_score"]["query"]["bool"]["must"].append({
            "term": {"stateName": stateName}
        })

    if complaintType != "All":
        search_body["query"]["script_score"]["query"]["bool"]["must"].append({
            "term": {"complaintType": complaintType}
        })

    if complaintMode != "All":
        search_body["query"]["script_score"]["query"]["bool"]["must"].append({
            "term": {"complaintMode": complaintMode}
        })

    if companyName != "All":
        search_body["query"]["script_score"]["query"]["bool"]["must"].append({
            "multi_match": {
                "query": companyName,
                "fields": ["converganceCompanyName", "nonCoverganeceCompanyName"]
            }
        })

    if complaintStatus != "All":
        search_body["query"]["script_score"]["query"]["bool"]["must"].append({
            "term": {"complaintStatus": complaintStatus}
        })

    try:
        response = es_client.search(
            index=index_name,
            body=search_body,
            request_timeout=600
        )
    except Exception as e:
        print(f"Error during search: {e}")
        return {"total_count": 0, "grievanceData": []}

    # Process results
    total_hits = response.get('hits', {}).get('total', {}).get('value', 0)
    results = []
    for hit in response.get('hits', {}).get('hits', []):
        result = {
            "id": hit['_id'].replace("_", "/"),
            "complaintDetails": hit['_source'].get('complaintDetails', ''),
            "userId": hit['_source'].get('userId', ''),
            "stateCode": hit['_source'].get('stateCode', ''),
            "complaintType": hit['_source'].get('complaintType', ''),
            "complaintMode": hit['_source'].get('complaintMode', ''),
            "categoryCode": hit['_source'].get('categoryCode', ''),
            "companyName": hit['_source'].get('converganceCompanyName', '') or hit['_source'].get('nonCoverganeceCompanyName', ''),
            "complaintStatus": hit['_source'].get('complaintStatus', ''),
            "companyStatus": hit['_source'].get('companyStatus', ''),
            "complaintRegDate": hit['_source'].get('complaintRegDate', ''),
            "lastUpdationDate": hit['_source'].get('lastUpdationDate', '')
        }
        results.append(result)

    grievanceData = process_grievance_data(results)
    
    print(f"Semantic search found {total_hits} hits within {len(complaint_numbers)} complaint numbers.")
    print(f"After processing, {len(grievanceData)} records found.")
    
    return {
        "total_count": total_hits,
        "grievanceData": grievanceData
    }


def semanticSearchBasic(
    es_client,
    query: str,
    start_date: str,
    end_date: str,
    embed_model,
    index_name: str,
    CityName: str = "All",
    stateName: str = "All",
    complaintType: str = "All",
    complaintMode: str = "All",
    companyName: str = "All",
    complaintStatus: str = "All",
    threshold: float = 0.5,
    complaint_numbers: list = ["NA"]
) -> dict:
    """
    Perform semantic search and return only counts and registration numbers.
    
    Returns
    -------
    dict
        Dictionary containing total_counts and list of registration numbers
    """ 
    print("Starting basic semantic search...", query)
    
    query_vector = embed_model.encode([query], show_progress_bar=False, convert_to_numpy=True)[0].tolist()

    search_body = {
        "size": 10000,  # Adjust based on your needs
        "_source": ["_id"],  # Only fetch IDs
        "track_total_hits": True,
        "min_score": threshold,
        "query": {
            "script_score": {
                "query": {
                    "bool": {
                        "must": [
                            {"range": {"complaintRegDate": {"gte": start_date, "lte": end_date}}}
                        ]
                    }
                },
                "script": {
                    "source": "cosineSimilarity(params.query_vector, 'complaintDetails_vector') + 1.0",
                    "params": {"query_vector": query_vector}
                }
            }
        }
    }

    # Add complaint numbers filter if provided
    if complaint_numbers != ["NA"]:
        formatted_ids = [num.replace("/", "_") for num in complaint_numbers]
        search_body["query"]["script_score"]["query"]["bool"]["must"].append({
            "ids": {"values": formatted_ids}
        })


    # Add filters conditionally
    if CityName != "All":
        search_body["query"]["script_score"]["query"]["bool"]["must"].append({
            "term": {"cityName": CityName}
        })

    if stateName != "All":
        search_body["query"]["script_score"]["query"]["bool"]["must"].append({
            "term": {"stateName": stateName}
        })

    if complaintType != "All":
        search_body["query"]["script_score"]["query"]["bool"]["must"].append({
            "term": {"complaintType": complaintType}
        })

    if complaintMode != "All":
        search_body["query"]["script_score"]["query"]["bool"]["must"].append({
            "term": {"complaintMode": complaintMode}
        })

    if companyName != "All":
        search_body["query"]["script_score"]["query"]["bool"]["must"].append({
            "multi_match": {
                "query": companyName,
                "fields": ["converganceCompanyName", "nonCoverganeceCompanyName"]
            }
        })

    if complaintStatus != "All":
        search_body["query"]["script_score"]["query"]["bool"]["must"].append({
            "term": {"complaintStatus": complaintStatus}
        })

    try:
        response = es_client.search(
            index=index_name,
            body=search_body,
            request_timeout=600
        )
        
        total_hits = response["hits"]["total"]["value"]
        complaintNumbers = [hit["_id"].replace("_", "/") for hit in response["hits"]["hits"]]
        
        return {
            "total_counts": total_hits,
            "complaintNumbers": complaintNumbers
        }
    
    except Exception as e:
        print(f"Error during search: {e}")
        return {
            "total_counts": 0,
            "complaintNumbers": []
        }
    


# es_client,
#         start_date,
#         end_date,
#         embed_model,
#         INDEX_NAME,
#         CityName,
#         stateName,
#         complaintType,
#         complaintMode,
#         companyName,
#         complaintStatus,
#         threshold,
#         complaint_numbers

def semanticSearchSpatialAnalysis(
    es_client,
    query: str,
    start_date: str,
    end_date: str,
    embed_model,
    index_name: str,
    CityName: str = "All",
    stateName: str = "All",
    complaintType: str = "All",
    complaintMode: str = "All",
    companyName: str = "All",
    complaintStatus: str = "All",
    threshold: float = 0.5,
    complaint_numbers: list = ["NA"]
) -> dict:
    """
    Perform semantic search and return state-wise distribution of results.
    
    Returns
    -------
    dict
        Dictionary containing state codes and their complaint counts
    """

    print("Starting spatial analysis semantic search...", query)
    query_vector = embed_model.encode([query], show_progress_bar=False, convert_to_numpy=True)[0].tolist()
    
    search_body = {
        "size": 0,  # We only need aggregations
        "track_total_hits": True,
        "min_score": threshold,
        "query": {
            "script_score": {
                "query": {
                    "bool": {
                        "must": [
                            {"range": {"complaintRegDate": {"gte": start_date, "lte": end_date}}}
                        ]
                    }
                },
                "script": {
                    "source": "cosineSimilarity(params.query_vector, 'complaintDetails_vector') + 1.0",
                    "params": {"query_vector": query_vector}
                }
            }
        },
        "aggs": {
            "state_distribution": {
                "terms": {
                    "field": "stateCode",
                    "size": 50  # Adjust if you have more states
                }
            }
        }
    }

    # Add complaint numbers filter if provided
    if complaint_numbers != ["NA"]:
        formatted_ids = [num.replace("/", "_") for num in complaint_numbers]
        search_body["query"]["script_score"]["query"]["bool"]["must"].append({
            "ids": {"values": formatted_ids}
        })


    # Add filters conditionally
    if CityName != "All":
        search_body["query"]["script_score"]["query"]["bool"]["must"].append({
            "term": {"cityName": CityName}
        })

    if stateName != "All":
        search_body["query"]["script_score"]["query"]["bool"]["must"].append({
            "term": {"stateName": stateName}
        })

    if complaintType != "All":
        search_body["query"]["script_score"]["query"]["bool"]["must"].append({
            "term": {"complaintType": complaintType}
        })

    if complaintMode != "All":
        search_body["query"]["script_score"]["query"]["bool"]["must"].append({
            "term": {"complaintMode": complaintMode}
        })

    if companyName != "All":
        search_body["query"]["script_score"]["query"]["bool"]["must"].append({
            "multi_match": {
                "query": companyName,
                "fields": ["converganceCompanyName", "nonCoverganeceCompanyName"]
            }
        })

    if complaintStatus != "All":
        search_body["query"]["script_score"]["query"]["bool"]["must"].append({
            "term": {"complaintStatus": complaintStatus}
        })

    try:
        response = es_client.search(
            index=index_name,
            body=search_body,
            request_timeout=600
        )
        
        # Process aggregation results
        state_distribution = {}
        for bucket in response["aggregations"]["state_distribution"]["buckets"]:
            state_distribution[bucket["key"]] = bucket["doc_count"]
            
        return state_distribution
    
    except Exception as e:
        print(f"Error during spatial analysis: {e}")
        return {}
    
# get the complaint details according to the complaint numbers only just accept the complaint numbers list and return the details data will be fetch from es and match _id with complaint numbers

def getcomplaintDetails(complaint_number: list, es_client, index_name: str,) -> dict:
    """
    Fetch complaint details from Elasticsearch based on provided list of complaint numbers.
    """

    try:
        formatted_ids = [num.replace("/", "_") for num in complaint_number]

        search_body = {
            "query": {
                "ids": {
                    "values": formatted_ids
                }
            }
        }

        response = es_client.search(
            index=index_name,
            body=search_body,
            request_timeout=600
        )

        results = []
        for hit in response.get('hits', {}).get('hits', []):
            result = {
                "id": hit['_id'].replace("_", "/"),
                "complaintDetails": hit['_source'].get('complaintDetails', ''),
                "userId": hit['_source'].get('userId', ''),
                "stateCode": hit['_source'].get('stateCode', ''),
                "complaintType": hit['_source'].get('complaintType', ''),
                "complaintMode": hit['_source'].get('complaintMode', ''),
                "categoryCode": hit['_source'].get('categoryCode', ''),
                "companyName": hit['_source'].get('converganceCompanyName', '') or hit['_source'].get('nonCoverganeceCompanyName', ''),
                "complaintStatus": hit['_source'].get('complaintStatus', ''),
                "companyStatus": hit['_source'].get('companyStatus', ''),
                "complaintRegDate": hit['_source'].get('complaintRegDate', ''),
                "lastUpdationDate": hit['_source'].get('lastUpdationDate', '')
            }
            results.append(result)

        return {"complaintDetails": results}
    except Exception as e:
        print(f"Error fetching complaint details: {e}")
        return {"error": str(e)}


