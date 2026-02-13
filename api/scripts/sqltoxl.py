import sys
import pandas as pd
from pathlib import Path

# Add project root to sys.path
# api/scripts/sqltoxl.py -> parents[0]=scripts, parents[1]=api, parents[2]=root
project_root = Path(__file__).resolve().parents[2]
sys.path.append(str(project_root))

from resources.utility import connectDB_alchemy, closeDB
import traceback

import re

# Database connection
try:
    # Use SQLAlchemy engine for pandas
    db_engine = connectDB_alchemy()
    print("Database engine created successfully.")
except Exception as e:
    print(f"Failed to connect to database: {e}")
    traceback.print_exc()
    sys.exit(1)

# Table name
table_name = "tblfeedback"

# SQL query
query = f"SELECT * FROM {table_name}"

def clean_text(text):
    if isinstance(text, str):
        # Remove characters that are illegal in Excel (control characters)
        return re.sub(r'[\000-\010]|[\013-\014]|[\016-\037]', '', text)
    return text

try:
    # Read data into DataFrame
    # pd.read_sql works best with SQLAlchemy engine
    df = pd.read_sql(query, db_engine)
    
    print(f"Data read successfully. Rows: {len(df)}")
    
    # Sanitize data for Excel
    print("Sanitizing data...")
    for col in df.columns:
        if df[col].dtype == 'object':  # Apply only to string-like columns
            df[col] = df[col].apply(clean_text)

    # Export to Excel
    output_file = "output.xlsx"

    df.to_excel(output_file, index=False, sheet_name='Sheet1', engine='openpyxl')
    print("Excel file created:", output_file)

except Exception as e:
    print(f"Error executing query or saving file: {e}")
    traceback.print_exc()

# database.py / utility.py logic suggests connectDB_alchemy returns an engine, 
# which acts as a connection factory. We don't necessarily need to "close" it explicitly 
# in the same way as a raw connection, but we can dispose it if needed.
# However, the script ends here, so it's fine.

