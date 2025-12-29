import sys
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import pandas as pd

# ---------------------------- Path Management ----------------------------
resources_dir = Path(__file__).resolve().parents[2] / "resources"
sys.path.append(str(resources_dir))

# ---------------------------- Import External Utilities ----------------------------
from utility import getES, getEmbed, load_config, connectDB_alchemy
from repository.feedback.keyword_search import keywordSearch
from repository.basicdetails import getComplaintDistribution, getFeedbackDistribution
from typing import Annotated
from fastapi import Depends
from sqlalchemy.orm import Session
from repository import database
from router.authentication import get_current_user
from fastapi.security import OAuth2PasswordBearer
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# ---------------------------- Import Internal Utilities ----------------------------
config = load_config()

router = APIRouter(tags=["Feedback Features"])

# ---------------------------- Request Model ----------------------------
# class FeedbackRequest(BaseModel):
#     sectorname: str = "All"
#     companyname: str = "All"
#     categoryname: str = "All"
#     offset: int = 0
#     limit: int = 100

class KeywordSearchRequest(BaseModel):
    query:str
    start_date:str
    end_date:str
    skip: int
    size: int
    index_name: str
    CompanyName: str
    Sector: str
    Category: str
    complaint_numbers: list = ["NA"]


# ---------------------------- Route Definition ----------------------------
# @router.post("/get_feedback_keywords")
# async def getFeedbackData(token : Annotated[str, Depends(oauth2_scheme)], item: FeedbackRequest, db: Session = Depends(database.get_db)):
#     """
#     Fetch top keywords from remark_keywords table
#     filtered by Sector, CompanyName, and Category.
#     Only alphabetic keywords are included (no numbers or special characters).
#     """
#     user = await get_current_user(token, db)
#     user = user.username.lower()


#     con = connectDB_alchemy()

#     try:
#         # Base query
#         query = """
#             SELECT 
#                 keyword, 
#                 idf_score, 
#                 COUNT(*) AS keyword_count
#             FROM remark_keywords
#             WHERE keyword REGEXP '^[A-Za-z]+$'
#         """

#         filters = []
#         params = []

#         # Dynamic filters
#         if item.companyname != "All":
#             filters.append("CompanyName = %s")
#             params.append(item.companyname)

#         if item.sectorname != "All":
#             filters.append("Sector = %s")
#             params.append(item.sectorname)

#         if item.categoryname != "All":
#             filters.append("Category = %s")
#             params.append(item.categoryname)

#         # Combine filters
#         if filters:
#             query += " AND " + " AND ".join(filters)

#         # Add grouping, sorting, limit, offset
#         query += " GROUP BY keyword, idf_score ORDER BY idf_score DESC LIMIT %s OFFSET %s"
#         params.extend([item.limit, item.offset])

#         # ⚙️ Convert params to tuple
#         params = tuple(params)

#         print("Executing Query:", query)
#         print("With Parameters:", params)

#         # Execute
#         df = pd.read_sql(query, con, params=params)

#         if df.empty:
#             raise HTTPException(status_code=404, detail="No keywords found for the given filters.")

#         result = df.to_dict(orient="records")

#         return {
#             "status": "success",
#             "filters": item.dict(),
#             "count": len(result),
#             "data": result
#         }

#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error fetching keywords: {str(e)}")

#     finally:
#         con.dispose()



# class FeedbackDistributionRequest(BaseModel):
#     attribute: str
#     skip: int = 0
#     limit: int = 20


# @router.post("/feedback_distribution_by")
# def feedback_distribution_by(item: FeedbackDistributionRequest):
#     """
#     Get feedback distribution by a specified attribute.
#     Valid attributes: 'Sector', 'CompanyName', 'Category', 'ExperiencewithNCH', 'userexperience', 'unUnsatisfactory'
#     """

#     query = "select distinct {attribute}, count(*) as count from tblfeedback group by {attribute} order by count desc limit {skip}, {limit}".format(attribute=item.attribute, skip=item.skip, limit=item.limit)

