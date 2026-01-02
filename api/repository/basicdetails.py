import sys
from pathlib import Path
from fastapi import APIRouter
import pandas as pd
router = APIRouter(tags=["Basic Features"])
import json
from sqlalchemy.sql import text

# ---------------------------- Path Management ----------------------------
resources_dir = Path(__file__).resolve().parents[2] / "resources"
sys.path.append(str(resources_dir))
# ---------------------------- Import External Utilities ----------------------------
from utility import getES, getEmbed, load_config, connectDB_alchemy, connectDB, closeDB
config = load_config()
# ---------------------------- Constants ----------------------------



MAPPING_STATE_ID_TO_NAME_PATH = resources_dir / Path(config["MAPPING_STATE_ID_TO_NAME_PATH"]).name
MAPPING_CITY_ID_TO_NAME_PATH = resources_dir / Path(config["MAPPING_CITY_ID_TO_NAME_PATH"]).name

with open(MAPPING_STATE_ID_TO_NAME_PATH, 'r') as f:
    MAPPING_STATE = json.load(f)
with open(MAPPING_CITY_ID_TO_NAME_PATH, 'r') as f:
    MAPPING_CITY = json.load(f)

MAPPING_STATE_NAME_TO_ID_PATH = resources_dir / Path(config["MAPPING_STATE_NAME_TO_ID_PATH"]).name
MAPPING_CITY_NAME_TO_ID_PATH = resources_dir / Path(config["MAPPING_CITY_NAME_TO_ID_PATH"]).name

with open(MAPPING_STATE_NAME_TO_ID_PATH, 'r') as f:
    MAPPING_STATE_NAME_TO_ID = json.load(f)
with open(MAPPING_CITY_NAME_TO_ID_PATH, 'r') as f:
    MAPPING_CITY_NAME_TO_ID = json.load(f)

MAPPING_CATEGORY_ID_TO_NAME_PATH = resources_dir / Path(config["MAPPING_CATEGORY_ID_TO_NAME_PATH"]).name
MAPPING_CATEGORY_NAME_TO_ID_PATH = resources_dir / Path(config["MAPPING_CATEGORY_NAME_TO_ID_PATH"]).name
MAPPING_SECTOR_ID_TO_NAME_PATH = resources_dir / Path(config["MAPPING_SECTOR_ID_TO_NAME_PATH"]).name
MAPPING_SECTOR_NAME_TO_ID_PATH = resources_dir / Path(config["MAPPING_SECTOR_NAME_TO_ID_PATH"]).name

with open(MAPPING_CATEGORY_ID_TO_NAME_PATH, 'r') as f:
    MAPPING_CATEGORY = json.load(f)
with open(MAPPING_CATEGORY_NAME_TO_ID_PATH, 'r') as f:
    MAPPING_CATEGORY_NAME_TO_ID = json.load(f)
with open(MAPPING_SECTOR_ID_TO_NAME_PATH, 'r') as f:
    MAPPING_SECTOR = json.load(f)
with open(MAPPING_SECTOR_NAME_TO_ID_PATH, 'r') as f:
    MAPPING_SECTOR_NAME_TO_ID = json.load(f)





# ---------------------------- Logs Directory Setup ----------------------------
BASE_DIR = Path("logs")
BASE_DIR.mkdir(exist_ok=True)

# def getcomplaintDetails(complain_number: str):
#     '''
#     A function to get complaint details from the database based on complaint_number
#     '''

