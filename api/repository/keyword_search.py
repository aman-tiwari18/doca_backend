from repository.basicdetails import process_grievance_data
import json

def keywordSearch(
    es_client,
    query: str,
    start_date: str,
    end_date: str,
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
    Perform keyword search in Elasticsearch using BM25.
    """
    # Separate quoted and non-quoted terms
    print("Executing keyword search with parameters:")
    parts = query.split('"')
    quoted_parts = [part.strip() for idx, part in enumerate(parts) if idx % 2 == 1 and part.strip()]
    non_quoted_parts = [part.strip() for idx, part in enumerate(parts) if idx % 2 == 0 and part.strip()]

    # Build the query body
    query_body = {
        "from": skip,
        "size": size,
        "track_total_hits": True,
        "query": {
            "bool": {
                "must": [
                    {"range": {"complaintRegDate": {"gte": start_date, "lte": end_date}}}
                ]
            }
        }
    }

    # Add text search conditions
    bool_condition = {"bool": {}}
    if quoted_parts:
        bool_condition['bool']['must'] = [
            {"match_phrase": {"complaintDetails": part}} for part in quoted_parts
        ]
    if non_quoted_parts:
        bool_condition['bool']['should'] = [
            {"match": {"complaintDetails": {"query": " ".join(non_quoted_parts), "operator": "OR"}}}
        ]
    if bool_condition['bool']:
        query_body['query']['bool']['must'].append(bool_condition)

    # Add filters conditionally
    if CityName != "All":
        query_body["query"]["bool"]["must"].append({
            "term": {"cityName": CityName}
        })

    if stateName != "All":
        query_body["query"]["bool"]["must"].append({
            "term": {"stateName": stateName}
        })

    if complaintType != "All":
        query_body["query"]["bool"]["must"].append({
            "term": {"complaintType": complaintType}
        })

    if complaintMode != "All":
        query_body["query"]["bool"]["must"].append({
            "term": {"complaintMode": complaintMode}
        })

    if companyName != "All":
        query_body["query"]["bool"]["must"].append({
            "multi_match": {
                "query": companyName,
                "fields": ["converganceCompanyName", "nonCoverganeceCompanyName"]
            }
        })

    if complaintStatus != "All":
        query_body["query"]["bool"]["must"].append({
            "term": {"complaintStatus": complaintStatus}
        })

    if complaint_numbers != ["NA"]:
        formatted_ids = [num.replace("/", "_") for num in complaint_numbers]
        query_body["query"]["bool"]["must"].append({
            "ids": {"values": formatted_ids}
        })

    try:
        response = es_client.search(
            index=index_name,
            body=query_body,
            request_timeout=600
        )
    except Exception as e:
        print(f"Error during search: {e}")
        return {"total_count": 0, "grievanceData": []}

    # Process results
    # total_hits = response.get('hits', {}).get('total', {}).get('value', 0)
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
            "lastUpdationDate": hit['_source'].get('lastUpdationDate', ''),
            "score": hit.get('_score', 0)
        }
        results.append(result)


    with open("keyword_search_debug.txt", "w") as debug_file:
        debug_file.write(json.dumps(query_body, indent=2))
        debug_file.write("\n\n")
        # Write the response to the debug file not as a json
        debug_file.write(str(response))

    updated_results = process_grievance_data(results)

    return updated_results


# ef semanticSearchCount(
#     es_client,
#     query: str,
#     start_date: str,
#     end_date: str,
#     embed_model,
#     index_name: str,
#     CityName: str = "All",
#     stateName: str = "All",
#     complaintType: str = "All",
#     complaintMode: str = "All",
#     companyName: str = "All",
#     complaintStatus: str = "All",
#     threshold: float = 0.5,
#     complaint_numbers: list = ["NA"]
# ):
#     """
#     Perform semantic search count in Elasticsearch
#     """
#     search_type = 'complaintDetails_vector'
#     query_vector = embed_model.encode([query], show_progress_bar=False, convert_to_numpy=True)[0].tolist()

#     # Construct the search query
#     search_query = {
#         "size": 0,
#         "track_total_hits": True,
#         "min_score": threshold,
#         "query": {
#             "script_score": {
#                 "query": {
#                     "bool": {
#                         "must": [
#                             {"exists": {"field": search_type}},
#                             {"range": {"complaintRegDate": {"gte": start_date, "lte": end_date}}}
#                         ]
#                     }
#                 },
#                 "script": {
#                     "source": f"cosineSimilarity(params.query_vector, '{search_type}') + 1.0",
#                     "params": {"query_vector": query_vector}
#                 }
#             }
#         }
#     }

#     # Add filters conditionally
#     if CityName != "All":
#         search_query["query"]["script_score"]["query"]["bool"]["must"].append({
#             "term": {"cityName": CityName}
#         })

#     if stateName != "All":
#         search_query["query"]["script_score"]["query"]["bool"]["must"].append({
#             "term": {"stateName": stateName}
#         })

#     if complaintType != "All":
#         search_query["query"]["script_score"]["query"]["bool"]["must"].append({
#             "term": {"complaintType": complaintType}
#         })

#     if complaintMode != "All":
#         search_query["query"]["script_score"]["query"]["bool"]["must"].append({
#             "term": {"complaintMode": complaintMode}
#         })

#     if companyName != "All":
#         search_query["query"]["script_score"]["query"]["bool"]["must"].append({
#             "multi_match": {
#                 "query": companyName,
#                 "fields": ["converganceCompanyName", "nonCoverganeceCompanyName"]
#             }
#         })

#     if complaintStatus != "All":
#         search_query["query"]["script_score"]["query"]["bool"]["must"].append({
#             "term": {"complaintStatus": complaintStatus}
#         })

#     if complaint_numbers != ["NA"]:
#         formatted_ids = [num.replace("/", "_") for num in complaint_numbers]
#         search_query["query"]["script_score"]["query"]["bool"]["must"].append({
#             "ids": {"values": formatted_ids}
#         })

#     with open("semantic_search_count_debug.txt", "w") as debug_file:
#         debug_file.write(json.dumps(search_query, indent=2))

#     try:
#         response = es_client.search(
#             index=index_name, 
#             body=search_query,
#             request_timeout=600
#         )
#         return {"total_count":response["hits"]["total"]["value"]}
#     except Exception as e:
#         print(f"Error during search count: {e}")
#         return 0





def keywordSearchCount(
    es_client,
    query: str,
    start_date: str,
    end_date: str,
    index_name: str,
    CityName: str = "All",
    stateName: str = "All",
    complaintType: str = "All",
    complaintMode: str = "All",
    companyName: str = "All",
    complaintStatus: str = "All",
    complaint_numbers: list = ["NA"]
) -> dict:
    """
    Return count of documents matching keyword search criteria.
    """
    # Separate quoted and non-quoted terms
    parts = query.split('"')
    quoted_parts = [part.strip() for idx, part in enumerate(parts) if idx % 2 == 1 and part.strip()]
    non_quoted_parts = [part.strip() for idx, part in enumerate(parts) if idx % 2 == 0 and part.strip()]

    # Build the query body
    query_body = {
        "size": 0,  # Set size to 0 since we only need count
        "track_total_hits": True,
        "query": {
            "bool": {
                "must": [
                    {"range": {"complaintRegDate": {"gte": start_date, "lte": end_date}}}
                ]
            }
        }
    }

    # Add text search conditions
    bool_condition = {"bool": {}}
    if quoted_parts:
        bool_condition['bool']['must'] = [
            {"match_phrase": {"complaintDetails": part}} for part in quoted_parts
        ]
    if non_quoted_parts:
        bool_condition['bool']['should'] = [
            {"match": {"complaintDetails": {"query": " ".join(non_quoted_parts), "operator": "OR"}}}
        ]
    if bool_condition['bool']:
        query_body['query']['bool']['must'].append(bool_condition)

    # Add filters conditionally
    if CityName != "All":
        query_body["query"]["bool"]["must"].append({
            "term": {"cityName": CityName}
        })

    if stateName != "All":
        query_body["query"]["bool"]["must"].append({
            "term": {"stateName": stateName}
        })

    if complaintType != "All":
        query_body["query"]["bool"]["must"].append({
            "term": {"complaintType": complaintType}
        })

    if complaintMode != "All":
        query_body["query"]["bool"]["must"].append({
            "term": {"complaintMode": complaintMode}
        })

    if companyName != "All":
        query_body["query"]["bool"]["must"].append({
            "multi_match": {
                "query": companyName,
                "fields": ["converganceCompanyName", "nonCoverganeceCompanyName"]
            }
        })

    if complaintStatus != "All":
        query_body["query"]["bool"]["must"].append({
            "term": {"complaintStatus": complaintStatus}
        })

    if complaint_numbers != ["NA"]:
        formatted_ids = [num.replace("/", "_") for num in complaint_numbers]
        query_body["query"]["bool"]["must"].append({
            "ids": {"values": formatted_ids}
        })

    with open("keyword_search_count_debug.txt", "w") as debug_file:
        debug_file.write(json.dumps(query_body, indent=2))

    try:
        response = es_client.search(
            index=index_name,
            body=query_body,
            request_timeout=600
        )
        return {"total_count":response["hits"]["total"]["value"]}
    except Exception as e:
        print(f"Error during count: {e}")
        return 0
    

# def keywordSearchBasic(
#     es_client,
#     query: str,
#     start_date: str,
#     end_date: str,
#     index_name: str,
#     CityName: str = "All",
#     stateName: str = "All",
#     complaintType: str = "All",
#     complaintMode: str = "All",
#     companyName: str = "All",
#     complaintStatus: str = "All",
#     complaint_numbers: list = ["NA"]
# ) -> dict:
#     """
#     Perform keyword-based search and return only counts and registration numbers.
    
#     Returns
#     -------
#     dict
#         Dictionary containing total_counts and list of registration numbers
#     """
    
#     print("Starting basic keyword search...", query)

#     search_body = {
#         "size": 10000,  # Adjust based on your needs
#         "_source": ["_id"],  # Only fetch IDs
#         "track_total_hits": True,
#         "query": {
#             "bool": {
#                 "must": [
#                     {
#                         "range": {
#                             "complaintRegDate": {
#                                 "gte": start_date,
#                                 "lte": end_date,
#                                 "format": "yyyy-MM-dd"
#                             }
#                         }
#                     },
#                     {
#                         "match": {
#                             "complaintDetails": {
#                                 "query": query,
#                                 "operator": "AND",
#                                 "minimum_should_match": "70%",
#                                 "fuzziness": "AUTO"
#                             }
#                         }
#                     }
#                 ]
#             }
#         }
#     }

#     # Add complaint numbers filter if provided
#     if complaint_numbers != ["NA"]:
#         formatted_ids = [num.replace("/", "_") for num in complaint_numbers]
#         search_body["query"]["bool"]["must"].append({
#             "ids": {"values": formatted_ids}
#         })

#     # Add filters conditionally
#     if CityName != "All":
#         search_body["query"]["bool"]["must"].append({
#             "term": {"cityName": CityName}
#         })

#     if stateName != "All":
#         search_body["query"]["bool"]["must"].append({
#             "term": {"stateName": stateName}
#         })

#     if complaintType != "All":
#         search_body["query"]["bool"]["must"].append({
#             "term": {"complaintType": complaintType}
#         })

#     if complaintMode != "All":
#         search_body["query"]["bool"]["must"].append({
#             "term": {"complaintMode": complaintMode}
#         })

#     if companyName != "All":
#         search_body["query"]["bool"]["must"].append({
#             "multi_match": {
#                 "query": companyName,
#                 "fields": ["converganceCompanyName", "nonCoverganeceCompanyName"],
#                 "operator": "OR"
#             }
#         })

#     if complaintStatus != "All":
#         search_body["query"]["bool"]["must"].append({
#             "term": {"complaintStatus": complaintStatus}
#         })

#     try:
#         response = es_client.search(
#             index=index_name,
#             body=search_body,
#             request_timeout=600
#         )
        
#         total_hits = response["hits"]["total"]["value"]
#         complaintNumbers = [hit["_id"].replace("_", "/") for hit in response["hits"]["hits"]]
        
#         return {
#             "total_counts": total_hits,
#             "complaintNumbers": complaintNumbers
#         }
    
#     except Exception as e:
#         print(f"Error during keyword search: {e}")
#         return {
#             "total_counts": 0,
#             "complaintNumbers": []
#         }


def keywordSearchBasic(
    es_client,
    query: str,
    start_date: str,
    end_date: str,
    index_name: str,
    CityName: str = "All",
    stateName: str = "All",
    complaintType: str = "All",
    complaintMode: str = "All",
    companyName: str = "All",
    complaintStatus: str = "All",
    complaint_numbers: list = ["NA"]
) -> dict:
    """
    Perform keyword-based search using exact matching and return counts and registration numbers.
    Supports quoted phrases for exact phrase matching.
    """
    
    print("Starting basic keyword search with exact matching...", query)
    
    # Validate query
    if not query or not query.strip():
        print("Warning: Empty query provided")
        query = ""
    
    query = query.strip()

    # Split query into quoted and non-quoted parts
    parts = query.split('"')
    quoted_parts = [part.strip() for idx, part in enumerate(parts) if idx % 2 == 1 and part.strip()]
    non_quoted_parts = [part.strip() for idx, part in enumerate(parts) if idx % 2 == 0 and part.strip()]
    
    # Join non-quoted parts and clean up
    non_quoted_text = " ".join(non_quoted_parts).strip()

    search_body = {
        "size": 10000,
        "_source": ["_id"],
        "track_total_hits": True,
        "query": {
            "bool": {
                "must": [
                    {
                        "range": {
                            "complaintRegDate": {
                                "gte": start_date,
                                "lte": end_date,
                                "format": "yyyy-MM-dd"
                            }
                        }
                    }
                ]
            }
        }
    }

    # Track if we have any text search conditions
    has_text_search = False

    # Add exact phrase searches for quoted parts
    if quoted_parts:
        has_text_search = True
        for part in quoted_parts:
            search_body["query"]["bool"]["must"].append({
                "match_phrase": {
                    "complaintDetails": {
                        "query": part,
                        "boost": 2.0  # Higher weight for exact phrases
                    }
                }
            })

    # Add exact term matching for non-quoted parts
    if non_quoted_text:
        has_text_search = True
        search_body["query"]["bool"]["must"].append({
            "match": {
                "complaintDetails": {
                    "query": non_quoted_text,
                    "operator": "AND",  # All terms must match
                    "boost": 1.0
                }
            }
        })

    # Add filters conditionally
    if complaint_numbers != ["NA"]:
        formatted_ids = [num.replace("/", "_") for num in complaint_numbers]
        search_body["query"]["bool"]["must"].append({
            "ids": {"values": formatted_ids}
        })

    if CityName != "All":
        search_body["query"]["bool"]["must"].append({
            "term": {"cityName": CityName}
        })

    if stateName != "All":
        search_body["query"]["bool"]["must"].append({
            "term": {"stateName": stateName}
        })

    if complaintType != "All":
        search_body["query"]["bool"]["must"].append({
            "term": {"complaintType": complaintType}
        })

    if complaintMode != "All":
        search_body["query"]["bool"]["must"].append({
            "term": {"complaintMode": complaintMode}
        })

    if companyName != "All":
        search_body["query"]["bool"]["must"].append({
            "term": {
                "converganceCompanyName": companyName
            }
        })

    if complaintStatus != "All":
        search_body["query"]["bool"]["must"].append({
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
        
        # Debug output
        debug_info = {
            "original_query": query,
            "quoted_parts": quoted_parts,
            "non_quoted_text": non_quoted_text,
            "has_text_search": has_text_search,
            "elasticsearch_query": search_body,
            "total_hits": total_hits
        }
        
        with open("keyword_search_debug.txt", "w") as debug_file:
            debug_file.write(json.dumps(debug_info, indent=2))
        
        return {
            "total_counts": total_hits,
            "complaintNumbers": complaintNumbers
        }
    
    except Exception as e:
        print(f"Error during keyword search: {e}")
        return {
            "total_counts": 0,
            "complaintNumbers": []
        }