import sys
from pathlib import Path
from fastapi import APIRouter
from repository.semantic_search import semanticSearch, semanticSearchCount, semanticSearchSpatialAnalysis
from repository.keyword_search import keywordSearch, keywordSearchCount
from repository.hybrid_search import hybridSearch, hybridSearchCount
from repository.basicdetails import getUserDetails, getcomplaintDetails, getCompanyDetails
from datetime import datetime
from fastapi import Query
from typing import List
import json
import pandas as pd
from pydantic import BaseModel
router = APIRouter(tags=["Basic Features"])
from fastapi import HTTPException
from repository.basicdetails import getComplaintDistribution
from typing import Annotated
from fastapi import Depends
from sqlalchemy.orm import Session
from repository import database
from router.authentication import get_current_user
from fastapi.security import OAuth2PasswordBearer
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


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

@router.get("/get_complaint_details")
async def getComplaintDetails(token : Annotated[str, Depends(oauth2_scheme)], complain_number: str = Query(..., description="The complaint number to search for"), db: Session = Depends(database.get_db)):
    '''
    A function to get complaint details from the database based on complaint_number
    '''

    user = await get_current_user(token, db)
    user = user.username.lower()

    result = getcomplaintDetails(complain_number)
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result

@router.post("/get_company_details")
async def getCompanyDetailsEndpoint(token : Annotated[str, Depends(oauth2_scheme)], sectorname = "All", companyname = "All", categoryname="All", db: Session = Depends(database.get_db)):
    '''
    A function to get company details from the database based on a list of company IDs
    '''
    user = await get_current_user(token, db)
    user = user.username.lower()

    result = getCompanyDetails(sectorname, companyname, categoryname)
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result


class ComplaintDistributionRequest(BaseModel):
    start_date: str = "2024-01-01"
    end_date: str = "2025-12-31"
    stateName: str = "All"
    sectorName: str = "All"
    categoryName: str = "All"
    attribute: str
    skip: int = 0
    limit: int = 20


@router.post("/complaint_distribution_by")
async def Complaint_distribution_by(token : Annotated[str, Depends(oauth2_scheme)], item: ComplaintDistributionRequest, db: Session = Depends(database.get_db)):
    """
    Get Complaint distribution by a specified attribute.
    Valid attributes: 'stateName', 'complaintType', 'complaintMode', 'sectorName', 'categoryName', 'complaintStatus', 'companyStatus'
    """
    user = await get_current_user(token, db)
    user = user.username.lower()

    valid_attributes = ['stateName', 'complaintType', 'complaintMode', 'sectorName', 'categoryName', 'complaintStatus', 'companyStatus']

    if item.attribute not in valid_attributes:
        return {"error": f"Invalid attribute. Must be one of {valid_attributes}"}

    result = getComplaintDistribution(item.attribute, item.start_date, item.end_date, item.stateName, item.sectorName, item.categoryName, item.skip, item.limit)

    return {"distribution": result}