#     valid_attributes = ['Sector', 'CompanyName', 'Category', 'ExperiencewithNCH', 'userexperience', 'unUnsatisfactory']
#     if item.attribute not in valid_attributes:
#         return {"error": f"Invalid attribute. Must be one of {valid_attributes}"}


#     con = connectDB_alchemy()
#     df = pd.read_sql(query, con)
#     result = df.to_dict(orient='records')
#     return {"distribution": result}

class FeedbackDistributionRequest(BaseModel):
    start_date : str = "2024-10-13 00:00:00"
    end_date : str = "2025-10-06 00:00:00"
    Sector: str = "All"
    CompanyName: str = "All"
    Category: str = "All"
    attribute: str
    skip: int = 0
    limit: int = 20


@router.post("/feedback_distribution_by")
async def Feedback_distribution_by(token : Annotated[str, Depends(oauth2_scheme)], item: FeedbackDistributionRequest, db: Session = Depends(database.get_db)):
    """
    Get Feedback distribution by a specified attribute.
    Valid attributes: 'Sector', 'CompanyName', 'Category', 'ExperiencewithNCH', 'userexperience', 'unUnsatisfactory'
    """
    user = await get_current_user(token, db)
    user = user.username.lower()

    valid_attributes = ['Sector', 'CompanyName', 'Category', 'ExperiencewithNCH', 'userexperience', 'unUnsatisfactory']

    if item.attribute not in valid_attributes:
        return {"error": f"Invalid attribute. Must be one of {valid_attributes}"}

    result = getFeedbackDistribution(item.start_date, item.end_date, item.attribute, item.Sector, item.CompanyName, item.Category, item.skip, item.limit)

    return {"distribution": result}


# get DocketNumber feedback based on the provided userexperience
class DocketFeedbackRequest(BaseModel):
    userexperience: str

@router.post("/get_feedback_ids")
async def get_docket_feedback(token : Annotated[str, Depends(oauth2_scheme)], item: DocketFeedbackRequest, db: Session = Depends(database.get_db)):
    """
    Get feedback details for a specific docket number.
    """
    user = await get_current_user(token, db)
    user = user.username.lower()

    query = "SELECT DocketNumber FROM tblfeedback WHERE userexperience = %s"
    con = connectDB_alchemy()
    df = pd.read_sql(query, con, params=(item.userexperience,))
    if df.empty:
        raise HTTPException(status_code=404, detail="No feedback found for the given user experience.")
    
    updated_results = list(df["DocketNumber"])
    result = df.to_dict(orient='index')
    return {"feedback_id": updated_results}

# get_feedback_stats that will return the count of feedback entries grouped by rating and total count
# @router.get("/get_feedback_stats")
# async def get_feedback_stats(token : Annotated[str, Depends(oauth2_scheme)], 
#                              sector: str = "All",
#                              companyname: str = "All",
#                              category: str = "All",
#                              db: Session = Depends(database.get_db)):
#     """
#     Get feedback statistics
#     1) Count of feedback entries grouped by rating
#     2) Total count of feedback entries
#     3) 0 - unknown, 1 - very_poor, 2 - poor, 3 - good, 4 - very_good, 5 - excellent
#     """
#     user = await get_current_user(token, db)
#     user = user.username.lower()

#     query = """
#     SELECT 
#         rating, 
#         COUNT(*) AS count 
#     FROM 
#         tblfeedback 
#     GROUP BY 
#         rating
#     """

#     if sector != "All":
#         query += " HAVING Sector = '%s'" % sector
#     if companyname != "All":
#         query += " AND CompanyName = '%s'" % companyname
#     if category != "All":
#         query += " AND Category = '%s'" % category

#     con = connectDB_alchemy()
#     df = pd.read_sql(query, con)

#     if df.empty:
#         raise HTTPException(status_code=404, detail="No feedback statistics found.")
    