#     print(f"Fetching details for complaint number: {complain_number}")  
#     connection = connectDB_alchemy()
#     if connection is None:
#         return {"error": "Database connection failed."}
#     query = f"SELECT * FROM tblcomplaints WHERE complainNumber = '{complain_number}'"
#     query2 = f"SELECT * FROM tblfeedback WHERE Docketnumber = '{complain_number}'"
#     try:
#         df = pd.read_sql(query, connection)
#         if df.empty:
#             return {"error": f"No complaint found with number: {complain_number}"}
#         df_feedback = pd.read_sql(query2, connection)
#         print(df_feedback)
#         if not df_feedback.empty:
#             # Merge feedback details into the main dataframe
#             feedback_columns = ['ExperiencewithNCH', 'userexperience', 'unUnsatisfactory', 'Remark', 'created_at', 'updated_at']
#             for col in feedback_columns:
#                 if col in df_feedback.columns:
#                     df[col] = df_feedback.iloc[0][col]
#             df = df.merge(df_feedback[['Docketnumber']], left_on='complainNumber', right_on='Docketnumber', how='left')
#             df.drop(columns=['Docketnumber'], inplace=True)
#         # Process state and city names
#         df['stateName'] = df['stateCode'].map(MAPPING_STATE).fillna('Unknown')
#         # df['CityName'] = df['cityCode'].map(MAPPING_CITY).fillna('Unknown')
#         # print(f"State and City names mapped. Sample states: {df['stateName'].unique()[:5]}, Sample cities: {df['CityName'].unique()
#         return df.to_dict(orient='records')[0]  # Return the first record as a dictionary
#     except Exception as e:
#         return {"error": f"Failed to load complaint details: {e}"}

def getcomplaintDetails(complain_number: str):
    '''
    A function to get complaint details from the database based on complaint_number
    '''
    print(f"Fetching details for complaint number: {complain_number}")  
    connection = connectDB_alchemy()
    if connection is None:
        return {"error": "Database connection failed."}
    
    try:
        # Use parameterized queries to prevent SQL injection
        query = "SELECT * FROM tblcomplaints WHERE complainNumber = %(complain_number)s"
        query2 = "SELECT * FROM tblfeedback WHERE Docketnumber = %(complain_number)s"
        
        params = {'complain_number': complain_number}
        
        # Fetch complaint details
        df = pd.read_sql(query, connection, params=params)
        if df.empty:
            connection.dispose()
            return {"error": f"No complaint found with number: {complain_number}"}
        
        # Fetch feedback details
        df_feedback = pd.read_sql(query2, connection, params=params)
        print(df_feedback)
        
        if not df_feedback.empty:
            # Ensure both columns have the same data type before merging
            df['complainNumber'] = df['complainNumber'].astype(str)
            df_feedback['Docketnumber'] = df_feedback['Docketnumber'].astype(str)
            
            # Select only the feedback columns we need
            feedback_columns = ['Docketnumber', 'ExperiencewithNCH', 'userexperience', 
                              'unUnsatisfactory', 'Remark', 'created_at', 'updated_at']
            
            # Filter to only existing columns
            available_columns = [col for col in feedback_columns if col in df_feedback.columns]
            df_feedback_filtered = df_feedback[available_columns]
            
            # Merge feedback details with complaint details
            df = df.merge(
                df_feedback_filtered, 
                left_on='complainNumber', 
                right_on='Docketnumber', 
                how='left'
            )
            
            # Drop the duplicate Docketnumber column after merge
            if 'Docketnumber' in df.columns:
                df.drop(columns=['Docketnumber'], inplace=True)
        
        # Process state names
        if 'stateCode' in df.columns:
            df['stateName'] = df['stateCode'].astype(str).map(MAPPING_STATE).fillna('Unknown')
        
        # Process city names (uncomment if needed)
        # if 'cityCode' in df.columns:
        #     df['CityName'] = df['cityCode'].astype(str).map(MAPPING_CITY).fillna('Unknown')
        
        # Handle NaN values
        df = df.fillna('N/A')
        
        # Clean up connection
        connection.dispose()
        
        # Return the first record as a dictionary
        return df.to_dict(orient='records')[0]
        
    except Exception as e:
        if connection:
            connection.dispose()
        print(f"Error details: {str(e)}")
        return {"error": f"Failed to load complaint details: {e}"}


# def getUserDetails(userIds):
#     '''
#     A function to get user details from the database based on userIds
#     '''
#     connection = connectDB_alchemy()
#     if connection is None:
#         return {"error": "Database connection failed."}
#     query = f"SELECT userId, firstName, lastName, stateCode, CityCode, country, userType, status, activation, region, updationDate, estatus, source FROM tblregistration WHERE userId IN ({','.join(map(str, userIds))})"
#     # try:
#     df = pd.read_sql(query, connection)
  
