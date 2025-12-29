from repository.basicdetails import process_grievance_data
import json

def keywordSearch(
    query: str,
    start_date: str,
    end_date: str,
    skip: int,
    size: int,
    index_name: str,
    CompanyName: str,
    Sector: str,
    Category: str,
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
                    {"range": {"created_at": {"gte": start_date, "lte": end_date}}}
                ]
            }
        }
    }

    # Add text search conditions
    bool_condition = {"bool": {}}
    if quoted_parts:
        bool_condition['bool']['must'] = [
            {"match_phrase": {"Remark": part}} for part in quoted_parts
        ]
    if non_quoted_parts:
        bool_condition['bool']['should'] = [
            {"match": {"Remark": {"query": " ".join(non_quoted_parts), "operator": "OR"}}}
        ]
    if bool_condition['bool']:
        query_body['query']['bool']['must'].append(bool_condition)

    # Add filters for CompanyName, Sector, Category
    if CompanyName and CompanyName != "All":
        query_body['query']['bool']['must'].append({"term": {"CompanyName.keyword": CompanyName}})
    if Sector and Sector != "All":
        query_body['query']['bool']['must'].append({"term": {"Sector.keyword": Sector}})
    if Category and Category != "All":
        query_body['query']['bool']['must'].append({"term": {"Category.keyword": Category}})
    
    # Add filter for complaint numbers if provided
    if complaint_numbers != ["NA"]:
        query_body['query']['bool']['must'].append({"terms": {"ComplainNumber.keyword": complaint_numbers}})
    
    print("Constructed Query Body:", json.dumps(query_body, indent=2))
    # Execute the search
    es = process_grievance_data()
    response = es.search(index=index_name, body=query_body)
    return response