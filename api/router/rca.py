import sys
import pandas as pd
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List
from typing import Annotated
from fastapi import Depends

from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from repository.rcacategory import get_category_data_with_prompt
from repository.dynamic_rca import dynamicRca
from repository.rcacached import cachedrca, CachedRcaRequest
from repository.rcagenerate_ai_categories import GenerateAICategoriesRequest, generate_ai_categories
from repository import database
from router.authentication import get_current_user
from fastapi.security import OAuth2PasswordBearer
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


router = APIRouter(tags=["RCA Features"])

# ---------------------------- Path Management ----------------------------
resources_dir = Path(__file__).resolve().parents[2] / "resources"
sys.path.append(str(resources_dir))

# ---------------------------- Import External Utilities ----------------------------
from utility import getES, getEmbed, load_config, connectDB_alchemy, connectDB, closeDB

config = load_config()
INDEX_NAME = config["ES"]["INDEX_NAME"]
es = getES()
model = getEmbed()

print(f"[{datetime.now()}] , Connected to Elasticsearch.")

class MyItem(BaseModel):
    number_of_clusters: int = 26
    grievance_id_list: List[str] = ["NA"]

# @router.post("/dynamicrca/")
# async def dynamic_rca(item: MyItem):
#     """
#     Dynamic RCA Route to perform dynamic RCA
#     """
#     connection = connectDB_alchemy()
#     if connection is None:
#         return {"error": "Database connection failed."}
#     query = "SELECT * FROM tblcomplaints"  # Update with your actual table name
#     try:
#         df = pd.read_sql(query, connection)
#     except Exception as e:
#         return {"error": f"Failed to load data: {e}"}

#     # df = pd.read_pickle("../data/griev.pkl")
    
#     # Sample 10,000 rows
#     sample_df = df.sample(n=10000, random_state=42)
    
#     # Prepare grievance_id list
#     grievance_id_list = sample_df['grievance_id'].tolist()
    
#     # Call dynamic RCA function
#     output = dynamicRca(item.number_of_clusters, grievance_id_list)
    
#     return {"output": output}


@router.post("/generate_ai_categories", response_model=dict)
async def generate_ai_categories_fn( token : Annotated[str, Depends(oauth2_scheme)], request: GenerateAICategoriesRequest, db: Session = Depends(database.get_db)):
    """
    API endpoint to generate AIRCA topic labels for complaints.

    Args:
        request (GenerateAICategoriesRequest): The request containing start date, end date, ministry, and tree structure.

    Returns:
        dict: A dictionary containing the generated topic labels.
    """
    user = await get_current_user(token, db)
    user = user.username.lower()

    return JSONResponse(content=generate_ai_categories(request))



@router.get("/get_ai_categories")
async def get_ai_categories(token : Annotated[str, Depends(oauth2_scheme)], db: Session = Depends(database.get_db)):
    """
    API endpoint to retrieve AI-generated categories.

    Args:
        None

    Returns:
        dict: A dictionary containing the AI-generated categories.
    """
    user = await get_current_user(token, db)
    user = user.username.lower()

    # Safe parameterized SQL query
    DB_GET_AI_CATEGORIES = """
        SELECT  DISTINCT * FROM rcaaicategories 
        ORDER BY idx DESC LIMIT 20
    """

    con = connectDB()
    result = pd.read_sql_query(DB_GET_AI_CATEGORIES, con)
    closeDB(con)

    # Return empty list if nothing found
    if result.empty:
        return {"categories": []}

    # Now serialize to JSON
    return {"categories": result.to_dict(orient='records')}


@router.post("/realtimerca")
async def cachedrca_endpoint(token : Annotated[str, Depends(oauth2_scheme)], startDate: str = "2016-08-01", endDate: str = "2016-08-31", ministry: str = "DOCAF",  number_of_clusters: int = 11, db: Session = Depends(database.get_db)):
    """
    API endpoint to perform cached RCA based on the provided request.

    Args:
        request (CachedRcaRequest): The request containing start date, end date, ministry, state, district, and number of clusters.

    Returns:
        dict: A dictionary containing the cached RCA results.
    """

    user = await get_current_user(token, db)
    user = user.username.lower()

    dataRequest = CachedRcaRequest(
        startDate=startDate,
        endDate=endDate,
        ministry=ministry,
        number_of_clusters=number_of_clusters
    )
    # Validate the request
    if not dataRequest.startDate or not dataRequest.endDate:
        return {"status": "InvalidDateRange", "message": "Start date and end date are required."}

    return cachedrca(dataRequest)


@router.get("/categoryrca")
async def category_rca(token : Annotated[str, Depends(oauth2_scheme)], start_date: str = "2024-01-01", end_date: str = "2025-01-01", threshold:float =1.2, CityName: str = "All", stateName: str = "All", complaintType: str = "All", complaintMode: str = "All", companyName: str = "All", complaintStatus: str = "All", db: Session = Depends(database.get_db)):
    """
    API endpoint to get RCA category data based on the provided parameters.

    Args:
        start_date (str): The start date for filtering complaints.
        end_date (str): The end date for filtering complaints.
        CityName (str): The city name for filtering complaints.
        stateName (str): The state name for filtering complaints.
        complaintType (str): The complaint type for filtering complaints.
        complaintMode (str): The complaint mode for filtering complaints.
        companyName (str): The company name for filtering complaints.
        complaintStatus (str): The complaint status for filtering complaints.

    Returns:
        dict: A dictionary containing the category data including words, counts, and document IDs.
    """

    # Validate date format
    try:
        datetime.strptime(start_date, "%Y-%m-%d")
        datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        return {"status": "InvalidDateFormat", "message": "Dates must be in YYYY-MM-DD format."}

    # Fetch category data
    category_data = get_category_data_with_prompt(
        start_date,
        end_date,
        threshold=threshold,
        CityName=CityName,
        stateName=stateName,
        complaintType=complaintType,
        complaintMode=complaintMode,
        companyName=companyName,
        complaintStatus=complaintStatus
    )

    return JSONResponse(content=category_data)
