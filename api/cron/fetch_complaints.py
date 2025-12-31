import logging
import requests
import json
import time
from datetime import datetime
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import urllib3

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ================= CONFIG =================

BASE_URL = "https://consumerhelpline.gov.in"
USERNAME = "nchadmin"   
PASSWORD = "Nch@iit#2025"   

PER_PAGE = 1000
BACKFILL_START_DATE = "2025-01-01"
LOG_FILE = "cron_fetch.log"

# Rate limiting configuration
FETCH_DETAILS = False  # Set to True to fetch detailed info (slower but more complete)
DELAY_BETWEEN_REQUESTS = 2.0  # Seconds between API calls (increased from 0.1)
MAX_RETRIES_ON_RATE_LIMIT = 3
RATE_LIMIT_BACKOFF = 30  # Seconds to wait when rate limited

# =========================================

# ----------- LOGGING ---------------------
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
# -----------------------------------------

# ----------- LOAD DB CONFIG & MAPPINGS ---
resources_dir = Path(__file__).resolve().parents[2] / "resources"
with open(resources_dir / "config.json") as f:
    config = json.load(f)

# Load state name to ID mapping
with open(resources_dir / "state_name_to_id_map.json") as f:
    STATE_NAME_TO_ID = json.load(f)

db = config["DB"]
DB_URL = f"mysql+mysqlconnector://{db['USER']}:{db['PWD']}@{db['HOST']}/{db['NAME']}"

# ----------- DB --------------------------
engine = create_engine(DB_URL, pool_pre_ping=True, pool_recycle=1800)
Session = sessionmaker(bind=engine)

# ----------- HTTP SESSION ----------------
http = requests.Session()
retry = Retry(total=3, backoff_factor=2, status_forcelist=[500, 502, 503, 504])
http.mount("https://", HTTPAdapter(max_retries=retry))

# =========================================


def map_state_name_to_code(state_name):
    """Map state name to state code using the mapping file"""
    if not state_name:
        return None
    
    # Try exact match first (case-insensitive)
    state_upper = state_name.upper()
    for key, value in STATE_NAME_TO_ID.items():
        if key.upper() == state_upper:
            return int(value)
    
    logging.warning(f"State name '{state_name}' not found in mapping")
    return None


def get_date_range():
    """
    Decide date range:
    - If DB empty → full backfill
    - Else → incremental fetch from last complaint date
    """
    session = Session()
    try:
        count = session.execute(
            text("SELECT COUNT(*) FROM tblcomplaints")
        ).scalar()

        if count == 0:
            logging.info("Database empty → running full backfill")
            from_date = BACKFILL_START_DATE
        else:
            last_date = session.execute(
                text("SELECT MAX(complaintRegDate) FROM tblcomplaints")
            ).scalar()

            # Convert timestamp to date string
            from_date = last_date.strftime("%Y-%m-%d")

        to_date = datetime.utcnow().strftime("%Y-%m-%d")
        return from_date, to_date

    finally:
        session.close()


def fetch_grievance_history(from_date, to_date, page=1):
    """Fetch grievance history from the API for a specific page"""
    payload = {
        "from_date": from_date,
        "to_date": to_date,
        "per_page": PER_PAGE,
        "page": page
    }

    logging.info(f"Fetching grievances from {from_date} to {to_date} (Page {page})")

    response = http.post(
        f"{BASE_URL}/ws/prod/api2.0/public/api/grievanceHistoryDatewise",
        auth=(USERNAME, PASSWORD),
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=120,
        verify=False
    )
    response.raise_for_status()
    return response.json()


