import sys
from pathlib import Path
from fastapi import APIRouter
from datetime import datetime
from typing import List
import json
from fastapi.concurrency import run_in_threadpool

from pydantic import BaseModel
router = APIRouter(tags=["Search Features"])
from fastapi import HTTPException

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from typing import Annotated
from sqlalchemy.orm import Session
from repository import database
from router.authentication import get_current_user
from repository.distributions import semanticSearchCompanyCount, keywordSearchCompanyCount , getComplaintDistributionES, semanticSearchAlltypeCompanyCount, keywordSearchAlltypeCompanyCount

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

project_root = resources_dir.parent

MAPPING_STATE_ID_TO_NAME_PATH = project_root / config["MAPPING_STATE_ID_TO_NAME_PATH"].lstrip("/")
MAPPING_CITY_ID_TO_NAME_PATH = project_root / config["MAPPING_CITY_ID_TO_NAME_PATH"].lstrip("/")

MAPPING_STATE_NAME_TO_ID_PATH = project_root / config["MAPPING_STATE_NAME_TO_ID_PATH"].lstrip("/")
MAPPING_CITY_NAME_TO_ID_PATH = project_root / config["MAPPING_CITY_NAME_TO_ID_PATH"].lstrip("/")

# load both mapping and convert each to MAPPING_STATE_NAME_TO_ID and MAPPING_CITY_NAME_TO_ID
with open(MAPPING_STATE_ID_TO_NAME_PATH, 'r') as f:
    MAPPING_STATE_ID_TO_NAME = json.load(f)

with open(MAPPING_STATE_NAME_TO_ID_PATH, 'r') as f:
    MAPPING_STATE_NAME_TO_ID = json.load(f)

with open(MAPPING_CITY_ID_TO_NAME_PATH, 'r') as f:
    MAPPING_CITY_ID_TO_NAME = json.load(f)

with open(MAPPING_CITY_NAME_TO_ID_PATH, 'r') as f:
    MAPPING_CITY_NAME_TO_ID = json.load(f)


router = APIRouter(tags=["Distributions"])


class CompanyDistributionRequest(BaseModel):
    query: str = ""
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
    skip: int = 0
    limit: int = 10


@router.post("/get_company_distribution")
async def getCompanyDistribution(
    request: CompanyDistributionRequest,
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Session = Depends(database.get_db)
):
    """
    Get complaint distribution by company (merged across convergance + nonCovergence).
    Returns aggregated counts per company.
    """
    user = await get_current_user(token, db)
    user = user.username.lower()
    # Convert date strings
    start_date = datetime.strptime(request.start_date, "%Y-%m-%d").strftime("%Y-%m-%d")
    end_date = datetime.strptime(request.end_date, "%Y-%m-%d").strftime("%Y-%m-%d")
    # Map city and state names to IDs
    CityName = MAPPING_CITY_NAME_TO_ID.get(request.CityName, "All") if request.CityName != "All" else "All"
    stateName = MAPPING_STATE_NAME_TO_ID.get(request.stateName, "All") if request.stateName != "All" else "All"
    result = None
    try:
        if request.value==1:
            result = semanticSearchCompanyCount(
                es_client=es_client,
                query=request.query,
                start_date=start_date,
                end_date=end_date,
                index_name=INDEX_NAME,
                companyName=request.companyName,
                complaint_numbers=request.complaint_numbers,
                skip=request.skip,
                limit=request.limit
            )
        elif request.value==2:
            result = keywordSearchCompanyCount(
                es_client=es_client,
                query=request.query,
                start_date=start_date,
                end_date=end_date,
                index_name=INDEX_NAME,
                companyName=request.companyName,
                complaint_numbers=request.complaint_numbers,
                skip=request.skip,
                limit=request.limit
            )
        return {
            "total_companies": len(result),
            "distribution": result
        }
    except Exception as e:
        print(f"Error in get_company_distribution: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing request: {str(e)}"
        )


@router.post("/get_all_company_distribution")
async def getAllCompanyDistribution(
    request: CompanyDistributionRequest,
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Session = Depends(database.get_db)
):
    """
    Get complaint distribution by company (Both Converged and Non-Converged).
    Returns aggregated counts per company from both fields.
    """
    user = await get_current_user(token, db)
    user = user.username.lower()
    # Convert date strings
    start_date = datetime.strptime(request.start_date, "%Y-%m-%d").strftime("%Y-%m-%d")
    end_date = datetime.strptime(request.end_date, "%Y-%m-%d").strftime("%Y-%m-%d")
    
    # Map city and state names to IDs
    CityName = MAPPING_CITY_NAME_TO_ID.get(request.CityName, "All") if request.CityName != "All" else "All"
    stateName = MAPPING_STATE_NAME_TO_ID.get(request.stateName, "All") if request.stateName != "All" else "All"
    
    result = None
    try:
        if request.value==1:
            result = semanticSearchAlltypeCompanyCount(
                es_client=es_client,
                query=request.query,
                start_date=start_date,
                end_date=end_date,
                index_name=INDEX_NAME,
                companyName=request.companyName,
                complaint_numbers=request.complaint_numbers,
                skip=request.skip,
                limit=request.limit
            )
        elif request.value==2:
            result = keywordSearchAlltypeCompanyCount(
                es_client=es_client,
                query=request.query,
                start_date=start_date,
                end_date=end_date,
                index_name=INDEX_NAME,
                companyName=request.companyName,
                complaint_numbers=request.complaint_numbers,
                skip=request.skip,
                limit=request.limit
            )
        return result if result else {"converged": [], "non_converged": []}
    except Exception as e:
        print(f"Error in get_all_company_distribution: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing request: {str(e)}"
        )


