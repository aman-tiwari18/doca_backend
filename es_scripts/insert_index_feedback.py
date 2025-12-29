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
INDEX_NAME = config["ES"]["INDEX_NAME_FEEDBACK"]
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
    descriptions = batch['Remark'].fillna('').astype(str).tolist()


    vectors = model.encode(descriptions, show_progress_bar=False, convert_to_numpy=True)
    for idx, row in batch.iterrows():
        grievance_id = row['Docketnumber']
        yield {
            "_index": INDEX_NAME,
            "_id": grievance_id,
            "_source": {
                'Regmobile': row['Regmobile'] if not pd.isna(row['Regmobile']) else None,
                'CompanyName': row['CompanyName'] if not pd.isna(row['CompanyName']) else None,
                'Sector': row['Sector'] if not pd.isna(row['Sector']) else None,
                'Category': row['Category'] if not pd.isna(row['Category']) else None,
                'ExperiencewithNCH': row['ExperiencewithNCH'] if not pd.isna(row['ExperiencewithNCH']) else None,
                'userexperience': row['userexperience'] if not pd.isna(row['userexperience']) else None,
                'unUnsatisfactory': row['unUnsatisfactory'] if not pd.isna(row['unUnsatisfactory']) else None,
                'Remark': row['Remark'] if not pd.isna(row['Remark']) else None,
                'Remark_vector': vectors[idx].tolist(),
                'created_at': row['created_at'] if not pd.isna(row['created_at']) else None,
                'updated_at': row['updated_at'] if not pd.isna(row['updated_at']) else None
            }
        }

def process_batch(batch):
    try:
        helpers.bulk(es_client, prepare_bulk_data(batch))
    except Exception as e:
        print(f"[{datetime.now()}] Error in bulk upload: {e}")


print(f"[{datetime.now()}] Acquired file lock. Starting process...")
# Load data
try:
    connection = connectDB_alchemy()
    query = "SELECT * FROM tblfeedback where created_at >= '2024-10-14 00:00:00'"  # Update with your actual table name
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