def main():
    logging.info("=== Grievance fetch job started ===")
    logging.info(f"Configuration: FETCH_DETAILS={FETCH_DETAILS}, DELAY={DELAY_BETWEEN_REQUESTS}s, PER_PAGE={PER_PAGE}")
    
    if FETCH_DETAILS:
        logging.info("Running in DETAILED mode - will fetch full details for each complaint (slower)")
    else:
        logging.info("Running in BASIC mode - will only insert basic complaint data (faster)")

    if not all([BASE_URL, USERNAME, PASSWORD]):
        logging.error("Missing API credentials or BASE_URL")
        return

    try:
        # Determine date range once
        from_date, to_date = get_date_range()
        current_page = 1
        total_processed = 0
        total_pages = 0

        while True:
            # Fetch grievance history for current page
            response_data = fetch_grievance_history(from_date, to_date, current_page)
            history_items = response_data.get('data', [])
            
            if not history_items:
                logging.info(f"No more complaints found on page {current_page}.")
                break
            
            total_pages += 1
            
            # Process and insert complaints
            process_complaints(history_items)
            total_processed += len(history_items)
            
            # Check pagination
            pagination = response_data.get("pagination", {})
            next_page_url = pagination.get("next_page")
            
            if not next_page_url:
                logging.info(f"Reached last page ({current_page}). Stopping.")
                break
            
            logging.info(f"Moving to next page... (Processed {total_processed} records across {total_pages} pages so far)")
            current_page += 1
            time.sleep(1) # Small delay between pages to be nice to the API
        
        logging.info(f"=== Grievance fetch job completed. Total: {total_processed} records from {total_pages} pages ===")
        
    except Exception as e:
        logging.exception(f"Grievance fetch job failed: {str(e)}")


def fetch_grievance_details(grievance_number, retry_count=0):
    """Fetch detailed information for a specific grievance with rate limit handling"""
    try:
        payload = {"grievance_number": grievance_number}
        
        response = http.post(
            f"{BASE_URL}/ws/prod/api2.0/public/api/grievanceDetails",
            auth=(USERNAME, PASSWORD),
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=60,
            verify=False
        )

        # Handle rate limiting with exponential backoff
        if response.status_code == 429:
            if retry_count < MAX_RETRIES_ON_RATE_LIMIT:
                wait_time = RATE_LIMIT_BACKOFF * (2 ** retry_count)
                logging.warning(f"Rate limited for grievance {grievance_number}. Waiting {wait_time}s before retry {retry_count + 1}/{MAX_RETRIES_ON_RATE_LIMIT}")
                time.sleep(wait_time)
                return fetch_grievance_details(grievance_number, retry_count + 1)
            else:
                logging.error(f"Max retries exceeded for grievance {grievance_number} due to rate limiting")
                return None
        
        # Handle authentication errors
        if response.status_code == 401:
            logging.error(f"Authentication failed for grievance {grievance_number}")
            return None

        response.raise_for_status()
        data = response.json()
        
        # Handle successful response with data
        if data.get("status") is True and data.get("basicGrievanceDetails"):
            return data
        
        # Handle "No Record found" response (status: false)
        elif data.get("status") is False:
            message = data.get("message", "Unknown")
            logging.debug(f"No details available for grievance {grievance_number}: {message}")
            return None
        
        # Handle other cases where data is missing
        else:
            logging.warning(f"Unexpected response format for grievance {grievance_number}")
            return None

    except Exception as e:
        logging.error(f"Failed to fetch details for grievance {grievance_number}: {str(e)}")
        return None


