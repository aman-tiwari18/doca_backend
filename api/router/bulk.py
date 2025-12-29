from fastapi import FastAPI, APIRouter
from elasticsearch import Elasticsearch
from typing import List

# app = FastAPI()
router = APIRouter(tags=["Bulk Operations"])

# Initialize ElasticSearch
es_client = Elasticsearch("http://localhost:9200")  # Update with your ES URL

# Index name
index_name = "testing"  # Change to your index name


@router.get("/get_children/")
def get_children_by_parent_id(token : Annotated[str, Depends(oauth2_scheme)], parent_id, db: Session = Depends(database.get_db)):
    """
    Retrieve all child documents of a given parent_id from Elasticsearch.

    Parameters
    ----------

    1) es: Elasticsearch client instance
    2) index_name: Name of the Elasticsearch index
    3) parent_id: The parent document ID
    :return: List of child documents
    """
    query = {
        "query": {
            "bool": {
                "must": [
                    {"term": {"parent_id": parent_id}}
                ]
            }
        },
        "_source" : ["grievance_description"]
    }

    response = es_client.search(index=index_name, body=query, size=1000)  # Adjust size if expecting more children
    children = [hit["_source"] | {"_id": hit["_id"]} for hit in response["hits"]["hits"]]
    return children


@router.get("/get_parents/")
async def get_parents_with_multiple_children(token : Annotated[str, Depends(oauth2_scheme)], skip: int = 0, size: int = 10, db: Session = Depends(database.get_db)):

    """
    Retrieve parent documents that have more than one child document in Elasticsearch.

    Parameters
    ----------
    1) skip: Number of records to skip (for pagination)
    2) size: Number of records to retrieve
    :return: A dictionary containing the results and total count
    """
    # Initialize variables

    after_key = None
    collected_results = []

    while True:
        body = {
            "size": 0,
            "query": {
                "exists": {
                    "field": "parent_id"
                }
            },
            "aggs": {
                "parents_with_children": {
                    "composite": {
                        "size": 100,  # inner page size
                        "sources": [
                            {"parent_id": {"terms": {"field": "parent_id"}}}
                        ],
                        **({"after": after_key} if after_key else {})
                    },
                    "aggs": {
                        "children_count": {
                            "value_count": {
                                "field": "_id"
                            }
                        }
                    }
                }
            }
        }

        response = es_client.search(index=index_name, body=body)

        buckets = response['aggregations']['parents_with_children']['buckets']

        # Process and collect buckets with more than one child
        for bucket in buckets:
            count = bucket["children_count"]["value"]
            if count > 1:
                collected_results.append({
                    "parent_id": bucket["key"]["parent_id"],
                    "children_count": count
                })

        # Check if we have enough results for skip + size
        if len(collected_results) >= skip + size:
            break

        # Pagination
        after_key = response['aggregations']['parents_with_children'].get('after_key')
        if not after_key:
            break  # No more pages

    # Apply skip and limit after collection, and sort descending
    paginated_results = sorted(
        collected_results,
        key=lambda x: x["children_count"],
        reverse=True
    )[skip: skip + size]

    return {
        "results": paginated_results,
        "total": len(collected_results)
    }
