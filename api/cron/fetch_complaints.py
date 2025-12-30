import os
import logging
import requests
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ================= CONFIG =================

BASE_URL = "https://consumerhelpline.gov.in"
USERNAME = "nchadmin"
PASSWORD = "Nch@iit#2025"
DB_URL = os.getenv("DB_URL")

LOG_FILE = "/var/log/consumer_affairs_cron.log"
FETCH_WINDOW_MINUTES = 15     # safe buffer for 10-min cron
PER_PAGE = 1000

# =========================================

# ----------- LOGGING ---------------------
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
# -----------------------------------------

# ----------- DB ---------------------------
engine = create_engine(
    DB_URL,
    pool_pre_ping=True,
    pool_recycle=1800
)
Session = sessionmaker(bind=engine)
# -----------------------------------------

# ----------- HTTP SESSION ----------------
http = requests.Session()
retries = Retry(
    total=3,
    backoff_factor=2,
    status_forcelist=[500, 502, 503, 504]
)
http.mount("https://", HTTPAdapter(max_retries=retries))
# -----------------------------------------


def fetch_grievances():
    """Fetch grievances from last FETCH_WINDOW_MINUTES"""
    now = datetime.utcnow()
    from_date = (now - timedelta(minutes=FETCH_WINDOW_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")
    to_date = now.strftime("%Y-%m-%d %H:%M:%S")

    payload = {
        "from_date": from_date,
        "to_date": to_date,
        "per_page": PER_PAGE
    }

    logging.info(f"Fetching grievances from {from_date} to {to_date}")

    response = http.post(
        f"{BASE_URL}/ws/prod/api2.0/public/api/grievanceHistoryDatewise",
        auth=(USERNAME, PASSWORD),
        json=payload,
        timeout=30
    )

    response.raise_for_status()
    return response.json()


def upsert_complaints(data):
    session = Session()
    inserted = 0

    try:
        for item in data.get("data", []):
            query = text("""
                INSERT INTO tblcomplaints (
                    complainNumber,
                    sectorCode,
                    categoryCode,
                    complaintStatus,
                    complaintRegDate,
                    stateCode,
                    complaintDetails,
                    converganceCompanyName
                ) VALUES (
                    :complainNumber,
                    :sectorCode,
                    :categoryCode,
                    :complaintStatus,
                    :complaintRegDate,
                    :stateCode,
                    :complaintDetails,
                    :companyName
                )
                ON DUPLICATE KEY UPDATE
                    complaintStatus = VALUES(complaintStatus),
                    lastUpdationDate = CURRENT_TIMESTAMP
            """)

            session.execute(query, {
                "complainNumber": item.get("complainNumber"),
                "sectorCode": item.get("sectorCode"),
                "categoryCode": item.get("categoryCode"),
                "complaintStatus": item.get("status"),
                "complaintRegDate": item.get("grievanceDate"),
                "stateCode": item.get("stateCode"),
                "complaintDetails": item.get("grievanceDetails"),
                "companyName": item.get("companyName"),
            })

            inserted += 1

        session.commit()
        logging.info(f"Processed {inserted} complaints")

    except Exception:
        session.rollback()
        logging.exception("Database upsert failed")
        raise
    finally:
        session.close()


def main():
    logging.info("=== Grievance cron started ===")

    if not all([BASE_URL, USERNAME, PASSWORD, DB_URL]):
        logging.error("Missing environment variables")
        return

    try:
        data = fetch_grievances()
        upsert_complaints(data)
        logging.info("=== Grievance cron completed successfully ===")
    except Exception:
        logging.exception("Grievance cron failed")


if __name__ == "__main__":
    main()