#     df['stateName'] = df['stateCode'].map(MAPPING_STATE).fillna('Unknown')
#     df['CityName'] = df['CityCode'].map(MAPPING_CITY).fillna('Unknown')

#     print(f"State and City names mapped. Sample states: {df['stateName'].unique()[:5]}, Sample cities: {df['CityName'].unique()[:5]}")
#     df['fullName'] = df['firstName'].fillna('') + ' ' + df['lastName'].fillna('')
    
#     df = df.drop(columns=['firstName', 'lastName', 'stateCode', 'CityCode'])
#     df['fullName'] = df['fullName'].str.strip()

#     return df.to_dict(orient='records')



def getLastComplaints():
    """
    A function to get last 1000 complaints from the database
    """

    print("Fetching last 1000 complaints")

    connection = connectDB_alchemy()
    if connection is None:
        return {"error": "Database connection failed."}

    try:
        # Raw SQL query
        query = """
        SELECT *
        FROM tblcomplaints
        ORDER BY complainNumber DESC
        LIMIT 1
        """

        # Execute query
        df = pd.read_sql(query, connection)

        if df.empty:
            connection.dispose()
            return {"error": "No complaints found."}

        # Process state names
        if 'stateCode' in df.columns:
            df['stateName'] = (
                df['stateCode']
                .astype(str)
                .map(MAPPING_STATE)
                .fillna('Unknown')
            )

        # Handle NaN values
        df = df.fillna('N/A')

        # Clean up connection
        connection.dispose()

        # Return all records
        return df.to_dict(orient='records')

    except Exception as e:
        if connection:
            connection.dispose()
        print(f"Error details: {str(e)}")
        return {"error": f"Failed to load last complaints: {e}"}



def getUserDetails(userIds):
    """
    A function to get user details from the database based on userIds
    (MySQL parameterized query using %s)
    """

    if not userIds:
        return []

    con = connectDB()  # MySQL connection (not SQLAlchemy)
    if con is None:
        return {"error": "Database connection failed."}

    placeholders = ",".join(["%s"] * len(userIds))

    query = f"""
        SELECT userId, firstName, lastName, stateCode, CityCode, country,
               userType, status, activation, region, updationDate,
               estatus, source
        FROM tblregistration
        WHERE userId IN ({placeholders})
    """

    # try:
    cursor = con.cursor(dictionary=True)
    cursor.execute(query, tuple(userIds))
    rows = cursor.fetchall()

    df = pd.DataFrame(rows)

    if df.empty:
        return []

    df['stateName'] = df['stateCode'].map(MAPPING_STATE).fillna('Unknown')
    df['CityName'] = df['CityCode'].map(MAPPING_CITY).fillna('Unknown')

    df['fullName'] = (
        df['firstName'].fillna('') + ' ' + df['lastName'].fillna('')
    ).str.strip()

    df = df.drop(columns=['firstName', 'lastName', 'stateCode', 'CityCode'])

    return df.to_dict(orient='records')

    # finally:
    #     cursor.close()
    #     closeDB(con)



# def getCompanyDetails(companyName, sectorname):
#     '''
#     A function to get company details from the database based on companyName and sectorname
#     '''
#     connection = connectDB_alchemy()
#     if connection is None:
#         return {"error": "Database connection failed."}
#     query = f"SELECT companyId, legalName, sectorName, address, email, phone1, phone2, address1, address2, cityid, stateid FROM tblcompany WHERE companyName LIKE `%{companyName}%` OR sectorName LIKE '%{sectorname}%'"
#     try:
#         df = pd.read_sql(query, connection)
#         return df.to_dict(orient='records')
#     except Exception as e:
#         return {"error": f"Failed to load company details: {e}"}


def getCompanyDetails(companyName, sectorname):
    connection = connectDB_alchemy()
    if connection is None:
        return {"error": "Database connection failed."}

    query = text("""
        SELECT companyId, legalName, sectorName, address, email, phone1, phone2,
               address1, address2, cityid, stateid
        FROM tblcompany
        WHERE companyName LIKE :companyName
           OR sectorName LIKE :sectorName
    """)

    params = {
        "companyName": f"%{companyName}%",
        "sectorName": f"%{sectorname}%"
    }

    try:
        df = pd.read_sql(query, connection, params=params)
        return df.to_dict(orient="records")
    except Exception as e:
        return {"error": f"Failed to load company details: {e}"}


