# import logging
# import requests
# import json
# import time
# from datetime import datetime, timedelta
# from pathlib import Path
# from sqlalchemy import create_engine, text
# from sqlalchemy.orm import sessionmaker
# from requests.adapters import HTTPAdapter
# from urllib3.util.retry import Retry
# import urllib3
# import sys

# urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# # Configuration
# resources_dir = Path(__file__).resolve().parents[2] / "resources"
# with open(resources_dir / "config.json") as f:
#     config = json.load(f)

# # API Configuration
# API_BASE_URL = config["BASE_URL_CRON"]
# API_USERNAME = config["USERNAME_CRON"]
# API_PASSWORD = config["PASSWORD_CRON"]

# # Script Configuration
# START_DATE = "2024-01-01"  # Start date for data fetch
# PER_PAGE = 1000  # Number of records per page
# BATCH_SIZE = 100  # Number of grievance numbers to fetch details at once
# DELAY_BETWEEN_REQUESTS = 1  # Delay in seconds between API calls
# MAX_RETRIES = 3  # Maximum retries for failed requests
# LOG_FILE = "fetch_complaints_datewise_script.log"

# # Run mode: 'script' or 'cron'
# # In script mode, it will continue until all data is fetched
# # In cron mode, it will process one day and exit
# RUN_MODE = sys.argv[1] if len(sys.argv) > 1 else "script"

# # Logging Configuration
# logging.basicConfig(
#     filename=LOG_FILE,
#     level=logging.INFO,
#     format="%(asctime)s [%(levelname)s] %(message)s"
# )
# console = logging.StreamHandler()
# console.setLevel(logging.INFO)
# console.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
# logging.getLogger("").addHandler(console)

# # State mapping
# with open(resources_dir / "state_name_to_id_map.json") as f:
#     STATE_NAME_TO_ID = json.load(f)

# # Database Configuration (Hardcoded)
# DB_HOST = "localhost"
# DB_USER = "root"
# DB_PASSWORD = "rootpassword123"
# DB_NAME = "consumer_affairs_db_1"
# DB_URL = f"mysql+mysqlconnector://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}"

# engine = create_engine(DB_URL, pool_pre_ping=True, pool_recycle=1800)
# Session = sessionmaker(bind=engine)

# # HTTP Session with retry
# http = requests.Session()
# retry = Retry(total=5, backoff_factor=2, status_forcelist=[500, 502, 503, 504])
# http.mount("https://", HTTPAdapter(max_retries=retry))


# def map_state_name_to_code(state_name):
#     """Map state name to state code using the mapping file"""
#     if not state_name:
#         return None
    
#     state_upper = state_name.upper()
#     for key, value in STATE_NAME_TO_ID.items():
#         if key.upper() == state_upper:
#             return int(value)
    
#     logging.warning(f"State name '{state_name}' not found in mapping")
#     return None


# def get_last_processed_date():
#     """Get the last processed date from state table"""
#     session = Session()
#     try:
#         # Check if state table exists, if not create it
#         session.execute(text("""
#             CREATE TABLE IF NOT EXISTS grievance_ingest_state (
#                 id INT PRIMARY KEY,
#                 last_processed_date DATE,
#                 last_complaint_reg_date DATETIME,
#                 last_complain_number BIGINT,
#                 updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
#             )
#         """))
#         session.commit()
        
#         row = session.execute(
#             text("SELECT last_processed_date FROM grievance_ingest_state WHERE id = 1")
#         ).fetchone()
        
#         if row and row[0]:
#             last_date = row[0]
#             logging.info(f"Resuming from last processed date: {last_date}")
#             # Return next day
#             next_date = datetime.strptime(str(last_date), "%Y-%m-%d") + timedelta(days=1)
#             return next_date.strftime("%Y-%m-%d")
#         else:
#             # Initialize state record if not exists
#             session.execute(text("""
#                 INSERT INTO grievance_ingest_state (id, last_processed_date, updated_at)
#                 VALUES (1, NULL, NOW())
#                 ON DUPLICATE KEY UPDATE updated_at = NOW()
#             """))
#             session.commit()
#             logging.info(f"Starting fresh from {START_DATE}")
#             return START_DATE
            
#     except Exception as e:
#         logging.error(f"Error getting last processed date: {e}")
#         return START_DATE
#     finally:
#         session.close()


# def update_last_processed_date(date_str):
#     """Update the last processed date in state table"""
#     session = Session()
#     try:
#         session.execute(
#             text("""
#                 UPDATE grievance_ingest_state
#                 SET last_processed_date = :date,
#                     updated_at = NOW()
#                 WHERE id = 1
#             """),
#             {"date": date_str}
#         )
#         session.commit()
#         logging.info(f"Updated last processed date to: {date_str}")
#     except Exception as e:
#         logging.error(f"Error updating last processed date: {e}")
#     finally:
#         session.close()


