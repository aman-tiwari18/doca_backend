from pathlib import Path
import sys
import pandas as pd
from sqlalchemy import text
from sklearn.feature_extraction.text import TfidfVectorizer

# ---------------------------- Path Management ----------------------------
resources_dir = Path(__file__).resolve().parents[2] / "resources"
sys.path.append(str(resources_dir))

# ---------------------------- Import External Utilities ----------------------------
from utility import getES, getEmbed, load_config, connectDB_alchemy

config = load_config()

# ---------------------------- DB Engine ----------------------------
engine = connectDB_alchemy(engine=True)
if engine is None:
    raise RuntimeError("Database engine creation failed")

# ---------------------------- Query ----------------------------
QUERY_TO_FETCH_COMPANY_DETAILS = """
SELECT id, CompanyName, Sector, Category, Remark
FROM tblfeedback
"""

# ---------------------------- Fetch Data ----------------------------
df = pd.read_sql(QUERY_TO_FETCH_COMPANY_DETAILS, engine)

if df.empty:
    print("⚠️ No data found in tblfeedback")
    sys.exit(0)

# ---------------------------- Prepare Remarks ----------------------------
remarks = df["Remark"].fillna("").tolist()

# ---------------------------- TF-IDF Computation ----------------------------
vectorizer = TfidfVectorizer(stop_words="english")
vectorizer.fit(remarks)

terms = vectorizer.get_feature_names_out()
idf_values = vectorizer.idf_

idf_data = pd.DataFrame({
    "keyword": terms,
    "idf_score": idf_values
})

# ---------------------------- Create Table ----------------------------
create_table_query = text("""
CREATE TABLE IF NOT EXISTS remark_keywords (
    id INT AUTO_INCREMENT PRIMARY KEY,
    keyword VARCHAR(255),
    idf_score FLOAT,
    CompanyName VARCHAR(250),
    Sector VARCHAR(100),
    Category VARCHAR(100)
)
""")

with engine.begin() as conn:
    conn.execute(create_table_query)

# ---------------------------- Insert Keywords (Parameterized) ----------------------------
insert_query = text("""
INSERT INTO remark_keywords (keyword, idf_score, CompanyName, Sector, Category)
VALUES (:keyword, :idf_score, :company, :sector, :category)
""")

with engine.begin() as conn:
    for _, row in df.iterrows():
        company = row["CompanyName"] or ""
        sector = row["Sector"] or ""
        category = row["Category"] or ""
        remark_text = row["Remark"] or ""

        tfidf_vector = vectorizer.transform([remark_text])
        feature_indices = tfidf_vector.nonzero()[1]

        for idx in feature_indices:
            conn.execute(
                insert_query,
                {
                    "keyword": terms[idx],
                    "idf_score": float(vectorizer.idf_[idx]),
                    "company": company,
                    "sector": sector,
                    "category": category
                }
            )

print("✅ Keywords with IDF scores have been stored successfully.")
