import json
from repository.semantic_search import semanticSearch, semanticSearchCount
from repository.keyword_search import keywordSearch
from repository.hybrid_search import hybridSearch
from typing import List, Optional
from fastapi import Query

import sys
from pathlib import Path
from fastapi import APIRouter
from datetime import datetime, timedelta

import pandas as pd
from typing import Dict
router = APIRouter(tags=["Search Features"])

# ---------------------------- Path Management ----------------------------
resources_dir = Path(__file__).resolve().parents[2] / "resources"
sys.path.append(str(resources_dir))

# ---------------------------- Import External Utilities ----------------------------
from utility import getES, getEmbed, load_config

# ---------------------------- Import Internal Utilities ----------------------------
config = load_config()
INDEX_NAME = config["ES"]["INDEX_NAME"]

es_client = getES()
embed_model = getEmbed()


# def categoryWiseAlerts(
#     query: str,
#     last_days: int = 84,
#     given_date: Optional[str] = None,
#     value: int = 1,
#     CityName: str = "All",
#     stateName: str = "All",
#     complaintType: str = "All",
#     complaintMode: str = "All",
#     companyName: str = "All",
#     complaintStatus: str = "All",
#     threshold: float = 1.3,
#     complaint_numbers: List[str] = Query(default=["NA"])
# ) -> Dict:
#     """
#     Calculate category-wise alerts based on complaint frequency changes.

#     Parameters
#     ----------
#     query : str
#         Search query for filtering complaints
#     last_days : int, optional
#         Number of days to look back for comparison, by default 7
#     given_date : Optional[str], optional
#         Reference date for comparison, by default current date
#     value : int, optional
#         Search type (1-Semantic, 2-Keyword, 3-Hybrid), by default 1
#     CityName : str, optional
#         City filter, by default "All"
#     stateName : str, optional
#         State filter, by default "All"
#     complaintType : str, optional
#         Complaint type filter, by default "All"
#     complaintMode : str, optional 
#         Complaint mode filter, by default "All"
#     companyName : str, optional
#         Company filter, by default "All"
#     complaintStatus : str, optional
#         Status filter, by default "All"
#     threshold : float, optional
#         Relevance threshold, by default 1.5
#     complaint_numbers : List[str], optional
#         Specific complaint numbers to filter, by default ["NA"]

#     Returns
#     -------
#     Dict
#         Dictionary containing category stats including:
#         - category: search query
#         - previous_count_per_hours: historical hourly average
#         - today_count_per_hours: current hourly rate
#         - increase_percentage: percentage change
#     """
#     # Clean query
#     query = query.replace("+", " ").strip()
    
#     # Set dates
#     current_date = datetime.now()
#     given_date = given_date or current_date.strftime("%Y-%m-%d")
    
#     # Calculate date ranges
#     if last_days == 84:
#         # last 12 weeks data, before a week 
#         reference_date = datetime.strptime(given_date, "%Y-%m-%d")
#         historical_start = (reference_date - timedelta(days=91))
#         historical_end = (reference_date - timedelta(days=8))

#         # total_hours = 24 * 7
#         # find total days between historical_end and historical_start
#         total_days = historical_end - historical_start
#         # total_days = (historical_end - historical_start)
#     else:
#         # Handle other time periods if needed
#         return {"error": f"Unsupported last_days value: {last_days}"}

#     # Common search parameters
#     search_params = {
#         "es_client": es_client,
#         "query": query,
#         "embed_model": embed_model,
#         "index_name": INDEX_NAME,
#         "CityName": CityName,
#         "stateName": stateName,
#         "complaintType": complaintType,
#         "complaintMode": complaintMode,
#         "companyName": companyName,
#         "complaintStatus": complaintStatus,
#         "threshold": threshold,
#         "complaint_numbers": complaint_numbers
#     }

#     # Get historical counts
#     historical_count = semanticSearchCount(
#         start_date=historical_start.strftime("%Y-%m-%d"),
#         end_date=historical_end.strftime("%Y-%m-%d"),
#         **search_params
#     )["total_count"]

#     # Get current day counts
#     reference_start_date = datetime.strptime(given_date, "%Y-%m-%d") - timedelta(days=7)
#     reference_end_date = datetime.strptime(given_date)

#     # Assuming historical_start and historical_end are strings in a format like "YYYY-MM-DD"
#     reference_start_date = datetime.strptime(reference_start_date, "%Y-%m-%d")
#     reference_end_date = datetime.strptime(reference_end_date, "%Y-%m-%d")

