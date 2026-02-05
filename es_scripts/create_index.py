#------------------------Util Library Import------------------------------------------------------
import sys
from pathlib import Path
from elasticsearch import Elasticsearch
# ---------------------------- Path Management ----------------------------
resources_dir = Path(__file__).resolve().parents[1] / "resources" # ../resources
sys.path.append(str(resources_dir))
# ---------------------------- Import External Utilities ----------------------------
from utility import getES, load_config, config

def create_index(es_client, index_name, index_schema):
    try:
        if es_client.indices.exists(index=index_name):
            print(f"[INFO] Index '{index_name}' already exists. Skipping creation.")
            return
        response = es_client.indices.create(
            index=index_name,
            body=index_schema # use `body`, safer
        )
        if response.get('acknowledged'):
            print(f"[SUCCESS] Index '{index_name}' created successfully.")
        else:
            print(f"[WARNING] Index '{index_name}' creation not acknowledged: {response}")
    except Exception as e:
        print(f"[ERROR] Failed to create index '{index_name}': {e}")

# x = Elasticsearch(
#     # hosts=[{'host': 'localhost', 'port': 9200, 'scheme': 'https'}],
#     hosts = "https://localhost:9200",
#     basic_auth=(config["ES"]["USERNAME"], config["ES"]["PASSWORD"]),
#     request_timeout=30,
#     ca_certs=config["ES"]["CERT_PATH"],  # Path to SSL certificate
#     verify_certs=True
#     )

# print(x.info())

if __name__ == "__main__":
    config = load_config()
    es_client = getES()

    INDEX_SCHEMA = {
        "mappings": {
            "properties": {
                # Add attributes here
                'complainNumber': {'type': 'keyword'},
                'userId': {'type': 'integer'},
                'stateCode': {'type': 'integer'},
                'purchasePlaceCode': {'type': 'integer'},
                'complaintType': {'type': 'text', 'analyzer': 'simple'},
                'complaintMode': {'type': 'text', 'analyzer': 'simple'},
                'sectorCode': {'type': 'integer'},
                'categoryCode': {'type': 'integer'},
                'converganceCompanyId': {'type': 'keyword'},
                'converganceCompanyName': {'type': 'keyword'},
                'nonCoverganeceCompanyCode': {'type': 'integer'},
                'nonCoverganeceCompanyName': {'type': 'keyword'},
                'companyEmailId': {'type': 'text'},
                'companyContactNumber': {'type': 'keyword'},
                'companyPincode': {'type': 'keyword'},
                'agencyDetails': {'type': 'text'},
                'productValue': {'type': 'text'},
                'agentId': {'type': 'integer'},
                'fop': {'type': 'text'},
                'complaintDetails': {'type': 'text'},
                'complaintStatus': {'type': 'keyword'},
                'companyStatus': {'type': 'keyword'},
                'complaintRegDate': {'type': 'date'},
                'lastEditedBy': {'type': 'integer'},
                'pgDocketNumber': {'type': 'keyword'},
                'userCommentDate': {'type': 'date'},
                'lastUpdationDate': {'type': 'date'},
                'regulatorId': {'type': 'integer'},
                'DeptRegulatorId': {'type': 'keyword'},
                'countryCode': {'type': 'keyword'}
            }
        }
    }

    create_index(es_client, config["ES"]["INDEX_NAME"], INDEX_SCHEMA)
    es_client.close()