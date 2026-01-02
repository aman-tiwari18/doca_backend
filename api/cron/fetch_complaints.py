import logging
import requests
import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import urllib3


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://consumerhelpline.gov.in"
USERNAME = "nchadmin"   
PASSWORD = "Nch@iit#2025"   

PER_PAGE = 1000
BACKFILL_START_DATE = "2025-09-01"
LOG_FILE = "cron_fetch.log"
DATE_CHUNK_DAYS = 10  # Fetch 10 days at a time

FETCH_DETAILS = False  
DELAY_BETWEEN_REQUESTS = 2.0 
MAX_RETRIES_ON_RATE_LIMIT = 3
RATE_LIMIT_BACKOFF = 30 


logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

resources_dir = Path(__file__).resolve().parents[2] / "resources"
with open(resources_dir / "config.json") as f:
    config = json.load(f)

with open(resources_dir / "state_name_to_id_map.json") as f:
    STATE_NAME_TO_ID = json.load(f)

db = config["DB"]
DB_URL = f"mysql+mysqlconnector://{db['USER']}:{db['PWD']}@{db['HOST']}/{db['NAME']}"

engine = create_engine(DB_URL, pool_pre_ping=True, pool_recycle=1800)
Session = sessionmaker(bind=engine)

http = requests.Session()
retry = Retry(total=3, backoff_factor=2, status_forcelist=[500, 502, 503, 504])
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

            from_date = last_date.strftime("%Y-%m-%d")

        to_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return from_date, to_date

    finally:
        session.close()


def fetch_grievance_history(from_date, to_date, page=1, retry_count=0):
    """Fetch grievance history from the API for a specific page with rate limit handling"""
    payload = {
        "from_date": from_date,
        "to_date": to_date,
        "per_page": PER_PAGE,
        "page": page
    }

    logging.info(f"Fetching grievances from {from_date} to {to_date} (Page {page})")

    try:
        response = http.post(
            f"{BASE_URL}/ws/prod/api2.0/public/api/grievanceHistoryDatewise",
            auth=(USERNAME, PASSWORD),
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=120,
            verify=False
        )
        
        if response.status_code == 429:
            if retry_count < MAX_RETRIES_ON_RATE_LIMIT:
                wait_time = RATE_LIMIT_BACKOFF * (2 ** retry_count)
                logging.warning(f"Rate limited fetching history. Waiting {wait_time}s before retry {retry_count + 1}/{MAX_RETRIES_ON_RATE_LIMIT}")
                time.sleep(wait_time)
                return fetch_grievance_history(from_date, to_date, page, retry_count + 1)
            else:
                logging.error("Max retries exceeded for history fetch due to rate limiting")
                response.raise_for_status() # Raise error to be caught by caller

        response.raise_for_status()
        return response.json()
    except Exception as e:
        # If it's not a 429 (handled above) or we ran out of retries
        raise e


