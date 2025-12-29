def hybridSearch(
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
    Hybrid search: combines semantic vector search with boosted keyword search.

    Parameters
    ----------
    es_client : Elasticsearch
        Elasticsearch client instance
    query : str
        Search query string
    start_date : str
        Start date for filtering
    end_date : str
        End date for filtering
    embed_model : Any
        Embedding model instance
    skip : int
        Number of records to skip
    size : int
        Number of records to retrieve
    index_name : str
        Name of the Elasticsearch index
    """
    # Field weights for keyword search
    field_weights = {
        "complaintDetails": 3
    }

    vector_query = embed_model.encode([query], show_progress_bar=False, convert_to_numpy=True)[0].tolist()

    # Prepare keyword query
    parts = query.split('"')
    quoted_parts = [part.strip() for idx, part in enumerate(parts) if idx % 2 == 1 and part.strip()]
    non_quoted_parts = [part.strip() for idx, part in enumerate(parts) if idx % 2 == 0 and part.strip()]

    keyword_should = []

    # Handle quoted parts (AND operator)
    if quoted_parts:
        for field, weight in field_weights.items():
            keyword_should.append({
                "match_phrase": {
                    field: {
                        "query": " ".join(quoted_parts),
                        "boost": weight
                    }
                }
            })

    # Handle non-quoted parts (OR operator)
    if non_quoted_parts:
        for field, weight in field_weights.items():
            keyword_should.append({
                "match": {
                    field: {
                        "query": " ".join(non_quoted_parts),
                        "operator": "OR",
                        "boost": weight
                    }
                }
            })

    # Prepare semantic (vector) query with filters
    semantic_query = {
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
                "params": {"query_vector": vector_query}
            }
        }
    }

    # Add filters to both semantic and keyword queries
    filter_conditions = []
    
    if CityName != "All":
        filter_conditions.append({"term": {"cityName": CityName}})
    
    if stateName != "All":
        filter_conditions.append({"term": {"stateName": stateName}})
    
    if complaintType != "All":
        filter_conditions.append({"term": {"complaintType": complaintType}})
    
    if complaintMode != "All":
        filter_conditions.append({"term": {"complaintMode": complaintMode}})
    
    if companyName != "All":
        filter_conditions.append({
            "multi_match": {
                "query": companyName,
                "fields": ["converganceCompanyName", "nonCoverganeceCompanyName"]
            }
        })
    
    if complaintStatus != "All":
        filter_conditions.append({"term": {"complaintStatus": complaintStatus}})

    if complaint_numbers != ["NA"]:
        formatted_ids = [num.replace("/", "_") for num in complaint_numbers]
        filter_conditions.append({"ids": {"values": formatted_ids}})

    # Combine both queries with filters
    query_body = {
        "from": skip,
        "size": size,
        "min_score": threshold,
        "track_total_hits": True,
        "query": {
            "bool": {
                "must": filter_conditions,
                "should": [
                    semantic_query,
                    {"bool": {"should": keyword_should}}
                ],
                "minimum_should_match": 1
            }
        }
    }

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
            "lastUpdationDate": hit['_source'].get('lastUpdationDate', ''),
            "score": hit.get('_score', 0)
        }
        results.append(result)

    return {
        "total_count": total_hits,
        "grievanceData": results
    }



def hybridSearchCount(
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
) -> int:
    """
    Get count of results for hybrid search without retrieving documents.

    Parameters
    ----------
    es_client : Elasticsearch
        Elasticsearch client instance
    query : str
        Search query string
    start_date : str
        Start date for filtering
    end_date : str
        End date for filtering
    embed_model : Any
        Embedding model instance
    index_name : str
        Name of the Elasticsearch index
    """
    # Field weights for keyword search
    field_weights = {
        "complaintDetails": 3
    }

    vector_query = embed_model.encode([query], show_progress_bar=False, convert_to_numpy=True)[0].tolist()

    # Prepare keyword query parts
    parts = query.split('"')
    quoted_parts = [part.strip() for idx, part in enumerate(parts) if idx % 2 == 1 and part.strip()]
    non_quoted_parts = [part.strip() for idx, part in enumerate(parts) if idx % 2 == 0 and part.strip()]

    keyword_should = []

    # Handle quoted parts (AND operator)
    if quoted_parts:
        for field, weight in field_weights.items():
            keyword_should.append({
                "match_phrase": {
                    field: {
                        "query": " ".join(quoted_parts),
                        "boost": weight
                    }
                }
            })

    # Handle non-quoted parts (OR operator)
    if non_quoted_parts:
        for field, weight in field_weights.items():
            keyword_should.append({
                "match": {
                    field: {
                        "query": " ".join(non_quoted_parts),
                        "operator": "OR",
                        "boost": weight
                    }
                }
            })

    # Prepare semantic query with filters
    semantic_query = {
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
                "params": {"query_vector": vector_query}
            }
        }
    }

    # Add filters
    filter_conditions = []
    
    if CityName != "All":
        filter_conditions.append({"term": {"cityName": CityName}})
    
    if stateName != "All":
        filter_conditions.append({"term": {"stateName": stateName}})
    
    if complaintType != "All":
        filter_conditions.append({"term": {"complaintType": complaintType}})
    
    if complaintMode != "All":
        filter_conditions.append({"term": {"complaintMode": complaintMode}})
    
    if companyName != "All":
        filter_conditions.append({
            "multi_match": {
                "query": companyName,
                "fields": ["converganceCompanyName", "nonCoverganeceCompanyName"]
            }
        })
    
    if complaintStatus != "All":
        filter_conditions.append({"term": {"complaintStatus": complaintStatus}})

    if complaint_numbers != ["NA"]:
        formatted_ids = [num.replace("/", "_") for num in complaint_numbers]
        filter_conditions.append({"ids": {"values": formatted_ids}})

    # Combine queries with filters
    query_body = {
        "size": 0,  # Set size to 0 since we only need count
        "track_total_hits": True,
        "min_score": threshold,
        "query": {
            "bool": {
                "must": filter_conditions,
                "should": [
                    semantic_query,
                    {"bool": {"should": keyword_should}}
                ],
                "minimum_should_match": 1
            }
        }
    }

    try:
        response = es_client.search(
            index=index_name,
            body=query_body,
            request_timeout=600
        )
        return response["hits"]["total"]["value"]
    except Exception as e:
        print(f"Error during count: {e}")
        return 0