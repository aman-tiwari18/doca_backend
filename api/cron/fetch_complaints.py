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
BACKFILL_START_DATE = "2025-09-01 00:00:00"
BACKFILL_END_DATE = "2025-12-31 23:59:59"
LOG_FILE = "cron_fetch.log"

FETCH_DETAILS = False  
DELAY_BETWEEN_REQUESTS = 0.5
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
            to_date = BACKFILL_END_DATE
        else:
            # Find the earliest date we have processed so far (within our target range)
            # We want to resume from where we left off (working backwards)
            min_date = session.execute(
                text(f"SELECT MIN(complaintRegDate) FROM tblcomplaints WHERE complaintRegDate >= '{BACKFILL_START_DATE}'")
            ).scalar()

            if min_date:
                # Resume from the earliest date we have
                to_date = min_date.strftime("%Y-%m-%d %H:%M:%S")
            else:
                # No data in our range yet, start from the end
                to_date = BACKFILL_END_DATE

        return BACKFILL_START_DATE, to_date

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
    logging.info(f"Configuration: FETCH_DETAILS={FETCH_DETAILS}, DELAY={DELAY_BETWEEN_REQUESTS}s, PER_PAGE={PER_PAGE}")
    
    if FETCH_DETAILS:
        logging.info("Running in DETAILED mode - will fetch full details for each complaint (slower)")
    else:
        logging.info("Running in BASIC mode - will only insert basic complaint data (faster)")

    if not all([BASE_URL, USERNAME, PASSWORD]):
        logging.error("Missing API credentials or BASE_URL")
        return

    try:
        # Determine overall date range
        from_date, to_date = get_date_range()
        
        logging.info(f"--- Processing date range: {from_date} to {to_date} ---")
        
        current_page = 1
        total_processed = 0
        total_pages = 0

        while True:
            # Fetch grievance history for current page
            try:
                response_data = fetch_grievance_history(from_date, to_date, current_page)
                history_items = response_data.get('data', [])
                
                if not history_items:
                    logging.info(f"No more complaints found on page {current_page} for range {from_date} to {to_date}.")
                    break
                
                total_pages += 1
                
                # Process and insert complaints
                process_complaints(history_items)
                total_processed += len(history_items)
                
                # Check pagination
                pagination = response_data.get("pagination", {})
                next_page_url = pagination.get("next_page")
                
                if not next_page_url:
                    logging.info(f"Reached last page ({current_page}) for range {from_date} to {to_date}.")
                    break
                
                logging.info(f"Moving to next page... (Processed {total_processed} records so far)")
                current_page += 1
                time.sleep(2) # Increased delay between pages
                
            except Exception as e:
                logging.error(f"Error fetching page {current_page} for range {from_date} to {to_date}: {e}")
                # Wait a bit before retrying or exiting
                time.sleep(10)
                break
        
        logging.info("=== Grievance fetch job completed ===")
        
    except Exception as e:
        logging.exception(f"Grievance fetch job failed: {str(e)}")


def fetch_grievance_details(grievance_number, sectorCode, categoryCode, retry_count=0):
    """Fetch detailed information for a specific grievance with rate limit handling"""
    try:
        payload = {
            "grievanceno": grievance_number,
            "sectorcode": sectorCode,
            "categoryCode": categoryCode

         }
        
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
                return fetch_grievance_details(grievance_number, sectorCode, categoryCode, retry_count + 1)
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
            "nonCoverganenceCompanyName": "nonCoverganeceCompanyName",
            "complaintMode": "grievanceMode",
            "agentRemark": "agentRemark",
            "userComment": "userComment",
            "userCommentDate": "userCommentDate",
            "docketType": "docketType",
            "grievanceclassification": "grievanceClassification",
            "productValue": "grivanceAmount",
            "supportDoc1": "supportDoc1",
            "supportDoc2": "supportDoc2",
            "supportDoc3": "supportDoc3",
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


def upsert_user(session, detail_info):
    """
    Insert or update user details in tblregistration
    """
    try:
        user_id = detail_info.get("userId")
        if not user_id:
            return

        # Try to get names directly first
        first_name = detail_info.get("firstName")
        last_name = detail_info.get("lastName")

        # Fallback to splitting consumerName if firstName is missing
        if not first_name:
            consumer_name = detail_info.get("consumerName", "").strip()
            if " " in consumer_name:
                first_name, last_name = consumer_name.split(" ", 1)
            else:
                first_name = consumer_name
                last_name = ""

        state_name = detail_info.get("stateName")
        state_code = None
        if state_name:
            state_code = map_state_name_to_code(state_name)

        user_data = {
            "userId": user_id,
            "firstName": first_name,
            "lastName": last_name,
            "mobNumber": detail_info.get("mbileNumber"),
            "emailId": detail_info.get("emailId"),
            "stateCode": state_code,
            "pincode": detail_info.get("pincode")
        }

        columns = []
        values_placeholders = []
        update_clauses = []
        params = {}

        for key, value in user_data.items():
            if value is not None:
                columns.append(key)
                values_placeholders.append(f":{key}")
                params[key] = value
                
                if key != "userId":
                    update_clauses.append(f"{key} = VALUES({key})")

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

        session.execute(text(query), params)

    except Exception as e:
        logging.error(f"Failed to upsert user {user_id}: {e}")


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
                sectorCode = item.get("sectorCode")
                categoryCode = item.get("categoryCode")
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
                

                # if FETCH_DETAILS:
                #     details = fetch_grievance_details(complaint_number, sectorCode, categoryCode)
                #     if details:
                #         details_fetched += 1
                #         # Update user details if available
                #         if details.get("basicGrievanceDetails"):
                #             upsert_user(session, details["basicGrievanceDetails"][0])
                #     
                #     time.sleep(DELAY_BETWEEN_REQUESTS)
                
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