def main():
    logging.info("=== Grievance fetch job started ===")
    logging.info(f"Configuration: FETCH_DETAILS={FETCH_DETAILS}, DELAY={DELAY_BETWEEN_REQUESTS}s, PER_PAGE={PER_PAGE}, DATE_CHUNK={DATE_CHUNK_DAYS} days")
    
    if FETCH_DETAILS:
        logging.info("Running in DETAILED mode - will fetch full details for each complaint (slower)")
    else:
        logging.info("Running in BASIC mode - will only insert basic complaint data (faster)")

    if not all([BASE_URL, USERNAME, PASSWORD]):
        logging.error("Missing API credentials or BASE_URL")
        return

    try:
        # Determine overall date range
        start_date_str, final_end_date_str = get_date_range()
        
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
        final_end_date = datetime.strptime(final_end_date_str, "%Y-%m-%d")
        
        current_date = start_date

        while current_date <= final_end_date:
            # Calculate chunk end date
            chunk_end_date = current_date + timedelta(days=DATE_CHUNK_DAYS - 1)
            
            # Cap at final end date
            if chunk_end_date > final_end_date:
                chunk_end_date = final_end_date
            
            from_date = current_date.strftime("%Y-%m-%d")
            to_date = chunk_end_date.strftime("%Y-%m-%d")
            
            logging.info(f"--- Processing date range: {from_date} to {to_date} ---")
            
            current_page = 1
            total_processed_in_chunk = 0
            total_pages_in_chunk = 0

            while True:
                # Fetch grievance history for current page
                try:
                    response_data = fetch_grievance_history(from_date, to_date, current_page)
                    history_items = response_data.get('data', [])
                    
                    if not history_items:
                        logging.info(f"No more complaints found on page {current_page} for range {from_date} to {to_date}.")
                        break
                    
                    total_pages_in_chunk += 1
                    
                    # Process and insert complaints
                    process_complaints(history_items)
                    total_processed_in_chunk += len(history_items)
                    
                    # Check pagination
                    pagination = response_data.get("pagination", {})
                    next_page_url = pagination.get("next_page")
                    
                    if not next_page_url:
                        logging.info(f"Reached last page ({current_page}) for range {from_date} to {to_date}.")
                        break
                    
                    logging.info(f"Moving to next page... (Processed {total_processed_in_chunk} records in this chunk)")
                    current_page += 1
                    time.sleep(2) # Increased delay between pages
                    
                except Exception as e:
                    logging.error(f"Error fetching page {current_page} for range {from_date} to {to_date}: {e}")
                    # Wait a bit before moving to next chunk if we failed hard
                    time.sleep(10)
                    break

            logging.info(f"Completed range {from_date} to {to_date}. Processed {total_processed_in_chunk} records.")
            
            # Move to next chunk
            current_date = chunk_end_date + timedelta(days=1)
            
            # Delay between chunks to avoid rate limiting
            time.sleep(5)
        
        logging.info("=== Grievance fetch job completed ===")
        
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

        if response.status_code == 429:
            if retry_count < MAX_RETRIES_ON_RATE_LIMIT:
                wait_time = RATE_LIMIT_BACKOFF * (2 ** retry_count)
                logging.warning(f"Rate limited for grievance {grievance_number}. Waiting {wait_time}s before retry {retry_count + 1}/{MAX_RETRIES_ON_RATE_LIMIT}")
                time.sleep(wait_time)
                return fetch_grievance_details(grievance_number, retry_count + 1)
            else:
                logging.error(f"Max retries exceeded for grievance {grievance_number} due to rate limiting")
                return None
        
        if response.status_code == 401:
            logging.error(f"Authentication failed for grievance {grievance_number}")
            return None

        response.raise_for_status()
        data = response.json()
        
        if data.get("status") is True and data.get("basicGrievanceDetails"):
            return data
        
        elif data.get("status") is False:
            message = data.get("message", "Unknown")
            logging.debug(f"No details available for grievance {grievance_number}: {message}")
            return None
        
        else:
            logging.warning(f"Unexpected response format for grievance {grievance_number}")
            return None

    except Exception as e:
        logging.error(f"Failed to fetch details for grievance {grievance_number}: {str(e)}")
        return None



from sqlalchemy import text


def safe_update_dict(target: dict, source: dict, mapping: dict):
    """
    Update target dict from source dict using mapping
    without overwriting existing values with None.
    """
    for target_key, source_key in mapping.items():
        value = source.get(source_key)
        if value is not None:
            target[target_key] = value


def fetch_company_status(complain_number):
    """
    Calls the companyRemarkHistory API and returns the latest companyStatus.
    Returns None if no updates.
    """
    try:
        payload = {"complainNumber": complain_number}
        response = http.post(
            f"{BASE_URL}/ws/prod/api2.0/public/api/companyRemarkHistory",
            auth=(USERNAME, PASSWORD),
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10,
            verify=False
        )
        
        if response.status_code == 429:
            logging.warning(f"Rate limited fetching company status for {complain_number}")
            return None
            
        response.raise_for_status()
        data = response.json()
        
        remarks = data.get("grievanceUpdatedDetails", [])
        if not remarks:
            return None

        remarks.sort(key=lambda x: datetime.strptime(x.get("postingDate", "1970-01-01 00:00:00"), "%Y-%m-%d %H:%M:%S"), reverse=True)
        latest_remark = remarks[0]

        return latest_remark.get("complaintStatus")

    except Exception as e:
        logging.error(f"Error fetching companyStatus for {complain_number}: {e}")
        return None