# def fetch_grievance_history_datewise(from_date, to_date, page=1, retry_count=0):
#     """Fetch grievance history for a specific date"""
#     payload = {
#         "from_date": from_date,
#         "to_date": to_date,
#         "per_page": PER_PAGE,
#         "page": page
#     }
    
#     logging.info(f"Fetching grievances from {from_date} to {to_date} (Page {page})")
    
#     try:
#         response = http.post(
#             f"{API_BASE_URL}/grievanceHistoryDatewise",
#             auth=(API_USERNAME, API_PASSWORD),
#             json=payload,
#             timeout=120,
#             verify=False
#         )
        
#         response.raise_for_status()
#         data = response.json()
        
#         # Handle the response structure
#         if data.get("status"):
#             return data.get("basicGrievanceDetails", [])
#         else:
#             logging.warning(f"API returned status false: {data.get('message')}")
#             return []
            
#     except requests.exceptions.RequestException as e:
#         if retry_count < MAX_RETRIES:
#             wait_time = (retry_count + 1) * 5
#             logging.warning(f"Error fetching history: {e}. Retrying in {wait_time}s... (Attempt {retry_count + 1}/{MAX_RETRIES})")
#             time.sleep(wait_time)
#             return fetch_grievance_history_datewise(from_date, to_date, page, retry_count + 1)
#         else:
#             logging.error(f"Failed to fetch history after {MAX_RETRIES} attempts: {e}")
#             raise


# def fetch_grievance_details(grievance_numbers, retry_count=0):
#     """Fetch detailed information for multiple grievances"""
#     # Join grievance numbers as comma-separated string
#     grievance_nos = ",".join(map(str, grievance_numbers))
    
#     payload = {
#         "grievanceno": grievance_nos
#     }
    
#     logging.info(f"Fetching details for {len(grievance_numbers)} grievances")
    
#     try:
#         response = http.post(
#             f"{API_BASE_URL}/grievanceDetails",
#             auth=(API_USERNAME, API_PASSWORD),
#             json=payload,
#             timeout=120,
#             verify=False
#         )
        
#         response.raise_for_status()
#         data = response.json()
        
#         if data.get("status"):
#             return data.get("basicGrievanceDetails", [])
#         else:
#             logging.warning(f"API returned status false: {data.get('message')}")
#             return []
            
#     except requests.exceptions.RequestException as e:
#         if retry_count < MAX_RETRIES:
#             wait_time = (retry_count + 1) * 5
#             logging.warning(f"Error fetching details: {e}. Retrying in {wait_time}s... (Attempt {retry_count + 1}/{MAX_RETRIES})")
#             time.sleep(wait_time)
#             return fetch_grievance_details(grievance_numbers, retry_count + 1)
#         else:
#             logging.error(f"Failed to fetch details after {MAX_RETRIES} attempts: {e}")
#             return []


# def check_existing_complaints(session, complaint_numbers):
#     """Check which complaints already exist in the database"""
#     if not complaint_numbers:
#         return set()
    
#     try:
#         placeholders = ', '.join([f':id{i}' for i in range(len(complaint_numbers))])
#         params = {f'id{i}': num for i, num in enumerate(complaint_numbers)}
        
#         result = session.execute(
#             text(f"SELECT complainNumber FROM tblcomplaints WHERE complainNumber IN ({placeholders})"),
#             params
#         ).fetchall()
        
#         existing = {row[0] for row in result}
#         logging.info(f"Found {len(existing)}/{len(complaint_numbers)} existing complaints in database")
#         return existing
        
#     except Exception as e:
#         logging.error(f"Error checking existing complaints: {e}")
#         return set()


# def upsert_complaint(session, detail_info):
#     """Insert or update a single complaint with all available data"""
#     try:
#         grievance_number = detail_info.get("grievanceNumber")
#         if not grievance_number:
#             logging.warning("Skipping complaint without grievanceNumber")
#             return False
        
#         # Map state name to code
#         state_code = None
#         state_name = detail_info.get("stateName")
#         if state_name:
#             state_code = map_state_name_to_code(state_name)
        
#         complaint_data = {
#             "complainNumber": grievance_number,
#             "userId": detail_info.get("userId", 0),
#             "userEmailId": detail_info.get("emailId"),
#             "userContactNumber": detail_info.get("mbileNumber"),
#             "complaintDetails": detail_info.get("grievanceDetails"),
#             "converganceCompanyName": detail_info.get("converganceCompanyName"),
#             "nonCoverganenceCompanyName": detail_info.get("nonCoverganeceCompanyName"),
#             "complaintMode": detail_info.get("grievanceMode"),
#             "complaintStatus": detail_info.get("grievanceStatus"),
#             "complaintRegDate": detail_info.get("complaintRegDate"),
#             "agentRemark": detail_info.get("agentRemark"),
#             "userComment": detail_info.get("userComment"),
#             "userCommentDate": detail_info.get("userCommentDate"),
#             "docketType": detail_info.get("docketType"),
#             "grievanceclassification": detail_info.get("grievanceClassification"),
#             "productValue": detail_info.get("grivanceAmount") or detail_info.get("productValue"),
#             "supportDoc1": detail_info.get("supportDoc1"),
#             "supportDoc2": detail_info.get("supportDoc2"),
#             "supportDoc3": detail_info.get("supportDoc3"),
#             "fop": detail_info.get("frequentlyOccuredProblem"),
#             "pgDocketNumber": detail_info.get("pgDocketNumber"),
#             "agencyDetails": detail_info.get("agencyDetails"),
#             "stateCode": state_code,
#             "sectorName": detail_info.get("sectorName"),
#             "categoryName": detail_info.get("categoryName"),
#             "purchaseCity": detail_info.get("purchaseCity"),
#             "grievancEexpectation": detail_info.get("grievancEexpectation"),
#             "companyRegisteredGirvance": detail_info.get("companyRegisteredGirvance"),
#             "companyGrievanceNo": detail_info.get("companyGrievanceNo"),
#             "companyGrivanceNoReasons": detail_info.get("companyGrivanceNoReasons"),
#             "gstInfo": detail_info.get("gstInfo")
#         }
        