def process_grievance_data(grievance_data: list) -> list:
    """
    Process grievance data by adding user details and formatting the response.
    
    Parameters
    ----------
    grievance_data : list
        List of grievance dictionaries containing complaint details
        
    Returns
    -------
    list
        Processed grievance data with user details
    """
    # try:
    # Convert to DataFrame
    grievancedf = pd.DataFrame(grievance_data)
    if grievancedf.empty:
        return []

    # Get user details
    userIds = grievancedf['userId'].tolist()
    user_details = getUserDetails(userIds)
    user_detailsdf = pd.DataFrame(user_details)

    # Merge with user details
    grievancedf = grievancedf.merge(user_detailsdf, on="userId", how="left")

    # Select required columns
    columns = [
        'id', 'complaintDetails', 'userId', 'fullName', 
        'CityName', 'stateName', 'country', 'userType', 
        'status', 'complaintRegDate', 'updationDate', 
        'complaintType', 'complaintMode', 'categoryCode', 
        'companyName', 'complaintStatus', 'companyStatus', 
        'lastUpdationDate'
    ]
    grievancedf = grievancedf[columns]

    # Handle missing values
    grievancedf = grievancedf.fillna('nan')

    # Convert back to records
    return grievancedf.to_dict(orient='records')

    # except Exception as e:
    #     print(f"Error processing grievance data: {str(e)}")
    #     return []
    


def getCompanyDetails(sectorname="All", companyname="All", categoryname="All"):
    '''
    A function to get company details from the database based on companyname and sectorname
    '''
    connection = connectDB_alchemy()
    if connection is None:
        return {"error": "Database connection failed."}
    
    try:
        # Build the WHERE clause dynamically based on parameters
        where_conditions = []
        params = {}
        
        if companyname != "All" and companyname.strip():
            where_conditions.append("companyname LIKE %(companyname)s")
            params['companyname'] = f"%{companyname}%"
        
        if sectorname != "All" and sectorname.strip():
            where_conditions.append("sectorname LIKE %(sectorname)s")
            params['sectorname'] = f"%{sectorname}%"

        if categoryname != "All" and categoryname.strip():
            where_conditions.append("catname LIKE %(categoryname)s")
            params['categoryname'] = f"%{categoryname}%"
        
        # Base query with lowercase column names
        base_query = "SELECT companyname, catname, sectorname FROM tblcompany"
        
        # Add WHERE clause if conditions exist
        if where_conditions:
            query = f"{base_query} WHERE {' OR '.join(where_conditions)}"
        else:
            # If both parameters are "All", return all records (with limit)
            query = f"{base_query} LIMIT 1000"
        
        # Execute query with parameters to prevent SQL injection
        df = pd.read_sql(query, connection, params=params)
        
        # Clean up connection
        connection.dispose()
        
        return df.to_dict(orient='records')
        
    except Exception as e:
        if connection:
            connection.dispose()
        return {"error": f"Failed to load company details: {e}"}


    # state_name: str
    # sector_name: str
    # category_name: str
    # attribute: str
    # skip: int = 0
    # limit: int = 20

# def getComplaintDistribution(attribute, stateName="All", sectorName="All", categoryName="All", skip=0, limit=20):
#     '''
#     A function to get complaint distribution by a specified attribute.
#     Valid attributes: 'stateCode', 'complaintType', 'complaintMode', 'sectorCode', 'categoryCode', 'complaintStatus', 'companyStatus'
#     '''
#     valid_attributes = ['stateName', 'complaintType', 'complaintMode', 'sectorName', 'categoryName', 'complaintStatus', 'companyStatus']
#     if attribute not in valid_attributes:
#         return {"error": f"Invalid attribute. Must be one of {valid_attributes}"}


#     query = f"select distinct {attribute}, count(*) as count from tblcomplaints group by {attribute} order by count desc limit {skip}, {limit}".format(attribute=attribute, skip=skip, limit=limit)
#     filters = []
#     params = {}

