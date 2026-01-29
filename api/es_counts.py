import sys
from pathlib import Path

# add resources directory to PYTHONPATH
RESOURCES_DIR = Path(__file__).resolve().parent.parent / "resources"
sys.path.append(str(RESOURCES_DIR))

from utility import getES, config


def main():
    es_client = getES()
    index_name = config["ES"]["INDEX_NAME"]

    # 1) Total docs in ES
    total = es_client.count(index=index_name)
    print("Total docs in ES:", total["count"])

    # 2) Docs in date range
    body_date = {
        "query": {
            "range": {
                "complaintRegDate": {
                    "gte": "2024-01-01",
                    "lte": "2025-12-31"
                }
            }
        }
    }
    date_count = es_client.count(index=index_name, body=body_date)
    print("Docs in date range:", date_count["count"])

    # 3) Docs missing stateCode
    body_missing_state = {
        "query": {
            "bool": {
                "must_not": {
                    "exists": {"field": "stateCode"}
                }
            }
        }
    }
    missing_state = es_client.count(index=index_name, body=body_missing_state)
    print("Docs missing stateCode:", missing_state["count"])

    # 4) Docs missing categoryCode
    body_missing_category = {
        "query": {
            "bool": {
                "must_not": {
                    "exists": {"field": "categoryCode"}
                }
            }
        }
    }
    missing_category = es_client.count(index=index_name, body=body_missing_category)
    print("Docs missing categoryCode:", missing_category["count"])

    # 5) Docs in date range + has stateCode
    body_date_and_state = {
        "query": {
            "bool": {
                "filter": [
                    {
                        "range": {
                            "complaintRegDate": {
                                "gte": "2024-01-01",
                                "lte": "2025-12-31"
                            }
                        }
                    },
                    {
                        "exists": {"field": "stateCode"}
                    }
                ]
            }
        }
    }

    date_and_state = es_client.count(index=index_name, body=body_date_and_state)
    print("Docs in date range + has stateCode:", date_and_state["count"])

    es_client.close()


if __name__ == "__main__":
    main()
