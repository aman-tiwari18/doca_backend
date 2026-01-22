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

resources_dir = Path(__file__).resolve().parents[2] / "resources"
with open(resources_dir / "config.json") as f:
    config = json.load(f)

BASE_URL = config["BASE_URL_CRON"]
USERNAME = config["USERNAME_CRON"]   
PASSWORD = config["PASSWORD_CRON"]   

PER_PAGE = 1000
BACKFILL_START_DATE = "2026-01-01 00:00:00"
BACKFILL_END_DATE = "2026-01-14 23:59:59"
LOG_FILE = "cron_fetch.log"

FETCH_DETAILS = False  
DELAY_BETWEEN_REQUESTS = 0.5
MAX_RETRIES_ON_RATE_LIMIT = 5
RATE_LIMIT_BACKOFF = 30 


logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)



with open(resources_dir / "state_name_to_id_map.json") as f:
    STATE_NAME_TO_ID = json.load(f)

db = config["DB"]
DB_URL = f"mysql+mysqlconnector://{db['USER']}:{db['PWD']}@{db['HOST']}/{db['NAME']}"

engine = create_engine(DB_URL, pool_pre_ping=True, pool_recycle=1800)
Session = sessionmaker(bind=engine)

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


def get_date_range():
    """
    Decide date range based on grievance_ingest_state table.
    """
    session = Session()
    try:
        # Check state table
        row = session.execute(
            text("SELECT last_complaint_reg_date FROM grievance_ingest_state WHERE id = 1")
        ).fetchone()

        if row and row[0]:
            last_reg_date_str = str(row[0])
            logging.info(f"Found existing state: last_complaint_reg_date = {last_reg_date_str}")
            
            # If the last processed date is older than our start date, it means we haven't started this batch
            # or we are starting fresh for this period.
            # However, since we are fetching descending, if we have processed some 2026 data, 
            # last_reg_date would be e.g. 2026-01-14.
            # If last_reg_date is 2025-12-31, we start from BACKFILL_END_DATE.
            
            last_reg_date = datetime.strptime(last_reg_date_str, "%Y-%m-%d %H:%M:%S")
            start_date_dt = datetime.strptime(BACKFILL_START_DATE, "%Y-%m-%d %H:%M:%S")
            
            if last_reg_date < start_date_dt:
                logging.info("State is older than target start date. Starting from END_DATE.")
                to_date = BACKFILL_END_DATE
            else:
                logging.info("Resuming from last_complaint_reg_date.")
                to_date = last_reg_date_str
        else:
            logging.info("No state found. Starting from END_DATE.")
            to_date = BACKFILL_END_DATE

        return BACKFILL_START_DATE, to_date

    except Exception as e:
        logging.error(f"Error getting date range: {e}")
        return BACKFILL_START_DATE, BACKFILL_END_DATE
    finally:
        session.close()


def update_ingest_state(session, complain_number, reg_date):
    """
    Update the grievance_ingest_state table with the latest processed complaint info.
    Only updates the existing row with id=1, does not insert new rows.
    """
    try:
        query = """
            UPDATE grievance_ingest_state
            SET last_complain_number = :num,
                last_complaint_reg_date = :date,
                updated_at = NOW()
            WHERE id = 1
        """
        session.execute(text(query), {"num": complain_number, "date": reg_date})
        session.commit()
    except Exception as e:
        logging.error(f"Failed to update ingest state: {e}")


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
                response.raise_for_status() 

        response.raise_for_status()
        return response.json()
    except Exception as e:
        if retry_count < MAX_RETRIES_ON_RATE_LIMIT:
             wait_time = 10 * (retry_count + 1)
             logging.warning(f"Error fetching history: {e}. Retrying in {wait_time}s...")
             time.sleep(wait_time)
             return fetch_grievance_history(from_date, to_date, page, retry_count + 1)
        raise e


def main():
    logging.info("=== Grievance fetch job started ===")
    logging.info(f"Configuration: FETCH_DETAILS={FETCH_DETAILS}, DELAY={DELAY_BETWEEN_REQUESTS}s, PER_PAGE={PER_PAGE}")
    
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
                time.sleep(2) 
                
            except Exception as e:
                logging.error(f"Error fetching page {current_page} for range {from_date} to {to_date}: {e}")
                time.sleep(30)
                # Retry the same page loop
                continue
        
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

    try:
        last_processed_item = None
        for item in history_items:
            try:
                complaint_number = item.get("complainNumber")
                if not complaint_number:
                    skipped += 1
                    continue
                
                if complaint_number in existing_complaints:
                    skipped += 1
                    # Even if skipped, we track it as processed for state update purposes
                    # because we have moved past it in the descending list
                    last_processed_item = item
                    continue

                upsert_complaint(session, item, None)
                processed += 1
                last_processed_item = item

                if processed % 50 == 0:
                    session.commit()
                    logging.info(f"Processed {processed} complaints so far...")
                    # Update state periodically
                    if last_processed_item:
                         update_ingest_state(session, last_processed_item.get("complainNumber"), last_processed_item.get("complaintRegDate"))

            except Exception as e:
                logging.error(f"Failed to process complaint {complaint_number}: {str(e)}")
                failed += 1
                continue

        session.commit()
        
        # Update state at the end of the batch
        if last_processed_item:
            update_ingest_state(session, last_processed_item.get("complainNumber"), last_processed_item.get("complaintRegDate"))
        
        logging.info(f"Successfully processed {processed} complaints, {failed} failed, {skipped} skipped")

    except Exception as e:
        session.rollback()
        logging.exception(f"Database operation failed: {str(e)}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