#     # Dynamic filters
#     if stateName != "All":
#         if stateName in MAPPING_STATE_NAME_TO_ID:
#             stateCode = MAPPING_STATE_NAME_TO_ID(stateName)
#         else:
#             return {"error": f"Invalid state name: {stateName}"}
#         filters.append("stateCode = %(stateCode)s")
#         params['stateCode'] = stateCode

#     if sectorName != "All":
#         filters.append("sectorCode = %(sectorName)s")
#         params['sectorName'] = sectorName

#     if categoryName != "All":
#         filters.append("categoryCode = %(categoryName)s")
#         params['categoryName'] = categoryName

#     # Combine filters
#     if filters:
#         query += " WHERE " + " AND ".join(filters)

#     # Add grouping, sorting, limit, offset

#     if attribute == stateName:
#         attribute = stateCode

#     query += f" GROUP BY {attribute} ORDER BY count DESC LIMIT %(limit)s OFFSET %(skip)s"
#     params['limit'] = limit
#     params['skip'] = skip

#     con = connectDB_alchemy()
#     df = pd.read_sql(query, con, params=params)
#     result = df.to_dict(orient='records')
#     return {"distribution": result}


def getComplaintDistribution(attribute, start_date, end_date, stateName="All", sectorName="All", categoryName="All", skip=0, limit=20):
    '''
    A function to get complaint distribution by a specified attribute.
    Valid attributes: 'stateName', 'complaintType', 'complaintMode', 'sectorName', 'categoryName', 'complaintStatus', 'companyStatus'
    '''
    valid_attributes = ['stateName', 'complaintType', 'complaintMode', 'sectorName', 'categoryName', 'complaintStatus', 'companyStatus']
    if attribute not in valid_attributes:
        return {"error": f"Invalid attribute. Must be one of {valid_attributes}"}

    connection = connectDB_alchemy()
    if connection is None:
        return {"error": "Database connection failed."}
    
    try:
        # Map attribute names to actual database column names
        attribute_mapping = {
            'stateName': 'stateCode',
            'sectorName': 'sectorCode',
            'categoryName': 'categoryCode',
            'complaintType': 'complaintType',
            'complaintMode': 'complaintMode',
            'complaintStatus': 'complaintStatus',
            'companyStatus': 'companyStatus'
        }
        
        db_attribute = attribute_mapping.get(attribute, attribute)
        
        # Build base query with parameterized attribute
        filters = []
        params = {}

        # Dynamic filters
        if stateName != "All":
            if stateName in MAPPING_STATE_NAME_TO_ID:
                stateCode = MAPPING_STATE_NAME_TO_ID[stateName]  # Fixed: use [] instead of ()
                filters.append("stateCode = %(stateCode)s")
                params['stateCode'] = stateCode
            else:
                connection.dispose()
                return {"error": f"Invalid state name: {stateName}"}

        if sectorName != "All":
            if sectorName in MAPPING_SECTOR_NAME_TO_ID:
                sectorCode = MAPPING_SECTOR_NAME_TO_ID[sectorName]
                filters.append("sectorCode = %(sectorCode)s")
                params['sectorCode'] = sectorCode
            else:
                connection.dispose()
                return {"error": f"Invalid sector name: {sectorName}"}
            filters.append("sectorCode = %(sectorName)s")
            params['sectorName'] = sectorName

        if categoryName != "All":
            if categoryName in MAPPING_CATEGORY_NAME_TO_ID:
                categoryCode = MAPPING_CATEGORY_NAME_TO_ID[categoryName]
                filters.append("categoryCode = %(categoryCode)s")
                params['categoryCode'] = categoryCode
            else:
                connection.dispose()
                return {"error": f"Invalid category name: {categoryName}"}
            filters.append("categoryCode = %(categoryName)s")
            params['categoryName'] = categoryName

        # Date range filter
        if start_date and end_date:
            filters.append("complaintRegDate >= %(start_date)s AND complaintRegDate <= %(end_date)s")
            params['start_date'] = start_date
            params['end_date'] = end_date

        # Build the query
        if filters:
            where_clause = " WHERE " + " AND ".join(filters)
        else:
            where_clause = ""

        # Use safe query construction - attribute name cannot be parameterized
        query = f"""
            SELECT {db_attribute} as attribute_value, COUNT(*) as count 
            FROM tblcomplaints
            {where_clause}
            GROUP BY {db_attribute} 
            ORDER BY count DESC 
            LIMIT %(limit)s OFFSET %(skip)s
        """
        
        params['limit'] = limit
        params['skip'] = skip

        # Execute query
        df = pd.read_sql(query, connection, params=params)
        
        # Map codes back to names if needed
        if attribute == 'stateName' and not df.empty:
            df['attribute_value'] = df['attribute_value'].astype(str).map(MAPPING_STATE).fillna('Unknown')
        
        elif attribute == 'sectorName' and not df.empty:
            df['attribute_value'] = df['attribute_value'].astype(str).map(MAPPING_SECTOR).fillna('Unknown')
        
        elif attribute == 'categoryName' and not df.empty:
            df['attribute_value'] = df['attribute_value'].astype(str).map(MAPPING_CATEGORY).fillna('Unknown')

        # Clean up connection
        connection.dispose()
        
        result = df.to_dict(orient='records')
        return {"distribution": result}
        
    except Exception as e:
        if connection:
            connection.dispose()
        print(f"Error in getComplaintDistribution: {str(e)}")
        return {"error": f"Failed to get complaint distribution: {e}"}
    