#         # Filter out None values
#         complaint_data = {k: v for k, v in complaint_data.items() if v is not None}
        
#         columns = list(complaint_data.keys())
#         values_placeholders = [f":{k}" for k in columns]
        
#         # Build update clauses (all columns except primary key)
#         update_clauses = [f"{k} = VALUES({k})" for k in columns if k != "complainNumber"]
#         update_clauses.append("lastUpdationDate = CURRENT_TIMESTAMP")
        
#         query = f"""
#             INSERT INTO tblcomplaints (
#                 {', '.join(columns)}
#             ) VALUES (
#                 {', '.join(values_placeholders)}
#             )
#             ON DUPLICATE KEY UPDATE
#                 {', '.join(update_clauses)}
#         """
        
#         session.execute(text(query), complaint_data)
#         return True
        
#     except Exception as e:
#         logging.error(f"Error upserting complaint {grievance_number}: {e}")
#         return False


# def upsert_user(session, detail_info):
#     """Insert or update user details in tblregistration"""
#     try:
#         user_id = detail_info.get("userId")
#         if not user_id:
#             return False
        
#         # Get names
#         first_name = detail_info.get("firstName")
#         last_name = detail_info.get("lastName")
        
#         # Map state name to code
#         state_code = None
#         state_name = detail_info.get("stateName")
#         if state_name:
#             state_code = map_state_name_to_code(state_name)
        
#         user_data = {
#             "userId": user_id,
#             "firstName": first_name,
#             "lastName": last_name,
#             "mobNumber": detail_info.get("mbileNumber"),
#             "emailId": detail_info.get("emailId"),
#             "stateCode": state_code
#         }
        
#         # Filter out None values
#         user_data = {k: v for k, v in user_data.items() if v is not None}
        
#         columns = list(user_data.keys())
#         values_placeholders = [f":{k}" for k in columns]
        
#         # Build update clauses (all columns except primary key)
#         update_clauses = [f"{k} = VALUES({k})" for k in columns if k != "userId"]
#         update_clauses.append("updationDate = CURRENT_TIMESTAMP")
        
#         query = f"""
#             INSERT INTO tblregistration (
#                 {', '.join(columns)}
#             ) VALUES (
#                 {', '.join(values_placeholders)}
#             )
#             ON DUPLICATE KEY UPDATE
#                 {', '.join(update_clauses)}
#         """
        
#         session.execute(text(query), user_data)
#         return True
        
#     except Exception as e:
#         logging.error(f"Error upserting user {user_id}: {e}")
#         return False


# def process_day_data(date_str):
#     """Process all complaints for a specific day"""
#     from_datetime = f"{date_str} 00:00:00"
#     to_datetime = f"{date_str} 23:59:59"
    
#     logging.info(f"{'='*60}")
#     logging.info(f"Processing date: {date_str}")
#     logging.info(f"{'='*60}")
    
#     session = Session()
#     total_processed = 0
#     total_skipped = 0
#     total_failed = 0
    
#     try:
#         # Fetch all grievances for this day (pagination handled)
#         page = 1
#         all_grievances = []
        
#         while True:
#             grievances = fetch_grievance_history_datewise(from_datetime, to_datetime, page)
            
#             if not grievances:
#                 logging.info(f"No more grievances found on page {page}")
#                 break
            
#             all_grievances.extend(grievances)
#             logging.info(f"Fetched {len(grievances)} grievances from page {page}. Total so far: {len(all_grievances)}")
            
#             # Check if there are more pages (assuming API returns less than PER_PAGE when done)
#             if len(grievances) < PER_PAGE:
#                 break
            
#             page += 1
#             time.sleep(DELAY_BETWEEN_REQUESTS)
        
#         if not all_grievances:
#             logging.info(f"No grievances found for date {date_str}")
#             # Still update the state to move to next day
#             update_last_processed_date(date_str)
#             return True
        
#         logging.info(f"Total grievances fetched for {date_str}: {len(all_grievances)}")
        
