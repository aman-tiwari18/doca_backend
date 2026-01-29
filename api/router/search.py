import sys
from pathlib import Path
from fastapi import APIRouter
from repository.semantic_search import semanticSearch, semanticSearchCount, semanticSearchSpatialAnalysis, semanticSearchBasic, getcomplaintDetails, semanticSearchCompanyCount,keywordSearchCompanyCount
from repository.keyword_search import keywordSearch, keywordSearchCount, keywordSearchBasic
from repository.hybrid_search import hybridSearch, hybridSearchCount
from repository.basicdetails import getUserDetails
from datetime import datetime
from fastapi import Query
from typing import List
import json
import pandas as pd
from pydantic import BaseModel
router = APIRouter(tags=["Search Features"])
from fastapi import HTTPException
from repository.basicdetails import getLastComplaints

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from typing import Annotated
from sqlalchemy.orm import Session
from repository import database
from router.authentication import get_current_user
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# ---------------------------- Path Management ----------------------------
resources_dir = Path(__file__).resolve().parents[2] / "resources"
sys.path.append(str(resources_dir))
# ---------------------------- Import External Utilities ----------------------------
from utility import getES, getEmbed, load_config, connectDB_alchemy

# ---------------------------- Import Internal Utilities ----------------------------
config = load_config()
INDEX_NAME = config["ES"]["INDEX_NAME"]

es_client = getES()
embed_model = getEmbed()


MAPPING_STATE_ID_TO_NAME_PATH = resources_dir / Path(config["MAPPING_STATE_ID_TO_NAME_PATH"]).name
MAPPING_CITY_ID_TO_NAME_PATH = resources_dir / Path(config["MAPPING_CITY_ID_TO_NAME_PATH"]).name

MAPPING_STATE_NAME_TO_ID_PATH = resources_dir / Path(config["MAPPING_STATE_NAME_TO_ID_PATH"]).name
MAPPING_CITY_NAME_TO_ID_PATH = resources_dir / Path(config["MAPPING_CITY_NAME_TO_ID_PATH"]).name

# load both mapping and convert each to MAPPING_STATE_NAME_TO_ID and MAPPING_CITY_NAME_TO_ID
with open(MAPPING_STATE_ID_TO_NAME_PATH, 'r') as f:
    MAPPING_STATE_ID_TO_NAME = json.load(f)

with open(MAPPING_STATE_NAME_TO_ID_PATH, 'r') as f:
    MAPPING_STATE_NAME_TO_ID = json.load(f)

with open(MAPPING_CITY_ID_TO_NAME_PATH, 'r') as f:
    MAPPING_CITY_ID_TO_NAME = json.load(f)

with open(MAPPING_CITY_NAME_TO_ID_PATH, 'r') as f:
    MAPPING_CITY_NAME_TO_ID = json.load(f)


# ---------------------------- Logs Directory Setup ----------------------------
BASE_DIR = Path("logs")
BASE_DIR.mkdir(exist_ok=True)

class getSearchRequest(BaseModel):
    query: str
    skip: int
    size: int
    start_date: str = "2025-01-01"
    end_date: str = "2025-03-30"
    value: int = 1
    CityName: str = "All"
    stateName: str = "All"
    complaintType: str = "All"
    complaintMode: str = "All"
    companyName: str = "All"
    complaintStatus: str = "All"
    threshold: float = 1.5
    complaint_numbers: List[str] = ["NA"]