#     reference_days_in_bw = (reference_end_date - reference_start_date).days

#     # reference_date = datetime.strptime(given_date, "%Y-%m-%d") if isinstance(given_date, str) else given_date
#     # today = reference_date.strftime("%Y-%m-%d")
#     # yesterday = (reference_date - timedelta(days=1)).strftime("%Y-%m-%d")
#     current_count = semanticSearchCount(
#         start_date=reference_start_date,
#         end_date=reference_end_date,
#         **search_params
#     )["total_count"]

#     print("Today's Count:", current_count, type(current_count), search_params, reference_start_date, reference_end_date)

#     # Calculate rates
#     print("Historical Count:", historical_count,type(historical_count), "Total Hours:", total_days)
#     historical_hourly_rate = (historical_count / total_days) if total_days > 0 else 0
#     current_hourly_rate = current_count / reference_days_in_bw

#     # Calculate percentage increase
#     increase_percentage = (
#         ((current_hourly_rate - historical_hourly_rate) / historical_hourly_rate * 100)
#         if historical_hourly_rate > 0 else 0
#     )

#     return {
#         "category": query,
#         "previous_count_per_hours": round(historical_hourly_rate, 2),
#         "today_count_per_hours": round(current_hourly_rate, 2),
#         "increase_percentage": round(increase_percentage, 2)
#     }



def categoryWiseAlerts(
    query: str,
    last_days: int = 84,
    given_date: Optional[str] = None,
    value: int = 1,
    CityName: str = "All",
    stateName: str = "All",
    complaintType: str = "All",
    complaintMode: str = "All",
    companyName: str = "All",
    complaintStatus: str = "All",
    threshold: float = 1.3,
    complaint_numbers: List[str] = Query(default=["NA"])
) -> Dict:
    """
    Calculate category-wise alerts based on complaint frequency changes.
    """
    # Clean query
    query = query.replace("+", " ").strip()
    
    # Set dates
    current_date = datetime.now()
    if given_date is None:
        given_date = current_date.strftime("%Y-%m-%d")
    
    # Convert given_date to datetime if it's a string
    reference_date = datetime.strptime(given_date, "%Y-%m-%d")
    
    # Calculate date ranges for historical period (12 weeks before the reference week)
    if last_days == 84:
        historical_start = (reference_date - timedelta(days=91))  # 13 weeks ago
        historical_end = (reference_date - timedelta(days=7))     # Up to last week
        
        # Calculate total days between historical dates
        total_days = (historical_end - historical_start).days
    else:
        return {"error": f"Unsupported last_days value: {last_days}"}

    # Calculate reference period (last 7 days)
    reference_start_date = reference_date - timedelta(days=7)
    reference_end_date = reference_date

    # Common search parameters
    search_params = {
        "es_client": es_client,
        "query": query,
        "embed_model": embed_model,
        "index_name": INDEX_NAME,
        "CityName": CityName,
        "stateName": stateName,
        "complaintType": complaintType,
        "complaintMode": complaintMode,
        "companyName": companyName,
        "complaintStatus": complaintStatus,
        "threshold": threshold,
        "complaint_numbers": complaint_numbers
    }

    # Get historical counts (for the 12 weeks period)
    historical_count = semanticSearchCount(
        start_date=historical_start.strftime("%Y-%m-%d"),
        end_date=historical_end.strftime("%Y-%m-%d"),
        **search_params
    )["total_count"]

    # Get current period counts (last 7 days)
    current_count = semanticSearchCount(
        start_date=reference_start_date.strftime("%Y-%m-%d"),
        end_date=reference_end_date.strftime("%Y-%m-%d"),
        **search_params
    )["total_count"]

    # Calculate daily rates
    historical_daily_rate = (historical_count / total_days) if total_days > 0 else 0
    current_daily_rate = current_count / 7  # Always 7 days for reference period

    # Calculate percentage increase
    increase_percentage = (
        ((current_daily_rate - historical_daily_rate) / historical_daily_rate * 100)
        if historical_daily_rate > 0 else 0
    )

    return {
        "category": query,
        "previous_count_per_day": round(historical_daily_rate, 2),
        "current_count_per_day": round(current_daily_rate, 2),
        "increase_percentage": round(increase_percentage, 2),
    }