#         # Extract grievance numbers
#         grievance_numbers = [g.get("grievanceNumber") for g in all_grievances if g.get("grievanceNumber")]
        
#         # Check which complaints already exist
#         existing_complaints = check_existing_complaints(session, grievance_numbers)
        
#         # Filter out existing complaints
#         new_grievances = [g for g in all_grievances if g.get("grievanceNumber") not in existing_complaints]
        
#         if not new_grievances:
#             logging.info(f"All {len(all_grievances)} grievances already exist in database. Skipping...")
#             total_skipped = len(all_grievances)
#         else:
#             logging.info(f"Processing {len(new_grievances)} new grievances (skipping {len(existing_complaints)} existing)")
            
#             # Process grievances in batches
#             new_grievance_numbers = [g.get("grievanceNumber") for g in new_grievances]
            
#             for i in range(0, len(new_grievance_numbers), BATCH_SIZE):
#                 batch = new_grievance_numbers[i:i+BATCH_SIZE]
                
#                 # Fetch details for this batch
#                 details_list = fetch_grievance_details(batch)
                
#                 # Create a map for quick lookup
#                 details_map = {d.get("grievanceNumber"): d for d in details_list if d.get("grievanceNumber")}
                
#                 # Process each grievance
#                 for grievance_no in batch:
#                     try:
#                         detail_info = details_map.get(grievance_no)
                        
#                         if not detail_info:
#                             logging.warning(f"No details found for grievance {grievance_no}")
#                             total_failed += 1
#                             continue
                        
#                         # Upsert complaint
#                         if upsert_complaint(session, detail_info):
#                             # Upsert user if userId exists
#                             if detail_info.get("userId"):
#                                 upsert_user(session, detail_info)
                            
#                             total_processed += 1
#                         else:
#                             total_failed += 1
                        
#                         # Commit periodically
#                         if total_processed % 50 == 0:
#                             session.commit()
#                             logging.info(f"Progress: Processed {total_processed}, Failed {total_failed}, Skipped {total_skipped}")
                    
#                     except Exception as e:
#                         logging.error(f"Error processing grievance {grievance_no}: {e}")
#                         total_failed += 1
#                         continue
                
#                 # Delay between batches
#                 time.sleep(DELAY_BETWEEN_REQUESTS)
                
#                 # Commit after each batch
#                 session.commit()
#                 logging.info(f"Batch {i//BATCH_SIZE + 1} completed. Progress: Processed {total_processed}, Failed {total_failed}, Skipped {len(existing_complaints)}")
        
#         # Final commit
#         session.commit()
        
#         # Update state to mark this day as processed
#         update_last_processed_date(date_str)
        
#         logging.info(f"{'='*60}")
#         logging.info(f"Completed {date_str}: Processed {total_processed}, Failed {total_failed}, Skipped {len(existing_complaints)}")
#         logging.info(f"{'='*60}")
        
#         return True
        
#     except Exception as e:
#         logging.error(f"Error processing day {date_str}: {e}")
#         session.rollback()
#         return False
#     finally:
#         session.close()


# def main():
#     """Main function to orchestrate the data fetch"""
#     logging.info(f"{'#'*60}")
#     logging.info(f"Starting Grievance Data Fetch - Mode: {RUN_MODE}")
#     logging.info(f"{'#'*60}")
    
#     current_date = datetime.strptime(get_last_processed_date(), "%Y-%m-%d")
#     today = datetime.now()
    
#     while current_date < today:
#         date_str = current_date.strftime("%Y-%m-%d")
        
#         # Process this day
#         success = process_day_data(date_str)
        
#         if not success:
#             logging.error(f"Failed to process {date_str}. Will retry on next run.")
#             # In script mode, we can retry immediately
#             if RUN_MODE == "script":
#                 logging.info("Retrying after 30 seconds...")
#                 time.sleep(30)
#                 continue
#             else:
#                 # In cron mode, exit and let cron retry
#                 break
        
#         # Move to next day
#         current_date += timedelta(days=1)
        
#         # In cron mode, process only one day and exit
#         if RUN_MODE == "cron":
#             logging.info("Cron mode: Processed one day, exiting...")
#             break
        
#         # Small delay between days
#         time.sleep(2)
    
#     logging.info(f"{'#'*60}")
#     logging.info(f"Grievance Data Fetch Completed")
#     logging.info(f"{'#'*60}")


# if __name__ == "__main__":
#     main()


import logging
import requests
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import urllib3
import sys

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configuration
resources_dir = Path(__file__).resolve().parents[2] / "resources"
with open(resources_dir / "config.json") as f:
    config = json.load(f)

# API Configuration
API_BASE_URL = config["BASE_URL_CRON"]
API_USERNAME = config["USERNAME_CRON"]
API_PASSWORD = config["PASSWORD_CRON"]

# Script Configuration
START_DATE = "2024-01-01"  # Start date for data fetch
PER_PAGE = 1000  # Number of records per page
BATCH_SIZE = 50  # Number of grievance numbers to fetch details at once (API limit is 50)
DELAY_BETWEEN_REQUESTS = 1  # Delay in seconds between API calls
MAX_RETRIES = 3  # Maximum retries for failed requests
LOG_FILE = "fetch_complaints_datewise_script.log"