# Search Route
@router.post("/search")
async def search_grievance(
    token : Annotated[str, Depends(oauth2_scheme)],
    search_request: getSearchRequest,
    db: Session = Depends(database.get_db)
    ):
    '''
    A route to search grievances in the Elasticsearch index.
    This route supports three types of search:
    1. Semantic Search - to find semantically similar grievances
    2. Keyword Search - to find grievances based on exact keywords 
    3. Hybrid Search - a combination of semantic and keyword search
    
    Parameters
    ----------
    1) query: string
    2) value: int -> Represent Type of Search 1-Semantic 2-Keyword 3-hybrid search
    3) skiprecord: int
    4) size: int
    5) threshold: float-> relevance
    '''
    user = await get_current_user(token, db)
    user = user.username.lower()

    total_count = 0
    query=search_request.query.replace("+"," ")

    output=None

    start_date = datetime.strptime(search_request.start_date, "%Y-%m-%d").strftime("%Y-%m-%d")
    end_date = datetime.strptime(search_request.end_date, "%Y-%m-%d").strftime("%Y-%m-%d")

    CityName = MAPPING_CITY_NAME_TO_ID.get(search_request.CityName, "All") if search_request.CityName != "All" else "All"
    stateName = MAPPING_STATE_NAME_TO_ID.get(search_request.stateName, "All") if search_request.stateName != "All" else "All"

    if search_request.value==1:
        output=semanticSearch(
                es_client,
                query,
                start_date,
                end_date,
                embed_model,
                search_request.skip,
                search_request.size,
                INDEX_NAME,
                CityName,
                stateName,
                search_request.complaintType,
                search_request.complaintMode,
                search_request.companyName,
                search_request.complaintStatus,
                search_request.threshold,
                search_request.complaint_numbers
            )

        total_count=semanticSearchCount(
                es_client,
                query,
                start_date,
                end_date,
                embed_model,
                INDEX_NAME,
                CityName,
                stateName,
                search_request.complaintType,
                search_request.complaintMode,
                search_request.companyName,
                search_request.complaintStatus,
                search_request.threshold,
                search_request.complaint_numbers
            )
        print(total_count)
        print(output)

    elif search_request.value==2:
        output=keywordSearch(
                es_client,
                query,
                start_date,
                end_date,
                search_request.skip,
                search_request.size,
                INDEX_NAME,
                CityName,
                stateName,
                search_request.complaintType,
                search_request.complaintMode,
                search_request.companyName,
                search_request.complaintStatus,
                search_request.complaint_numbers)
        
        total_count=keywordSearchCount(
                es_client,
                query,
                start_date,
                end_date,
                INDEX_NAME,
                CityName,
                stateName,
                search_request.complaintType,
                search_request.complaintMode,
                search_request.companyName,
                search_request.complaintStatus,
                search_request.complaint_numbers)
                                       
        

    elif search_request.value==3:
        output=hybridSearch(    
            es_client,
            query,
            start_date,
            end_date,
            embed_model,
            search_request.skip,
            search_request.size,
            INDEX_NAME,
            CityName,
            stateName,
            search_request.complaintType,
            search_request.complaintMode,
            search_request.companyName,
            search_request.complaintStatus,
            search_request.threshold,
            search_request.complaint_numbers
        )
        total_count = hybridSearchCount(
            es_client,
            query,
            start_date,
            end_date,
            embed_model,
            INDEX_NAME,
            CityName,
            stateName,
            search_request.complaintType,
            search_request.complaintMode,
            search_request.companyName,
            search_request.complaintStatus,
            search_request.threshold,
            search_request.complaint_numbers
        )

    else:
        return {"total_count": 0, "grievanceData": []}

    return {"total_count": total_count, "grievanceData":output}



# Request model
class IDRequest(BaseModel):
    ids: list[str]   # list of IDs
    skip: int = 0
    size: int = 20


@router.post("/get_userdata")
async def get_es_data(token : Annotated[str, Depends(oauth2_scheme)], request: IDRequest, db: Session = Depends(database.get_db)):
    
    user = await get_current_user(token, db)
    user = user.username.lower()

    try:
        # Search by multiple _ids
        response = es_client.search(
            index=INDEX_NAME,   # change to your index
            body={
                "size" : request.size,
                "from": request.skip,
                "query": {
                    "ids": {
                        "values": request.ids
                    }
                },
                "_source" : ["complaintDetails", "userId", "stateCode", "complaintType", "complaintMode", "categoryCode", "converganceCompanyName", "nonCoverganeceCompanyName", "complaintStatus", "companyStatus", "complaintRegDate", "lastUpdationDate"]
            }
        )
        print(request.ids, type(request.ids))
        hits = response.get("hits", {}).get("hits", [])

        if not hits:
            raise HTTPException(status_code=404, detail="No documents found for given _ids")

        # Extract documents with their _id
        documents = [hit["_source"] | {"_id": hit["_id"]} for hit in hits]
        grievancedf = pd.DataFrame(documents)
        userIds = grievancedf['userId'].tolist()
        user_details = getUserDetails(userIds)

        print("we get the user details as", len(user_details))
        user_detailsdf = pd.DataFrame(user_details)
        grievancedf = grievancedf.merge(user_detailsdf, on="userId", how="left")
        grievancedf = grievancedf[['_id', 'complaintDetails', 'userId', 'fullName', 'CityName', 'stateName',  'country', 'userType', 'status','complaintRegDate', 'updationDate', 'complaintType', 'complaintMode', 'categoryCode', 'complaintStatus', 'companyStatus', 'lastUpdationDate']]
        # rename _id to complaintNumber and replace _ with /
        grievancedf = grievancedf.rename(columns={'_id': 'complaintNumber'})
        grievancedf = grievancedf.fillna('nan')
        documents = grievancedf.to_dict(orient='records')

        print("document from ES", len(documents))
        return {"count": len(documents), "data": documents}

    except Exception as e:
        return {"count": 0, "data": []} 
        raise HTTPException(status_code=500, detail=f"Elasticsearch error: {str(e)}")
    

