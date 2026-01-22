import json
import time
import logging
from pathlib import Path
from datetime import datetime

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import urllib3

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ================== CONFIG ==================

resources_dir = Path(__file__).resolve().parents[2] / "resources"

with open(resources_dir / "config.json") as f:
    config = json.load(f)

BASE_URL = config["BASE_URL_CRON"]
USERNAME = config["USERNAME_CRON"]   
PASSWORD = config["PASSWORD_CRON"]

BATCH_SIZE = 200
DETAIL_DELAY = 0.6
MAX_RETRIES_ON_RATE_LIMIT = 3
RATE_LIMIT_BACKOFF = 30
LOG_FILE = "details_backfill.log"

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
retry = Retry(total=3, backoff_factor=2, status_forcelist=[500, 502, 503, 504])
http.mount("https://", HTTPAdapter(max_retries=retry))


# ================== HELPERS ==================

def map_state_name_to_code(state_name):
    if not state_name:
        return None
    return STATE_NAME_TO_ID.get(state_name.upper())

def sanitize_phone(phone):
    if not phone:
        return None
    s = str(phone)
    # Truncate to 15 chars to fit in DB and avoid DataError
    if len(s) > 15:
        return s[:15]
    return s


def fetch_grievance_details(grievance_number, sectorCode, categoryCode, retry_count=0):
    payload = {
        "grievanceno": grievance_number,
        "sectorcode": sectorCode,
        "categoryCode": categoryCode
    }

    try:
        response = http.post(
            f"{BASE_URL}/ws/prod/api2.0/public/api/grievanceDetails",
            auth=(USERNAME, PASSWORD),
            json=payload,
            timeout=60,
            verify=False
        )

        if response.status_code == 429:
            if retry_count < MAX_RETRIES_ON_RATE_LIMIT:
                wait = RATE_LIMIT_BACKOFF * (2 ** retry_count)
                logging.warning(f"429 for {grievance_number}, waiting {wait}s")
                time.sleep(wait)
                return fetch_grievance_details(
                    grievance_number, sectorCode, categoryCode, retry_count + 1
                )
            return None

        response.raise_for_status()
        data = response.json()

        if data.get("status") and data.get("basicGrievanceDetails"):
            return data

        return None

    except Exception as e:
        logging.error(f"Details fetch failed for {grievance_number}: {e}")
        return None


# ================== DB OPERATIONS ==================

def get_pending_complaints(session, last_id=None):
    query = """
    SELECT complainNumber, sectorCode, categoryCode
    FROM tblcomplaints
    WHERE detailsFetched = 0
    """
    params = {"limit": BATCH_SIZE}

    if last_id:
        query += " AND complainNumber > :last_id"
        params["last_id"] = last_id

    query += " ORDER BY complainNumber LIMIT :limit"
    return session.execute(text(query), params).fetchall()


def upsert_user(session, detail):
    user_id = detail.get("userId")
    if not user_id:
        return

    state_code = map_state_name_to_code(detail.get("stateName"))

    data = {
        "userId": user_id,
        "firstName": detail.get("firstName"),
        "lastName": detail.get("lastName"),
        "mobNumber": sanitize_phone(detail.get("mbileNumber")),
        "emailId": detail.get("emailId"),
        "stateCode": state_code,
        "pincode": detail.get("pincode")
    }

    cols, vals, updates, params = [], [], [], {}

    for k, v in data.items():
        if v is not None:
            cols.append(k)
            vals.append(f":{k}")
            params[k] = v
            if k != "userId":
                updates.append(f"{k}=VALUES({k})")

    updates.append("updationDate=CURRENT_TIMESTAMP")

    query = f"""
    INSERT INTO tblregistration ({','.join(cols)})
    VALUES ({','.join(vals)})
    ON DUPLICATE KEY UPDATE {','.join(updates)}
    """

    session.execute(text(query), params)


def upsert_complaint_details(session, complain_number, details):
    detail = details["basicGrievanceDetails"][0]

    state_code = map_state_name_to_code(detail.get("stateName"))

    update_data = {
        "userId": detail.get("userId"),
        "userEmailId": detail.get("emailId"),
        "userContactNumber": sanitize_phone(detail.get("mbileNumber")),
        "complaintDetails": detail.get("grievanceDetails"),
        "converganceCompanyName" : detail.get("converganceCompanyName"),
        "nonCoverganenceCompanyName" : detail.get("nonCoverganeceCompanyName"),
        "complaintMode": detail.get("grievanceMode"),
        "agentRemark": detail.get("agentRemark"),
        "userComment": detail.get("userComment"),
        "userCommentDate" : detail.get("userCommentDate"),
        "grievanceclassification" : detail.get("grievanceClassification"),
        "docketType" : detail.get("docketType"),
        "productValue": detail.get("grivanceAmount"),
        "supportDoc1" : detail.get("supportDoc1"),
        "supportDoc2": detail.get("supportDoc2"),
        "supportDoc3" : detail.get("supportDoc3"),
        "fop" : detail.get("frequentlyOccuredProblem"),
        "pgDocketNumber" : detail.get("pgDocketNumber"),
        "agencyDetails" : detail.get("agencyDetails"),
        "stateCode": state_code,
        "detailsFetched": 1,
        "detailsFetchedAt": datetime.now()
    }

    updates, params = [], {"c": complain_number}

    for k, v in update_data.items():
        if v is not None:
            updates.append(f"{k}=:{k}")
            params[k] = v

    updates.append("lastUpdationDate=CURRENT_TIMESTAMP")

    query = f"""
    UPDATE tblcomplaints
    SET {', '.join(updates)}
    WHERE complainNumber = :c
    """

    session.execute(text(query), params)


# ================== MAIN WORKER ==================

def main():
    logging.info("=== DETAILS BACKFILL STARTED ===")

    last_id = None
    processed = 0

    while True:
        session = Session()
        try:
            rows = get_pending_complaints(session, last_id)
            if not rows:
                logging.info("No pending complaints left 🎉")
                break

            for row in rows:
                complain_number = row.complainNumber

                details = fetch_grievance_details(
                    complain_number,
                    row.sectorCode,
                    row.categoryCode
                )

                try:
                    if details:
                        upsert_complaint_details(session, complain_number, details)
                        upsert_user(session, details["basicGrievanceDetails"][0])
                    else:
                        session.execute(
                            text("""
                            UPDATE tblcomplaints
                            SET detailsFetched=1,
                                detailsFetchedAt=NOW()
                            WHERE complainNumber=:c
                            """),
                            {"c": complain_number}
                        )
                except Exception as e:
                    logging.error(f"Error processing {complain_number}: {e}")
                    # Attempt to mark as fetched so we don't get stuck on this record
                    try:
                        session.execute(
                            text("UPDATE tblcomplaints SET detailsFetched=1 WHERE complainNumber=:c"),
                            {"c": complain_number}
                        )
                    except Exception as ex:
                        logging.error(f"Failed to mark {complain_number} as skipped: {ex}")

                last_id = complain_number
                processed += 1

                if processed % 20 == 0:
                    session.commit()
                    logging.info(f"Details processed: {processed}")

                time.sleep(DETAIL_DELAY)

            session.commit()

        except Exception as e:
            session.rollback()
            logging.error(f"Batch failed at {last_id}: {e}")
            time.sleep(30)
        finally:
            session.close()

    logging.info("=== DETAILS BACKFILL COMPLETED ===")


if __name__ == "__main__":
    main()
