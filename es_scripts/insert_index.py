import pandas as pd
from elasticsearch import helpers
from multiprocessing import Pool, cpu_count
from tqdm import tqdm
from datetime import datetime
from filelock import FileLock
import sys
from pathlib import Path
import multiprocessing

# ---------------------------- Path Management ----------------------------
resources_dir = Path(__file__).resolve().parents[1] / "resources" # ../resources
sys.path.append(str(resources_dir))

# ---------------------------- Import External Utilities ----------------------------
from utility import getES, load_config, getEmbed, connectDB_alchemy

# Objects
es_client = getES()
config = load_config()
model = getEmbed()

# Constants
INDEX_NAME = config["ES"]["INDEX_NAME"]
# DATA_FILE = "../data/griev.pkl" # Update with your data file path
LOCK_FILE = "indexing.lock"
BATCH_SIZE = 1000

# Load model (with GPU support)
print(f"[{datetime.now()}] Loading model...")
if model.device.type == 'cuda':
    print(f"[{datetime.now()}] Using GPU: {model.device}")
else:
    print(f"[{datetime.now()}] Using CPU")

def prepare_bulk_data(batch):
    print(f"[{datetime.now()}] Preparing batch of size {len(batch)}")
    batch = batch.reset_index(drop=True) # ✅ Important
    # Encode in batch (GPU-accelerated)
    descriptions = batch['complaintDetails'].fillna('').astype(str).tolist()

    vectors = model.encode(descriptions, show_progress_bar=False, convert_to_numpy=True)
    for idx, row in batch.iterrows():
        grievance_id = row['complainNumber']
        yield {
            "_index": INDEX_NAME,
            "_id": grievance_id,
            "_source": {
                'userId': row['userId'] if not pd.isna(row['userId']) else None,
                'stateCode': row['stateCode'] if not pd.isna(row['stateCode']) else None,
                'purchasePlaceCode': row['purchasePlaceCode'] if not pd.isna(row['purchasePlaceCode']) else None,
                'complaintType': row['complaintType'] if not pd.isna(row['complaintType']) else None,
                'complaintMode': row['complaintMode'] if not pd.isna(row['complaintMode']) else None,
                'sectorCode': row['sectorCode'] if not pd.isna(row['sectorCode']) else None,
                'categoryCode': row['categoryCode'] if not pd.isna(row['categoryCode']) else None,
                'converganceCompanyId': row['converganceCompanyId'] if not pd.isna(row['converganceCompanyId']) else None,
                'converganceCompanyName': row['converganceCompanyName'] if not pd.isna(row['converganceCompanyName']) else None,
                'nonCoverganeceCompanyCode': row['nonCoverganeceCompanyCode'] if not pd.isna(row['nonCoverganeceCompanyCode']) else None,
                'nonCoverganeceCompanyName': row['nonCoverganeceCompanyName'] if not pd.isna(row['nonCoverganeceCompanyName']) else None,
                'companyEmailId': row['companyEmailId'] if not pd.isna(row['companyEmailId']) else None,
                'companyContactNumber': row['companyContactNumber'] if not pd.isna(row['companyContactNumber']) else None,
                'companyPincode': row['companyPincode'] if not pd.isna(row['companyPincode']) else None,
                'agencyDetails': row['agencyDetails'] if not pd.isna(row['agencyDetails']) else None,
                'productValue': row['productValue'] if not pd.isna(row['productValue']) else None,
                'agentId': row['agentId'] if not pd.isna(row['agentId']) else None,
                'fop': row['fop'] if not pd.isna(row['fop']) else None,
                'complaintStatus': row['complaintStatus'] if not pd.isna(row['complaintStatus']) else None,
                'companyStatus': row['companyStatus'] if not pd.isna(row['companyStatus']) else None,
                'complaintRegDate': row['complaintRegDate'] if not pd.isna(row['complaintRegDate']) else None,
                'lastEditedBy': row['lastEditedBy'] if not pd.isna(row['lastEditedBy']) else None,
                'pgDocketNumber': row['pgDocketNumber'] if not pd.isna(row['pgDocketNumber']) else None,
                'userCommentDate': row['userCommentDate'] if not pd.isna(row['userCommentDate']) else None,
                'lastUpdationDate': row['lastUpdationDate'] if not pd.isna(row['lastUpdationDate']) else None,
                'regulatorId': row['regulatorId'] if not pd.isna(row['regulatorId']) else None,
                'DeptRegulatorId': row['DeptRegulatorId'] if not pd.isna(row['DeptRegulatorId']) else None,
                'countryCode': row['countryCode'] if not pd.isna(row['countryCode']) else None,
                'complaintDetails': row['complaintDetails'] if not pd.isna(row['complaintDetails']) else None,
                "complaintDetails_vector": vectors[idx].tolist() if vectors is not None else None
            }
        }

def process_batch(batch):
    try:
        helpers.bulk(es_client, prepare_bulk_data(batch))
    except Exception as e:
        print(f"[{datetime.now()}] Error in bulk upload: {e}")

# def main():
#     # with FileLock(LOCK_FILE):
#     print(f"[{datetime.now()}] Acquired file lock. Starting process...")
#     # Load data
#     try:
#         connection = connectDB_alchemy()
#         query = "SELECT * FROM tblcomplaints"  # Update with your actual table name
#         data = pd.read_sql(query, connection)
#         connection.close()
#         print(data.columns)
#         print(data.head())
#     except Exception as e:
#         print(f"[{datetime.now()}] Failed to load data: {e}")
#         sys.exit(1)

#     if data.empty:
#         print(f"[{datetime.now()}] No data found to index.")
#         return

#     print(f"[{datetime.now()}] Records to index: {len(data)}")
#     # Split data into batches
#     data = data.reset_index(drop=True)
#     batches = [data.iloc[i:i + BATCH_SIZE] for i in range(0, len(data), BATCH_SIZE)]
#     print(f"[{datetime.now()}] Processing in {len(batches)} batches...")
#     num_processes = min(2, cpu_count()) # GPU safe: 1 or 2 processes only
#     with Pool(processes=num_processes) as pool:
#         list(tqdm(pool.imap_unordered(process_batch, batches), total=len(batches)))
#     print(f"[{datetime.now()}] Indexing completed successfully.")

print(f"[{datetime.now()}] Acquired file lock. Starting process...")
# Load data
try:
    connection = connectDB_alchemy()
    query = "SELECT * FROM tblcomplaints where complaintRegDate >= '2025-01-01 00:00:00'"  # Update with your actual table name
    data = pd.read_sql(query, connection)

    print(data.columns)
    print(data.head())
except Exception as e:
    print(f"[{datetime.now()}] Failed to load data: {e}")
    sys.exit(1)

if data.empty:
    print(f"[{datetime.now()}] No data found to index.")

print(f"[{datetime.now()}] Records to index: {len(data)}")
# Split data into batches
data = data.reset_index(drop=True)
batches = [data.iloc[i:i + BATCH_SIZE] for i in range(0, len(data), BATCH_SIZE)]
print(f"[{datetime.now()}] Processing in {len(batches)} batches...")
num_processes = min(2, cpu_count()) # GPU safe: 1 or 2 processes only
for batch in batches:
    process_batch(batch)
# with Pool(processes=num_processes) as pool:
#     list(tqdm(pool.imap_unordered(process_batch, batches), total=len(batches)))
print(f"[{datetime.now()}] Indexing completed successfully.")