# Run mode: 'script' or 'cron'
# In script mode, it will continue until all data is fetched
# In cron mode, it will process one day and exit
RUN_MODE = sys.argv[1] if len(sys.argv) > 1 else "script"

# Logging Configuration
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
console.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logging.getLogger("").addHandler(console)

# State mapping
with open(resources_dir / "state_name_to_id_map.json") as f:
    STATE_NAME_TO_ID = json.load(f)

# Database Configuration (Hardcoded)
DB_HOST = "localhost"
DB_USER = "root"
DB_PASSWORD = "rootpassword123"
DB_NAME = "consumer_affairs_db_1"
DB_URL = f"mysql+mysqlconnector://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}"

engine = create_engine(DB_URL, pool_pre_ping=True, pool_recycle=1800)
Session = sessionmaker(bind=engine)

# HTTP Session with retry
http = requests.Session()
retry = Retry(total=5, backoff_factor=2, status_forcelist=[500, 502, 503, 504])
http.mount("https://", HTTPAdapter(max_retries=retry))


def map_state_name_to_code(state_name):
    """Map state name to state code using the mapping file"""
    if not state_name:
        return None
    
    state_upper = state_name.upper()
    for key, value in STATE_NAME_TO_ID.items():
        if key.upper() == state_upper:
            return int(value)
    
    logging.warning(f"State name '{state_name}' not found in mapping")
    return None