class getSpatialAnalysisData(BaseModel):
    start_date: str = "2017-01-01",
    end_date: str = "2017-12-30",
    query: str
    threshold: float = 1.3
    CityName: str = "All"
    stateName: str = "All"
    complaintType: str = "All"
    complaintMode: str = "All"
    companyName: str = "All"
    complaintStatus: str = "All"
    complaint_numbers: List[str] = ["NA"]


# API to call
@router.post("/get_spatial_analysis_data")
async def get_spatial_analysis_data(
    token : Annotated[str, Depends(oauth2_scheme)],
    request: getSpatialAnalysisData,
    db: Session = Depends(database.get_db)
):
    """
    API endpoint to get spatial analysis data.

    Parameters:
    - start_date (str): Start date for filtering complaints.
    - end_date (str): End date for filtering complaints.
    - CityName (str): City name filter (default is "All").
    - stateName (str): State name filter (default is "All").
    - complaintType (str): Complaint type filter (default is "All").
    - complaintMode (str): Complaint mode filter (default is "All").
    - companyName (str): Company name filter (default is "All").
    - complaintStatus (str): Complaint status filter (default is "All").
    - threshold (float): Relevance threshold for semantic search (default is 1.5).
    - complaint_numbers (List[str]): List of specific complaint numbers to filter.

    Returns:
    - dict: A dictionary containing spatial analysis data.
    """

    user = await get_current_user(token, db)
    user = user.username.lower()

    start_date = datetime.strptime(request.start_date, "%Y-%m-%d").strftime("%Y-%m-%d")
    end_date = datetime.strptime(request.end_date, "%Y-%m-%d").strftime("%Y-%m-%d")

    CityName = MAPPING_CITY_NAME_TO_ID.get(request.CityName, "All") if request.CityName != "All" else "All"
    stateName = MAPPING_STATE_NAME_TO_ID.get(request.stateName, "All") if request.stateName != "All" else "All"

    #  es_client,
    # query: str,
    # start_date: str,
    # end_date: str,
    # embed_model,
    # index_name: str,
    # CityName: str = "All",
    # stateName: str = "All",
    # complaintType: str = "All",
    # complaintMode: str = "All",
    # companyName: str = "All",
    # complaintStatus: str = "All",
    # threshold: float = 0.5,
    # complaint_numbers: list = ["NA"]

    output = semanticSearchSpatialAnalysis(
        es_client,
        request.query,
        start_date,
        end_date,
        embed_model,
        INDEX_NAME,
        CityName,
        stateName,
        request.complaintType,
        request.complaintMode,
        request.companyName,
        request.complaintStatus,
        request.threshold,
        request.complaint_numbers
    )   

    # convert keys to state names
    output_named = {}
    for state_id, count in output.items():
        state_name = MAPPING_STATE_ID_TO_NAME[str(state_id)] if str(state_id) in MAPPING_STATE_ID_TO_NAME else state_id
        output_named[state_name] = count

    return output_named