class ComplaintDistributionRequest(BaseModel):
    start_date: str = "2024-01-01"
    end_date: str = "2025-12-31"
    stateName: str = "All"
    sectorName: str = "All"
    categoryName: str = "All"
    attribute: str
    skip: int = 0
    limit: int = 20


@router.post("/complaint_distribution_by_es")
async def Complaint_distribution_by(
    token: Annotated[str, Depends(oauth2_scheme)],
    item: ComplaintDistributionRequest,
    db: Session = Depends(database.get_db)
):
    """
    Get Complaint distribution by a specified attribute.
    Supported attributes (ES only):
      - stateName
      - categoryName
    """

    user = await get_current_user(token, db)
    user = user.username.lower()

    # 🔒 Only allow ES-backed attributes
    valid_attributes = ["stateName", "categoryName"]

    if item.attribute not in valid_attributes:
        return {
            "error": f"Invalid attribute. Only supported: {valid_attributes}"
        }

    # ✅ Always use Elasticsearch
    result = getComplaintDistributionES(
        attribute=item.attribute,
        start_date=item.start_date,
        end_date=item.end_date,
        stateName=item.stateName,
        sectorName=item.sectorName,
        categoryName=item.categoryName,
        skip=item.skip,
        limit=item.limit
    )

    return result   # already {"distribution": ...}


class SubcategoryWithCountsRequest(BaseModel):
    input_prompt: str
    value: int = 1  # 1-Semantic, 2-Keyword
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
    max_retries: int = 3



@router.post("/subcategory_with_counts")
async def subcategory_with_counts(
    token: Annotated[str, Depends(oauth2_scheme)],
    request: SubcategoryWithCountsRequest,
    db: Session = Depends(database.get_db)
):
    """
    Merged API: Generate subcategories using GPT and fetch counts + complaint numbers for each.
    
    This endpoint:
    1. Generates subcategories from input_prompt using GPT
    2. For each subcategory, calls semantic/keyword RCA to get counts and complaint numbers
    3. Returns comprehensive results with subcategory, prompt, counts, and complaint numbers
    
    Backend Configuration (hardcoded):
    - max_subcategories: 8
    - max_workers: 8 (based on max_subcategories)
    - enable_cache: True
    """
    from repository.distributions import getSubcategoryWithCounts
    
    user = await get_current_user(token, db)
    user = user.username.lower()
    
    # Convert date strings
    start_date = datetime.strptime(request.start_date, "%Y-%m-%d").strftime("%Y-%m-%d")
    end_date = datetime.strptime(request.end_date, "%Y-%m-%d").strftime("%Y-%m-%d")
    
    # Map city and state names to IDs
    CityName = MAPPING_CITY_NAME_TO_ID.get(request.CityName, "All") if request.CityName != "All" else "All"
    stateName = MAPPING_STATE_NAME_TO_ID.get(request.stateName, "All") if request.stateName != "All" else "All"
    
    # Hardcoded backend configuration
    MAX_SUBCATEGORIES = 8
    MAX_WORKERS = 8  # Based on max_subcategories
    ENABLE_CACHE = True
    
    try:
        # Run the synchronous function in a thread pool for async execution
        result = await run_in_threadpool(
            getSubcategoryWithCounts,
            input_prompt=request.input_prompt,
            value=request.value,
            start_date=start_date,
            end_date=end_date,
            threshold=request.threshold,
            CityName=CityName,
            stateName=stateName,
            complaintType=request.complaintType,
            complaintMode=request.complaintMode,
            companyName=request.companyName,
            complaintStatus=request.complaintStatus,
            complaint_numbers=request.complaint_numbers,
            max_retries=request.max_retries,
            max_subcategories=MAX_SUBCATEGORIES,
            max_workers=MAX_WORKERS,
            enable_cache=ENABLE_CACHE,
            es_client=es_client,
            embed_model=embed_model,
            index_name=INDEX_NAME
        )
        
        return {
            "success": True,
            "total_subcategories": len(result),
            "subcategories": result
        }
    except Exception as e:
        print(f"Error in subcategory_with_counts: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing request: {str(e)}"
        )


class CompanyCategoryDistributionRequest(BaseModel):
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
    skip: int = 0
    limit: int = 10