def get_last_processed_date():
    """Get the last processed date from state table"""
    session = Session()
    try:
        # Check if state table exists, if not create it
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS grievance_ingest_state (
                id INT PRIMARY KEY,
                last_processed_date DATE,
                last_complaint_reg_date DATETIME,
                last_complain_number BIGINT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
        """))
        session.commit()
        
        row = session.execute(
            text("SELECT last_processed_date FROM grievance_ingest_state WHERE id = 1")
        ).fetchone()
        
        if row and row[0]:
            last_date = row[0]
            logging.info(f"Resuming from last processed date: {last_date}")
            # Return next day
            next_date = datetime.strptime(str(last_date), "%Y-%m-%d") + timedelta(days=1)
            return next_date.strftime("%Y-%m-%d")
        else:
            # Initialize state record if not exists
            session.execute(text("""
                INSERT INTO grievance_ingest_state (id, last_processed_date, updated_at)
                VALUES (1, NULL, NOW())
                ON DUPLICATE KEY UPDATE updated_at = NOW()
            """))
            session.commit()
            logging.info(f"Starting fresh from {START_DATE}")
            return START_DATE
            
    except Exception as e:
        logging.error(f"Error getting last processed date: {e}")
        return START_DATE
    finally:
        session.close()


def update_last_processed_date(date_str):
    """Update the last processed date in state table"""
    session = Session()
    try:
        session.execute(
            text("""
                UPDATE grievance_ingest_state
                SET last_processed_date = :date,
                    updated_at = NOW()
                WHERE id = 1
            """),
            {"date": date_str}
        )
        session.commit()
        logging.info(f"Updated last processed date to: {date_str}")
    except Exception as e:
        logging.error(f"Error updating last processed date: {e}")
    finally:
        session.close()


def fetch_grievance_history_datewise(from_date, to_date, page=1, retry_count=0):
    """Fetch grievance history for a specific date"""
    payload = {
        "from_date": from_date,
        "to_date": to_date,
        "per_page": PER_PAGE,
        "page": page
    }
    
    logging.info(f"Fetching grievances from {from_date} to {to_date} (Page {page})")
    
    try:
        response = http.post(
            f"{API_BASE_URL}/grievanceHistoryDatewise",
            auth=(API_USERNAME, API_PASSWORD),
            json=payload,
            timeout=120,
            verify=False
        )
        
        # Handle 422 Unprocessable Entity (validation errors)
        if response.status_code == 422:
            logging.error(f"Validation error (422) for date range {from_date} to {to_date}: {response.text}")
            try:
                error_data = response.json()
                logging.error(f"Error details: {json.dumps(error_data, indent=2)}")
            except:
                pass
            return []
        
        response.raise_for_status()
        data = response.json()
        
        # Handle the actual response structure
        if data.get("status"):
            grievances = data.get("data", [])
            
            # Log pagination info
            pagination = data.get("pagination", {})
            logging.info(f"Page {pagination.get('current_page', page)}: Found {len(grievances)} grievances")
            if pagination.get("next_page"):
                logging.info(f"Next page available: {pagination.get('next_page')}")
            
            return grievances
        else:
            logging.warning(f"API returned status false: {data.get('message')}")
            return []
            
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 422:
            logging.error(f"Validation error (422): {e.response.text}")
            return []
        elif retry_count < MAX_RETRIES:
            wait_time = (retry_count + 1) * 5
            logging.warning(f"HTTP error fetching history: {e}. Retrying in {wait_time}s... (Attempt {retry_count + 1}/{MAX_RETRIES})")
            time.sleep(wait_time)
            return fetch_grievance_history_datewise(from_date, to_date, page, retry_count + 1)
        else:
            logging.error(f"Failed to fetch history after {MAX_RETRIES} attempts: {e}")
            raise
            
    except requests.exceptions.RequestException as e:
        if retry_count < MAX_RETRIES:
            wait_time = (retry_count + 1) * 5
            logging.warning(f"Error fetching history: {e}. Retrying in {wait_time}s... (Attempt {retry_count + 1}/{MAX_RETRIES})")
            time.sleep(wait_time)
            return fetch_grievance_history_datewise(from_date, to_date, page, retry_count + 1)
        else:
            logging.error(f"Failed to fetch history after {MAX_RETRIES} attempts: {e}")
            raise


def fetch_grievance_details(grievance_numbers, retry_count=0):
    """Fetch detailed information for multiple grievances (max 50 per API call)"""
    # Join grievance numbers as comma-separated string
    grievance_nos = ",".join(map(str, grievance_numbers))
    
    payload = {
        "grievanceno": grievance_nos
    }
    
    logging.info(f"Fetching details for {len(grievance_numbers)} grievances")
    
    try:
        response = http.post(
            f"{API_BASE_URL}/grievanceDetails",
            auth=(API_USERNAME, API_PASSWORD),
            json=payload,
            timeout=120,
            verify=False
        )
        
        # Handle 422 Unprocessable Entity
        if response.status_code == 422:
            logging.error(f"Validation error (422) for grievance details: {response.text}")
            try:
                error_data = response.json()
                logging.error(f"Error details: {json.dumps(error_data, indent=2)}")
            except:
                pass
            return []
        
        response.raise_for_status()
        data = response.json()
        
        if data.get("status"):
            # Use the correct field name from the API response
            details = data.get("data", [])
            if not details:
                # Fallback to check if it's using different field name
                details = data.get("basicGrievanceDetails", [])
            
            logging.info(f"Successfully fetched details for {len(details)} grievances")
            return details
        else:
            logging.warning(f"API returned status false: {data.get('message')}")
            return []
            
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 422:
            logging.error(f"Validation error (422): {e.response.text}")
            return []
        elif retry_count < MAX_RETRIES:
            wait_time = (retry_count + 1) * 5
            logging.warning(f"HTTP error fetching details: {e}. Retrying in {wait_time}s... (Attempt {retry_count + 1}/{MAX_RETRIES})")
            time.sleep(wait_time)
            return fetch_grievance_details(grievance_numbers, retry_count + 1)
        else:
            logging.error(f"Failed to fetch details after {MAX_RETRIES} attempts: {e}")
            return []
            
    except requests.exceptions.RequestException as e:
        if retry_count < MAX_RETRIES:
            wait_time = (retry_count + 1) * 5
            logging.warning(f"Error fetching details: {e}. Retrying in {wait_time}s... (Attempt {retry_count + 1}/{MAX_RETRIES})")
            time.sleep(wait_time)
            return fetch_grievance_details(grievance_numbers, retry_count + 1)
        else:
            logging.error(f"Failed to fetch details after {MAX_RETRIES} attempts: {e}")
            return []


def check_existing_complaints(session, complaint_numbers):
    """Check which complaints already exist in the database"""
    if not complaint_numbers:
        return set()
    
    try:
        placeholders = ', '.join([f':id{i}' for i in range(len(complaint_numbers))])
        params = {f'id{i}': num for i, num in enumerate(complaint_numbers)}
        
        result = session.execute(
            text(f"SELECT complainNumber FROM tblcomplaints WHERE complainNumber IN ({placeholders})"),
            params
        ).fetchall()
        
        existing = {row[0] for row in result}
        logging.info(f"Found {len(existing)}/{len(complaint_numbers)} existing complaints in database")
        return existing
        
    except Exception as e:
        logging.error(f"Error checking existing complaints: {e}")
        return set()


def upsert_complaint(session, detail_info):
    """Insert or update a single complaint with all available data"""
    try:
        # Try to get grievanceNumber or complainNumber
        grievance_number = detail_info.get("grievanceNumber") or detail_info.get("complainNumber")
        if not grievance_number:
            logging.warning("Skipping complaint without grievanceNumber/complainNumber")
            return False
        
        # Map state name to code
        state_code = None
        state_name = detail_info.get("stateName")
        if state_name:
            state_code = map_state_name_to_code(state_name)
        
        complaint_data = {
            "complainNumber": grievance_number,
            "userId": detail_info.get("userId", 0),
            "userEmailId": detail_info.get("emailId"),
            "userContactNumber": detail_info.get("mbileNumber") or detail_info.get("mobileNumber"),
            "complaintDetails": detail_info.get("grievanceDetails"),
            "convergenceCompanyName": detail_info.get("converganceCompanyName"),
            "nonConvergenceCompanyName": detail_info.get("nonCoverganeceCompanyName"),
            "complaintMode": detail_info.get("grievanceMode"),
            "complaintStatus": detail_info.get("grievanceStatus"),
            "complaintRegDate": detail_info.get("complaintRegDate"),
            "agentRemark": detail_info.get("agentRemark"),
            "userComment": detail_info.get("userComment"),
            "userCommentDate": detail_info.get("userCommentDate"),
            "docketType": detail_info.get("docketType"),
            "grievanceclassification": detail_info.get("grievanceClassification"),
            "productValue": detail_info.get("grivanceAmount") or detail_info.get("productValue"),
            "supportDoc1": detail_info.get("supportDoc1"),
            "supportDoc2": detail_info.get("supportDoc2"),
            "supportDoc3": detail_info.get("supportDoc3"),
            "fop": detail_info.get("frequentlyOccuredProblem"),
            "pgDocketNumber": detail_info.get("pgDocketNumber"),
            "agencyDetails": detail_info.get("agencyDetails"),
            "stateCode": state_code,
            "sectorName": detail_info.get("sectorName"),
            "categoryName": detail_info.get("categoryName"),
            "purchaseCity": detail_info.get("purchaseCity"),
            "grievancEexpectation": detail_info.get("grievancEexpectation"),
            "companyRegisteredGirvance": detail_info.get("companyRegisteredGirvance"),
            "companyGrievanceNo": detail_info.get("companyGrievanceNo"),
            "companyGrivanceNoReasons": detail_info.get("companyGrivanceNoReasons"),
            "gstInfo": detail_info.get("gstInfo")
        }
        
        # Filter out None values
        complaint_data = {k: v for k, v in complaint_data.items() if v is not None}
        
        columns = list(complaint_data.keys())
        values_placeholders = [f":{k}" for k in columns]
        
        # Build update clauses (all columns except primary key)
        update_clauses = [f"{k} = VALUES({k})" for k in columns if k != "complainNumber"]
        update_clauses.append("lastUpdationDate = CURRENT_TIMESTAMP")
        
        query = f"""
            INSERT INTO tblcomplaints (
                {', '.join(columns)}
            ) VALUES (
                {', '.join(values_placeholders)}
            )
            ON DUPLICATE KEY UPDATE
                {', '.join(update_clauses)}
        """
        
        session.execute(text(query), complaint_data)
        return True
        
    except Exception as e:
        logging.error(f"Error upserting complaint {grievance_number}: {e}")
        return False


def upsert_user(session, detail_info):
    """Insert or update user details in tblregistration"""
    try:
        user_id = detail_info.get("userId")
        if not user_id:
            return False
        
        # Get names
        first_name = detail_info.get("firstName")
        last_name = detail_info.get("lastName")
        
        # Map state name to code
        state_code = None
        state_name = detail_info.get("stateName")
        if state_name:
            state_code = map_state_name_to_code(state_name)
        
        user_data = {
            "userId": user_id,
            "firstName": first_name,
            "lastName": last_name,
            "mobNumber": detail_info.get("mbileNumber") or detail_info.get("mobileNumber"),
            "emailId": detail_info.get("emailId"),
            "stateCode": state_code
        }
        
        # Filter out None values
        user_data = {k: v for k, v in user_data.items() if v is not None}
        
        columns = list(user_data.keys())
        values_placeholders = [f":{k}" for k in columns]
        
        # Build update clauses (all columns except primary key)
        update_clauses = [f"{k} = VALUES({k})" for k in columns if k != "userId"]
        update_clauses.append("updationDate = CURRENT_TIMESTAMP")
        
        query = f"""
            INSERT INTO tblregistration (
                {', '.join(columns)}
            ) VALUES (
                {', '.join(values_placeholders)}
            )
            ON DUPLICATE KEY UPDATE
                {', '.join(update_clauses)}
        """
        
        session.execute(text(query), user_data)
        return True
        
    except Exception as e:
        logging.error(f"Error upserting user {user_id}: {e}")
        return False


def process_day_data(date_str):
    """Process all complaints for a specific day"""
    from_datetime = f"{date_str} 00:00:00"
    to_datetime = f"{date_str} 23:59:59"
    
    logging.info(f"{'='*60}")
    logging.info(f"Processing date: {date_str}")
    logging.info(f"{'='*60}")
    
    session = Session()
    total_processed = 0
    total_skipped = 0
    total_failed = 0
    
    try:
        # Fetch all grievances for this day (pagination handled)
        page = 1
        all_grievances = []
        
        while True:
            grievances = fetch_grievance_history_datewise(from_datetime, to_datetime, page)
            
            if not grievances:
                logging.info(f"No more grievances found on page {page}")
                break
            
            all_grievances.extend(grievances)
            logging.info(f"Fetched {len(grievances)} grievances from page {page}. Total so far: {len(all_grievances)}")
            
            # Check if there are more pages (assuming API returns less than PER_PAGE when done)
            if len(grievances) < PER_PAGE:
                break
            
            page += 1
            time.sleep(DELAY_BETWEEN_REQUESTS)
        
        if not all_grievances:
            logging.info(f"No grievances found for date {date_str}")
            # Still update the state to move to next day
            update_last_processed_date(date_str)
            return True
        
        logging.info(f"Total grievances fetched for {date_str}: {len(all_grievances)}")
        
        # Extract grievance numbers (try both field names)
        grievance_numbers = []
        for g in all_grievances:
            num = g.get("grievanceNumber") or g.get("complainNumber")
            if num:
                grievance_numbers.append(num)
        
        # Check which complaints already exist
        existing_complaints = check_existing_complaints(session, grievance_numbers)
        
        # Filter out existing complaints
        new_grievances = []
        for g in all_grievances:
            num = g.get("grievanceNumber") or g.get("complainNumber")
            if num and num not in existing_complaints:
                new_grievances.append(g)
        
        if not new_grievances:
            logging.info(f"All {len(all_grievances)} grievances already exist in database. Skipping...")
            total_skipped = len(all_grievances)
        else:
            logging.info(f"Processing {len(new_grievances)} new grievances (skipping {len(existing_complaints)} existing)")
            
            # Process grievances in batches (max 50 per API call)
            new_grievance_numbers = []
            for g in new_grievances:
                num = g.get("grievanceNumber") or g.get("complainNumber")
                if num:
                    new_grievance_numbers.append(num)
            
            for i in range(0, len(new_grievance_numbers), BATCH_SIZE):
                batch = new_grievance_numbers[i:i+BATCH_SIZE]
                batch_num = i//BATCH_SIZE + 1
                
                logging.info(f"Processing batch {batch_num} ({len(batch)} grievances)")
                
                # Fetch details for this batch
                details_list = fetch_grievance_details(batch)
                
                if not details_list:
                    logging.warning(f"No details returned for batch {batch_num}")
                    total_failed += len(batch)
                    continue
                
                # Create a map for quick lookup
                details_map = {}
                for d in details_list:
                    num = d.get("grievanceNumber") or d.get("complainNumber")
                    if num:
                        details_map[num] = d
                
                # Process each grievance
                for grievance_no in batch:
                    try:
                        detail_info = details_map.get(grievance_no)
                        
                        if not detail_info:
                            logging.warning(f"No details found for grievance {grievance_no}")
                            total_failed += 1
                            continue
                        
                        # Upsert complaint
                        if upsert_complaint(session, detail_info):
                            # Upsert user if userId exists
                            if detail_info.get("userId"):
                                upsert_user(session, detail_info)
                            
                            total_processed += 1
                        else:
                            total_failed += 1
                        
                        # Commit periodically
                        if total_processed % 50 == 0:
                            session.commit()
                            logging.info(f"Progress: Processed {total_processed}, Failed {total_failed}, Skipped {total_skipped}")
                    
                    except Exception as e:
                        logging.error(f"Error processing grievance {grievance_no}: {e}")
                        total_failed += 1
                        continue
                
                # Commit after each batch
                session.commit()
                logging.info(f"Batch {batch_num} completed. Progress: Processed {total_processed}, Failed {total_failed}, Skipped {len(existing_complaints)}")
                
                # Delay between batches
                time.sleep(DELAY_BETWEEN_REQUESTS)
        
        # Final commit
        session.commit()
        
        # Update state to mark this day as processed
        update_last_processed_date(date_str)
        
        logging.info(f"{'='*60}")
        logging.info(f"Completed {date_str}: Processed {total_processed}, Failed {total_failed}, Skipped {len(existing_complaints)}")
        logging.info(f"{'='*60}")
        
        return True
        
    except Exception as e:
        logging.error(f"Error processing day {date_str}: {e}")
        session.rollback()
        return False
    finally:
        session.close()


def main():
    """Main function to orchestrate the data fetch"""
    logging.info(f"{'#'*60}")
    logging.info(f"Starting Grievance Data Fetch - Mode: {RUN_MODE}")
    logging.info(f"{'#'*60}")
    
    current_date = datetime.strptime(get_last_processed_date(), "%Y-%m-%d")
    today = datetime.now()
    
    while current_date < today:
        date_str = current_date.strftime("%Y-%m-%d")
        
        # Process this day
        success = process_day_data(date_str)
        
        if not success:
            logging.error(f"Failed to process {date_str}. Will retry on next run.")
            # In script mode, we can retry immediately
            if RUN_MODE == "script":
                logging.info("Retrying after 30 seconds...")
                time.sleep(30)
                continue
            else:
                # In cron mode, exit and let cron retry
                break
        
        # Move to next day
        current_date += timedelta(days=1)
        
        # In cron mode, process only one day and exit
        if RUN_MODE == "cron":
            logging.info("Cron mode: Processed one day, exiting...")
            break
        
        # Small delay between days
        time.sleep(2)
    
    logging.info(f"{'#'*60}")
    logging.info(f"Grievance Data Fetch Completed")
    logging.info(f"{'#'*60}")


if __name__ == "__main__":
    main()