def upsert_complaint(session, history_item, details=None):
    """Insert or update a single complaint with all available data"""
    
    # Start with data from history API
    complaint_data = {
        "complainNumber": history_item.get("complainNumber"),
        "userId": 0,  # Default for API-fetched complaints
        "sectorCode": history_item.get("sectorCode"),
        "categoryCode": history_item.get("categoryCode"),
        "complaintStatus": history_item.get("grievanceStatus"),
        "complaintRegDate": history_item.get("complaintRegDate"),
    }
    
    # Map state name to code
    state_name = history_item.get("stateName")
    if state_name:
        complaint_data["stateCode"] = map_state_name_to_code(state_name)
    
    # If we have detailed information, merge it
    if details and details.get("basicGrievanceDetails"):
        detail_info = details["basicGrievanceDetails"][0]
        
        # Update with detailed information
        complaint_data.update({
            "userId": detail_info.get("userId") or 0,
            "userEmailId": detail_info.get("emailId"),
            "userContactNumber": detail_info.get("mbileNumber"),
            "complaintDetails": detail_info.get("grievanceDetails"),
            "converganceCompanyName": detail_info.get("converganceCompanyName"),
            "nonConverganceCompanyName": detail_info.get("nonCoverganeceCompanyName"),
            "complaintMode": detail_info.get("grievanceMode"),
            "productValue": detail_info.get("productValue"),
            "agentRemark": detail_info.get("agentRemark"),
            "userComment": detail_info.get("userComment"),
            "userCommentDate": detail_info.get("userCommentDate"),
            "govtDepartment": detail_info.get("govtDepartment"),
            "docketType": detail_info.get("docketType"),
            "grievanceClassification": detail_info.get("grievanceClassification"),
            "grievanceExpectation": detail_info.get("grievancEexpectation"),
            "companyRegisteredGrievance": detail_info.get("companyRegisteredGirvance"),
            "grievanceAmount": detail_info.get("grivanceAmount"),
            "companyGrievanceNo": detail_info.get("companyGrievanceNo"),
            "gstInfo": detail_info.get("gstInfo"),
        })
        
        # Override state code if available in details
        detail_state_name = detail_info.get("stateName")
        if detail_state_name:
            state_code = map_state_name_to_code(detail_state_name)
            if state_code:
                complaint_data["stateCode"] = state_code
    
    # Build dynamic INSERT query based on available fields
    columns = []
    values_placeholders = []
    update_clauses = []
    params = {}

    for key, value in complaint_data.items():
        if value is not None:
            columns.append(key)
            values_placeholders.append(f":{key}")
            params[key] = value
            
            # Add to update clause (except primary key)
            if key != "complainNumber":
                update_clauses.append(f"{key} = VALUES({key})")

    # Always update lastUpdationDate
    update_clauses.append("lastUpdationDate = CURRENT_TIMESTAMP")

    # Construct the query
    query = f"""
        INSERT INTO tblcomplaints (
            {', '.join(columns)}
        ) VALUES (
            {', '.join(values_placeholders)}
        )
        ON DUPLICATE KEY UPDATE
            {', '.join(update_clauses)}
    """

    session.execute(text(query), params)


def process_complaints(history_items):
    """Process and insert/update complaints with optional detailed information"""
    session = Session()
    processed = 0
    failed = 0
    skipped = 0
    details_fetched = 0

    try:
        for item in history_items:
            try:
                complaint_number = item.get("complainNumber")
                if not complaint_number:
                    logging.warning("Skipping item without complaint number")
                    skipped += 1
                    continue

                details = None
                
                # Only fetch details if enabled
                if FETCH_DETAILS:
                    details = fetch_grievance_details(complaint_number)
                    if details:
                        details_fetched += 1
                    
                    # Add delay to avoid rate limiting
                    time.sleep(DELAY_BETWEEN_REQUESTS)
                
                # Upsert the complaint with available data
                upsert_complaint(session, item, details)
                processed += 1

                # Commit every 50 records to avoid long transactions
                if processed % 50 == 0:
                    session.commit()
                    if FETCH_DETAILS:
                        logging.info(f"Processed {processed} complaints ({details_fetched} with details) so far...")
                    else:
                        logging.info(f"Processed {processed} complaints (basic data only) so far...")

            except Exception as e:
                logging.error(f"Failed to process complaint {complaint_number}: {str(e)}")
                failed += 1
                continue

        # Final commit
        session.commit()
        
        if FETCH_DETAILS:
            logging.info(f"Successfully processed {processed} complaints ({details_fetched} with details), {failed} failed, {skipped} skipped")
        else:
            logging.info(f"Successfully processed {processed} complaints (basic data only), {failed} failed, {skipped} skipped")

    except Exception as e:
        session.rollback()
        logging.exception(f"Database operation failed: {str(e)}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