#     total_count = int(df['count'].sum())  # Convert numpy.int64 to Python int
#     result = df.to_dict(orient='records')
#     return {
#         "total_count": total_count,
#         "feedback_stats": result
        
#     }

@router.get("/get_feedback_stats")
async def get_feedback_stats(
    token: Annotated[str, Depends(oauth2_scheme)],
    sector: str = "All",
    companyname: str = "All",
    category: str = "All",
    start_date: str = "2024-10-13 00:00:00",
    end_date: str = "2025-10-06 00:00:00",
    db: Session = Depends(database.get_db)
):
    """
    Get feedback statistics
    1) Count of feedback entries grouped by rating
    2) Total count of feedback entries
    3) 0 - unknown, 1 - very_poor, 2 - poor, 3 - good, 4 - very_good, 5 - excellent
    """
    user = await get_current_user(token, db)
    user = user.username.lower()

    query = """
        SELECT 
            rating, 
            COUNT(*) AS count 
        FROM 
            tblfeedback
    """
    filters = []
    params = []

    if sector != "All":
        filters.append("Sector = %s")
        params.append(sector)
    if companyname != "All":
        filters.append("CompanyName = %s")
        params.append(companyname)
    if category != "All":
        filters.append("Category = %s")
        params.append(category)
    if start_date and end_date:
        filters.append("created_at >= %s AND created_at <= %s")
        params.extend([start_date, end_date])

    if filters:
        query += " WHERE " + " AND ".join(filters)
    
    query += " GROUP BY rating"

    print("Final Query:", query, params)
    
    con = connectDB_alchemy()
    df = pd.read_sql(query, con, params=tuple(params))
    
    if df.empty:
        raise HTTPException(status_code=404, detail="No feedback statistics found.")

    total_feedback_count = int(df['count'].sum())
    result = df.to_dict(orient='records')
    return {
        "total_feedback_count": total_feedback_count,
        "feedback_stats": result
    }

@router.get("/get_feedback_by_rating/{rating}")
async def get_feedback_by_rating(
    token : Annotated[str, Depends(oauth2_scheme)],
    rating: int,
    sector: str = "All",
    companyname: str = "All",
    category: str = "All",
    start_date: str = "2024-10-13 00:00:00",
    end_date: str = "2025-10-06 00:00:00",
    skip: int = 0,
    size: int = 100,
    db: Session = Depends(database.get_db)
):
    """
    Get feedback entries by specific rating.
    Able to filter by Sector, CompanyName, Category and date range.
    Ratings: excellent - 5, very_good - 4, good - 3, poor - 2, very_poor - 1, unknown - 0
    """
    user = await get_current_user(token, db)
    user = user.username.lower()

    rating_mapping = {
        5: "excellent",
        4: "very_good",
        3: "good",
        2: "poor",
        1: "very_poor",
        0: "unknown"
    }

    if rating not in rating_mapping:
        raise HTTPException(status_code=400, detail="Invalid rating. Must be between 0 and 5.")

    params = []
    filters = []

    if sector != "All":
        filters.append("Sector = %s")
        params.append(sector)
    if companyname != "All":
        filters.append("CompanyName = %s")
        params.append(companyname)
    if category != "All":
        filters.append("Category = %s")
        params.append(category)
    if start_date and end_date:
        filters.append("created_at >= %s AND created_at <= %s")
        params.extend([start_date, end_date])

    query = "SELECT id, Docketnumber, Remark FROM tblfeedback WHERE rating = %s"
    params = [rating] + params
    if filters:
        query += " AND " + " AND ".join(filters)
    query += " order by id desc LIMIT %s OFFSET %s"
    params.extend([size, skip])

    con = connectDB_alchemy()
    df = pd.read_sql(query, con, params=tuple(params))
    if df.empty:
        raise HTTPException(status_code=404, detail="No feedback found for the given rating.")

    result = df.to_dict(orient='records')
    return {"feedback": result}