def getFeedbackDistribution(start_date, end_date, attribute, sectorName="All", companyName="All", categoryName="All", skip=0, limit=20):
    '''
    A function to get complaint distribution by a specified attribute.
    Valid attributes: 'stateName', 'complaintType', 'complaintMode', 'sectorName', 'categoryName', 'complaintStatus', 'companyStatus'
    '''
    valid_attributes = ['Sector', 'CompanyName', 'Category', 'ExperiencewithNCH', 'userexperience', 'unUnsatisfactory']
    if attribute not in valid_attributes:
        return {"error": f"Invalid attribute. Must be one of {valid_attributes}"}

    connection = connectDB_alchemy()
    if connection is None:
        return {"error": "Database connection failed."}
    
    try:
        # Map attribute names to actual database column names
        attribute_mapping = {
            'stateName': 'stateCode',
            'sectorName': 'sectorCode',
            'categoryName': 'categoryCode',
            'complaintType': 'complaintType',
            'complaintMode': 'complaintMode',
            'complaintStatus': 'complaintStatus',
            'companyStatus': 'companyStatus'
        }
        
        db_attribute = attribute_mapping.get(attribute, attribute)
        
        # Build base query with parameterized attribute
        filters = []
        params = {}

        # Dynamic filters
        if companyName != "All":
            filters.append("CompanyName = %(companyName)s")
            params['companyName'] = companyName

        if sectorName != "All":
            filters.append("Sector = %(sectorName)s")
            params['sectorName'] = sectorName

        if categoryName != "All":
            filters.append("Category = %(categoryName)s")
            params['categoryName'] = categoryName

        # Date range filter
        if start_date and end_date:
            filters.append("created_at >= %(start_date)s AND created_at <= %(end_date)s")
            params['start_date'] = start_date
            params['end_date'] = end_date

        # Build the query
        if filters:
            where_clause = " WHERE " + " AND ".join(filters)
        else:
            where_clause = ""

        # Use safe query construction - attribute name cannot be parameterized
        query = f"""
            SELECT {db_attribute} as attribute_value, COUNT(*) as count 
            FROM tblfeedback
            {where_clause}
            GROUP BY {db_attribute} 
            ORDER BY count DESC 
            LIMIT %(limit)s OFFSET %(skip)s
        """
        
        params['limit'] = limit
        params['skip'] = skip

        # Execute query
        df = pd.read_sql(query, connection, params=params)
        
        # Clean up connection
        connection.dispose()
        
        result = df.to_dict(orient='records')
        return {"distribution": result}
        
    except Exception as e:
        if connection:
            connection.dispose()
        print(f"Error in getComplaintDistribution: {str(e)}")
        return {"error": f"Failed to get complaint distribution: {e}"}