def upsert_complaint(session, history_item, details=None):
    """
    Insert or update a single complaint with all available data
    """
    complaint_data = {
        "complainNumber": history_item.get("complainNumber"),
        "userId": 0,  # Default for API-fetched complaints
        "sectorCode": history_item.get("sectorCode"),
        "categoryCode": history_item.get("categoryCode"),
        "complaintStatus": history_item.get("grievanceStatus"),
        "complaintRegDate": history_item.get("complaintRegDate"),
    }


    state_name = history_item.get("stateName")
    if state_name:
        state_code = map_state_name_to_code(state_name)
        if state_code:
            complaint_data["stateCode"] = state_code


    if details and details.get("basicGrievanceDetails"):
        detail_info = details["basicGrievanceDetails"][0]

        field_mapping = {
            "userId": "userId",
            "userEmailId": "emailId",
            "userContactNumber": "mbileNumber",
            "complaintDetails": "grievanceDetails",
            "converganceCompanyName": "converganceCompanyName",
            "nonConverganceCompanyName": "nonCoverganeceCompanyName",
            "complaintMode": "grievanceMode",
            "agentRemark": "agentRemark",
            "userComment": "userComment",
            "userCommentDate": "userCommentDate",
            "govtDepartment": "govtDepartment",
            "docketType": "docketType",
            "grievanceclassification": "grievanceClassification",
            "productValue": "grivanceAmount",
            "supportDoc1": "supportDoc1",
            "supportDoc2": "supportDoc2",
            "supportDoc3": "supportDoc3",
            "stateName": "stateName",
            "fop" : "frequentlyOccuredProblem",
            "pgDocketNumber" : "pgDocketNumber",
            "agencyDetails" : "agencyDetails"
        }

        if detail_info.get("userId") is not None:
            complaint_data["userId"] = detail_info.get("userId")


        safe_update_dict(complaint_data, detail_info, field_mapping)


        detail_state_name = detail_info.get("stateName")
        if detail_state_name:
            detail_state_code = map_state_name_to_code(detail_state_name)
            if detail_state_code:
                complaint_data["stateCode"] = detail_state_code

    columns = []
    values_placeholders = []
    update_clauses = []
    params = {}

    for key, value in complaint_data.items():
        if value is not None:
            columns.append(key)
            values_placeholders.append(f":{key}")
            params[key] = value

            if key != "complainNumber":
                update_clauses.append(f"{key} = VALUES({key})")


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

    session.execute(text(query), params)


def process_complaints(history_items):
    """Process and insert/update complaints with optional detailed information"""
    session = Session()
    processed = 0
    failed = 0
    skipped = 0
    details_fetched = 0
    
    # Extract complaint numbers to check existence
    complaint_numbers = [item.get("complainNumber") for item in history_items if item.get("complainNumber")]
    existing_complaints = set()
    
    if complaint_numbers:
        try:
            # Check which complaints already exist in DB
            placeholders = ', '.join([':id' + str(i) for i in range(len(complaint_numbers))])
            params = {f'id{i}': num for i, num in enumerate(complaint_numbers)}
            
            result = session.execute(
                text(f"SELECT complainNumber FROM tblcomplaints WHERE complainNumber IN ({placeholders})"),
                params
            ).fetchall()
            
            existing_complaints = {row[0] for row in result}
            logging.info(f"Found {len(existing_complaints)} existing complaints in this batch of {len(complaint_numbers)}. Skipping them.")
            
        except Exception as e:
            logging.error(f"Failed to check existing complaints: {e}")
            # If check fails, assume none exist to be safe (or empty set)

    try:
        for item in history_items:
            try:
                complaint_number = item.get("complainNumber")
                if not complaint_number:
                    logging.warning("Skipping item without complaint number")
                    skipped += 1
                    continue
                
                # Skip if already exists
                if complaint_number in existing_complaints:
                    skipped += 1
                    continue

                details = None
                company_status = None
                

                if FETCH_DETAILS:
                    details = fetch_grievance_details(complaint_number)
                    if details:
                        details_fetched += 1
                    
                    time.sleep(DELAY_BETWEEN_REQUESTS)
                
                upsert_complaint(session, item, details)
                processed += 1

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
