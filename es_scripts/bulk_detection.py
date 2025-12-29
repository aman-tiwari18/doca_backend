import sys
from pathlib import Path
from elasticsearch import helpers
from tqdm import tqdm
import logging
from utility import getES, load_config

# ---------------------------- Logging Setup ----------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
# ---------------------------- Path Management ----------------------------
resources_dir = Path(__file__).resolve().parents[1] / "resources"
sys.path.append(str(resources_dir))
# ---------------------------- External Utilities ----------------------------
from utility import getES, load_config

# Objects
es_client = getES()
config = load_config()

# Constants
INDEX_NAME = config["ES"]["INDEX_NAME"]
BATCH_SIZE = 1000

def create_index(es_client, index_name):
    try:
        if es_client.indices.exists(index=index_name):
            print(f"[INFO] Index '{index_name}' already exists. Skipping creation.")
            return
        response = es_client.indices.create(
            index=index_name,
            body={
                "mappings": {
                    "properties": {
                        'complainNumber': {'type': 'integer'},
                        'userId': {'type': 'integer'},
                        'stateCode': {'type': 'integer'},
                        'purchasePlaceCode': {'type': 'integer'},
                        'complaintType': {'type': 'text', 'analyzer': 'simple'},
                        'complaintMode': {'type': 'text', 'analyzer': 'simple'},
                        'sectorCode': {'type': 'integer'},
                        'categoryCode': {'type': 'integer'},
                        'converganceCompanyId': {'type': 'keyword'},
                        'converganceCompanyName': {'type': 'text'},
                        'nonCoverganeceCompanyCode': {'type': 'integer'},
                        'nonCoverganeceCompanyName': {'type': 'text'},
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
                        "complaintDetails": {'type': 'text', 'analyzer': 'simple'},
                        "complaintDetails_vector": {"type": "dense_vector", "index": True, "similarity": "cosine", "dims": 768}
                    }
                }
            }
        )
        if response.get('acknowledged'):
            print(f"[SUCCESS] Index '{index_name}' created successfully.")
        else:
            print(f"[WARNING] Index '{index_name}' creation not acknowledged: {response}")
    except Exception as e:
        print(f"[ERROR] Failed to create index '{index_name}': {e}")

def main():
    with FileLock(LOCK_FILE):
        print(f"[{datetime.now()}] Acquired file lock. Starting process...")
        # Load data
        try:
            data = pd.read_pickle(DATA_FILE)
            print(data.columns)
            print(data.head())
        except Exception as e:
            print(f"[{datetime.now()}] Failed to load data: {e}")
            sys.exit(1)

        if data.empty:
            print(f"[{datetime.now()}] No data found to index.")
            return

        print(f"[{datetime.now()}] Records to index: {len(data)}")
        # Split data into batches
        data = data.reset_index(drop=True)
        batches = [data.iloc[i:i + BATCH_SIZE] for i in range(0, len(data), BATCH_SIZE)]
        print(f"[{datetime.now()}] Processing in {len(batches)} batches...")
        num_processes = min(2, cpu_count()) # GPU safe: 1 or 2 processes only
        with Pool(processes=num_processes) as pool:
            list(tqdm(pool.imap_unordered(process_batch, batches), total=len(batches)))
        print(f"[{datetime.now()}] Indexing completed successfully.")
if __name__ == "__main__":
    main()