class SemanticRCARequest(BaseModel):
    query: str
    value: int = 1
    start_date: str = "2025-01-01"
    end_date: str = "2025-03-30"
    threshold: float = 1.5
    CityName: str = "All"
    stateName: str = "All"
    complaintType: str = "All"
    complaintMode: str = "All"
    companyName: str = "All"
    complaintStatus: str = "All"
    complaint_numbers: List[str] = ["NA"]


@router.post("/get_semantic_rca")
async def get_semantic_rca(token : Annotated[str, Depends(oauth2_scheme)], request: SemanticRCARequest, db: Session = Depends(database.get_db)):
    """
    API endpoint to get semantic RCA data.
    """

    user = await get_current_user(token, db)
    user = user.username.lower()

    try:
        # Format dates
        start_date = datetime.strptime(request.start_date, "%Y-%m-%d").strftime("%Y-%m-%d")
        end_date = datetime.strptime(request.end_date, "%Y-%m-%d").strftime("%Y-%m-%d")

        # Map city and state names to IDs
        city_name = MAPPING_CITY_NAME_TO_ID.get(request.CityName, "All") if request.CityName != "All" else "All"
        state_name = MAPPING_STATE_NAME_TO_ID.get(request.stateName, "All") if request.stateName != "All" else "All"
        
        print(f"Processing request with value: {request.value}, query: {request.query}")

        results = {}

        if request.value == 1:
            output = semanticSearchBasic(
                es_client,
                request.query,
                start_date,
                end_date,
                embed_model,
                INDEX_NAME,
                city_name,
                state_name,
                request.complaintType,
                request.complaintMode,
                request.companyName,
                request.complaintStatus,
                request.threshold,
                request.complaint_numbers
            )
            results["total_counts"] = semanticSearchCount(
                es_client,
                request.query,
                start_date,
                end_date,
                embed_model,
                INDEX_NAME, 
                city_name,
                state_name,
                request.complaintType,
                request.complaintMode,
                request.companyName,
                request.complaintStatus,
                request.threshold,
                request.complaint_numbers
            )
            results["complaintNumbers"] = output["complaintNumbers"]
            return results

        elif request.value == 2:
            output = keywordSearchBasic(
                es_client,
                request.query,
                start_date,
                end_date,
                INDEX_NAME,
                city_name,
                state_name,
                request.complaintType,
                request.complaintMode,
                request.companyName,
                request.complaintStatus,
                request.complaint_numbers
            )
            if output:
                results["total_counts"] = keywordSearchCount(
                    es_client,
                    request.query,
                    start_date,
                    end_date,
                    INDEX_NAME,
                    city_name,
                    state_name,
                    request.complaintType,
                    request.complaintMode,
                    request.companyName,
                    request.complaintStatus,
                    request.complaint_numbers
                )
                results["complaintNumbers"] = output["complaintNumbers"]
            return results

        else:
            return {"total_counts": 0, "complaintNumbers": []}

    except Exception as e:
        print(f"Error in get_semantic_rca: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing request: {str(e)}"
        )

    '''
    A function to get complaint details from the database based on complaint_number
    '''

    user = await get_current_user(token, db)
    user = user.username.lower()

    try:
        result = getcomplaintDetails(es_client=es_client, index_name=INDEX_NAME, complaint_number=complain_number)
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching complaint details: {str(e)}")




@router.post("/get_last_complaints")
async def get_last_complaints(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Session = Depends(database.get_db)
):
    """
    A function to get last 1000 complaints from the database
    """

    # Get logged-in user
    user = await get_current_user(token, db)
    username = user.username.lower()

    # Fetch last 1000 complaints
    try:
        complaints = getLastComplaints()
        return {
            "user": username,
            "count": len(complaints),
            "data": complaints
        }
    except Exception as e:
        print(f"Error in get_last_complaints: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing request: {str(e)}"
        )



@router.post("/get_complaint_details_with_ids")
async def get_complaint_details(
    token: Annotated[str, Depends(oauth2_scheme)], 
    complain_number: List[str], 
    db: Session = Depends(database.get_db)
):
    '''
    A function to get complaint details from the database based on complaint_number
    '''

    user = await get_current_user(token, db)
    user = user.username.lower()

    try:
        result = getcomplaintDetails(
            es_client=es_client, 
            index_name=INDEX_NAME, 
            complaint_number=complain_number
        )
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Error fetching complaint details: {str(e)}"
        )

