#  Step1 : Import libraries
import pandas as pd
from bertopic import BERTopic
import numpy as np
import re
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
import sys
import json
from pathlib import Path
from datetime import datetime, timedelta

# Download required NLTK data
try:
    nltk.download('stopwords', quiet=True)
    nltk.download('punkt', quiet=True)
except:
    print("[WARNING] Could not download NLTK data")

#  Step2 : Import custom libraries
# Move up 1 level to reach resources directory (was 3 levels, likely incorrect)
resources_dir = Path(__file__).resolve().parents[1] / "resources"
sys.path.append(str(resources_dir))

try:
    from utility import load_config, getES, connectDB, closeDB
    config = load_config()
    INDEX_NAME = config["ES"]["INDEX_NAME"]
    es = getES()

    if es is None:
        print("Elasticsearch connection failed")
        sys.exit(1)
except ImportError as e:
    print(f"[ERROR] Failed to import utility modules: {e}")
    sys.exit(1)

#  Step3: Load data from ES
def load_es_data(start_date, end_date, ministry, index=INDEX_NAME):
    """
    Load data from Elasticsearch based on date range and ministry.
    """
    # Add ministry filter to the query
    query = {
        "size": 10000,
        "sort": [{"complaintRegDate": {"order": "asc"}}],
        "query": {
            "bool": {
                "must": [
                    {
                        "range": {
                            "complaintRegDate": {
                                "gte": start_date,
                                "lte": end_date,
                                # "format": "yyyy-MM-dd"
                            }
                        }
                    }
                   
                ]
            }
        },
        "_source": ["complaintDetails", "complaintDetails_vector"]
    }

    try:
        response = es.search(index=index, body=query)
    except Exception as e:
        print(f"[ERROR] Elasticsearch query failed: {e}")
        return pd.DataFrame()

    records = []
    for hit in response.get("hits", {}).get("hits", []):
        complaint_details = hit["_source"].get("complaintDetails", "")
        complaint_vector = hit["_source"].get("complaintDetails_vector", [])
        
        # Skip if essential data is missing
        if not complaint_details or not complaint_vector:
            continue
            
        records.append({
            "complaintNumber": hit["_id"].replace("_", "/"),
            "complaintDetails": complaint_details,
            "complaintDetails_vector": complaint_vector
        })

    df = pd.DataFrame(records)
    print(f"[INFO] Retrieved {len(df)} records from Elasticsearch.")
    return df

#  Step4: Preprocess data
# Initialize stopwords with error handling
try:
    stop = stopwords.words("english")
except:
    print("[WARNING] Could not load English stopwords, using empty list")
    stop = []

stop.extend(["raha","tha","diya","ne","ja","tak","mein","dwara","jaye","kare","kar","kiya","koi","par","gaya","jo","mera","mujhe","mai","ji","se","ke","bhi","ho","aur","nhi","nahi","hu","meri","hi","sir","ko","ka","mere","ki","shri","also","may","madam","please","hai","kindly","thank","में","के","पर","कर","पर","रह","ke","और","se","aur",'~', ':', "'", '+', '[', '\\', '@', '^', '{', '%', '(', '-', '"', '*', '|', ',', '&', '<', '`', '}', '.', '_', '=', ']', '!', '>', ';', '?', '#', '$', ')', '/',"कर","नह","रह","पत","टर","मह","पर","गय","अस","रत"])

def preprocess(text):
    if pd.isna(text):
        return ""
    
    text = str(text)
    text = text.lower()
    text = text.replace('{html}'," ")
    cleanr = re.compile('<.*?>')
    cleantext = re.sub(cleanr, ' ', text)
    rem_url = re.sub(r'http\S+', ' ', cleantext)
    rem_spe = re.sub(r"[-()\"#/@;:<>{}`+=~|.!?,]", " ", rem_url)
    rem_num = re.sub('[^A-Za-z]+', ' ', rem_spe)
    
    try:
        tokens = word_tokenize(rem_num)
        processed_docs = [word for word in tokens if word not in stop and len(word) > 2]
        processed_docs = ' '.join(processed_docs)
    except:
        # Fallback if tokenization fails
        words = rem_num.split()
        processed_docs = ' '.join([word for word in words if word not in stop and len(word) > 2])
    
    return processed_docs

def preprocess_data(data):
    """
    Preprocess 'complaintDetails' and drop empty processed rows.
    Returns a cleaned DataFrame.
    """
    print("[INFO] Starting preprocessing of complaint content...")
    
    if data.empty:
        print("[WARNING] Empty dataframe provided for preprocessing")
        return data
    
    data = data.copy()  # Avoid modifying original dataframe
    data["preprocessed"] = data["complaintDetails"].apply(preprocess)
    data = data[["complaintNumber", "preprocessed", "complaintDetails_vector"]]
    data = data.dropna()  # drop rows with NaN values
    data = data[data["preprocessed"].str.strip() != ""]  # drop empty after stripping
    # delete row if complaintDetails length is less than 5
    data = data[data["preprocessed"].str.len() > 5]
    # reset index
    data.reset_index(drop=True, inplace=True)
    # drop duplicates
    data = data.drop_duplicates(subset=["preprocessed"], keep="first")
    print(f"[INFO] Preprocessing complete. Data shape: {data.shape}")
    return data

# Function to generate dataframe for a given level 
def generate_df(i, level_df):
    new_df = level_df[level_df.topic == i].copy()
    new_df.reset_index(drop=True, inplace=True)
    new_df = new_df.drop('topic', axis=1)
    return new_df

# similarity function to check if two list are more than or equal to 80% similar 
def is_similar(list1, list2, threshold=0.6):
    """
    Check if two lists are similar based on Jaccard similarity.
    Similarity is calculated as the size of the intersection divided by the size of the union.
    """
    # Convert lists to sets
    set1 = set(list1)
    set2 = set(list2)

    # Calculate the intersection
    intersection = set1.intersection(set2)

    # Calculate the similarity ratio, jaccard similarity
    if len(set1.union(set2)) == 0:
        return 0.0
    similarity_ratio = len(intersection) / len(set1.union(set2))

    return similarity_ratio >= threshold

#  Step5: Root Cause Analysis function
def get_rca_params(data_len):
    """
    Dynamically decide topic model parameters based on data size.
    """
    if data_len <= 100:
        return 5, 10
    elif data_len <= 1000:
        return 10, 15
    elif data_len >= 50000:
        return 100, 200
    return 20, 30

def fit_topic_model(docs, embeddings, limit):
    """
    Train BERTopic model on the provided documents and embeddings.
    """
    print(f"[INFO] Training BERTopic model with min_topic_size={limit} ...")
    
    try:
        model = BERTopic(
            verbose=False,
            nr_topics="auto",
            language="multilingual",
            min_topic_size=limit
        )
        topics, probs = model.fit_transform(docs, embeddings=embeddings)
        print(f"[INFO] BERTopic model trained. Topics found: {len(set(topics)) - 1}")
        return model, topics
    except Exception as e:
        print(f"[ERROR] Failed to train BERTopic model: {e}")
        return None, None

def process_topic_level(level_df, model, level, threshold, result, ministry):
    """
    Process each topic and call rca recursively for deep clustering.
    """
    try:
        topics_dict = model.get_topics()
        if not topics_dict:
            print(f"[WARNING] No topics found in model at level {level}")
            return
            
        total_topics = len(topics_dict)
        
        for topic_id in topics_dict.keys():
            if topic_id == -1:  # Skip outlier topic
                continue
                
            try:
                freq = model.get_topic_freq(topic_id)
                if freq < threshold:
                    continue

                topic_terms = model.get_topic(topic_id)
                if not topic_terms:
                    print(f"[WARNING] Empty topic {topic_id} at level {level}. Skipping.")
                    continue

                topic_key = level + str(topic_id + 1)
                topic_words = ','.join([item[0] for item in topic_terms])
                topic_doc_ids = level_df[level_df["topic"] == topic_id]["complaintNumber"].tolist()
                deep_df = generate_df(topic_id, level_df)

                # Update result dictionary
                result["words"][topic_key] = topic_words
                result["count"][topic_key] = freq
                result["doc_ids"][topic_key] = topic_doc_ids

                print(f"[CHECKPOINT] Level {topic_key}: Topic size={freq}, Terms={topic_words}")
                
                # Recursive call only if there's enough data
                if len(deep_df) > 10:
                    rca(topic_key + ".", deep_df, result, ministry)

            except Exception as e:
                print(f"[ERROR] Failed to process topic {topic_id} at level {level} | Error: {str(e)}")
                continue
                
    except Exception as e:
        print(f"[ERROR] Failed to process topic level {level} | Error: {str(e)}")

def rca(level, data, result, ministry):
    """
    Perform recursive topic modeling (Root Cause Analysis) at a given hierarchy level.
    """
    print(f"\n[INFO] Entering RCA level for {ministry}: {level} | Records: {len(data)}")

    if len(data) == 0:
        print("[WARNING] No data to process at this level.")
        return
        
    if len(data) < 5:  # Minimum threshold for meaningful clustering
        print(f"[WARNING] Insufficient data ({len(data)} records) for clustering at level {level}")
        return

    try:
        # Set RCA params dynamically
        limit, threshold = get_rca_params(len(data))

        # Extract docs and embeddings
        docs = data["preprocessed"].tolist()
        
        # Ensure embeddings are properly formatted
        embeddings_list = []
        for emb in data["complaintDetails_vector"].values:
            if isinstance(emb, list):
                embeddings_list.append(np.array(emb))
            else:
                embeddings_list.append(emb)
        
        if not embeddings_list:
            print("[ERROR] No valid embeddings found")
            return
            
        embeddings = np.vstack(embeddings_list)

        # Fit topic model
        model, topics = fit_topic_model(docs, embeddings, limit)
        
        if model is None or topics is None:
            print(f"[ERROR] Topic modeling failed at level {level}")
            return

        # Create topic dataframe
        topics_df = pd.DataFrame({
            'topic': topics,
            'preprocessed': docs,
            'complaintDetails_vector': embeddings_list  # keep as list for merging
        })

        # Merge with original data
        level_df = pd.merge(data.reset_index(drop=True), topics_df, left_index=True, right_index=True)

        # Clean and rename
        level_df = level_df[["complaintNumber", "preprocessed_x", "complaintDetails_vector_x", "topic"]]
        level_df.rename(columns={
            "preprocessed_x": "preprocessed",
            "complaintDetails_vector_x": "complaintDetails_vector"
        }, inplace=True)

        # Process deeper topics
        process_topic_level(level_df, model, level, threshold, result, ministry)

    except Exception as e:
        print(f"[ERROR] RCA failed at level {level}. | Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return

def initialize_rca_result(data, ministry):
    """
    Initialize RCA result structure with root node and call RCA on the data.
    """
    result = {
        "words": {"0": "root"},
        "count": {"0": len(data)},
        "doc_ids": {"0": data["complaintNumber"].tolist()}
    }
    level = "0."

    if len(data) > 0:
        print("[INFO] Starting root cause analysis...")
        rca(level, data, result, ministry)
    else:
        print("[WARNING] No data available for RCA.")

    return result

def execute_rca(start_date, end_date, ministry):
    """
    Main function to execute the RCA process.
    """
    print(f"[INFO] Starting RCA for {ministry} from {start_date} to {end_date}")
    
    data = load_es_data(start_date, end_date, ministry)
    if data.empty:
        print("[WARNING] No data loaded from Elasticsearch.")
        return

    data = preprocess_data(data)
    if data.empty:
        print("[WARNING] No data after preprocessing.")
        return

    result = initialize_rca_result(data, ministry)
    
    try:
        con = connectDB()
        if con is None:
            print("[ERROR] Database connection failed.")
            return
        cursor = con.cursor()
        insert_query = """
            INSERT INTO realrca (ministry, start_date, end_date, rcadata, updated_rcadata)
            VALUES (%s, %s, %s, %s, %s)
        """
        cursor.execute(insert_query, (
            ministry,
            start_date,
            end_date,
            json.dumps(result),
            ''
        ))
        con.commit()
        print("[INFO] RCA result inserted into database.")
        
    except Exception as e:
        print(f"[ERROR] Failed to insert RCA result into database: {e}")
    finally:
        try:
            cursor.close()
            closeDB(con)
            print("[INFO] Database connection closed.")
        except:
            pass

def get_step_days(ministry, start_date, end_date):
    """
    Determine the optimal step size (in days) based on grievance volume for a given ministry and start date.
    """
    step_options = [15, 30, 60, 90, 180]
    query_template = """
        SELECT COUNT(*) FROM tblcomplaints 
        WHERE complaintRegDate >= %s AND complaintRegDate <= %s
    """

    try:
        con = connectDB()
        cursor = con.cursor()

        start_dt = datetime.strptime(start_date, "%Y-%m-%d")

        for days in step_options:
            end_dt = (start_dt + timedelta(days=days)).strftime("%Y-%m-%d")
            cursor.execute(query_template, (start_date, end_dt))
            result = cursor.fetchone()
            count = result[0] if result else 0
            
            if count > 1000:
                cursor.close()
                closeDB(con)
                return days

        # Final fallback: check for all available data
        cursor.execute(query_template, (start_date, end_date))
        result = cursor.fetchone()
        count_all = result[0] if result else 0

        cursor.close()
        closeDB(con)

        if count_all > 100:  # Lower threshold for processing
            return 365

        print("[WARNING] No sufficient data to process.")
        return 0
        
    except Exception as e:
        print(f"[ERROR] Failed to get step days: {e}")
        return 30  # Default fallback

def date_range(start_date, end_date, step_days=1):
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=step_days)

#  Step6: Run Root Cause Analysis
def main():
    try:
        # Example usage
        start = datetime.strptime("2016-08-12", "%Y-%m-%d").date()
        end = datetime.strptime("2025-03-31", "%Y-%m-%d").date()
        ministry = "DOCAF"

        # step_days = get_step_days(ministry, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        step_days = 15
        if step_days == 0:
            print(f"[WARNING] No sufficient data for ministry {ministry}.")
            return

        print(f"start: {start}, end: {end}, step_days: {step_days}")

        # # Check the last checkpoint in the database
        # DB_GET_END_DATE = "SELECT MAX(end_date) FROM realrca"
        # con = connectDB()
        # end_date_in_db_res = pd.read_sql(DB_GET_END_DATE, con)
        # end_date_in_db = end_date_in_db_res.iloc[0, 0]
        # closeDB(con)
        
        # print("end:", end, type(end), "end_date_in_db:", end_date_in_db, type(end_date_in_db))
        
        # if end_date_in_db is not None:
        #     # Convert to date for comparison if it's a datetime
        #     if hasattr(end_date_in_db, 'date'):
        #         end_date_in_db = end_date_in_db.date()
            
        #     if end_date_in_db >= end:
        #         print(f"[INFO] Ministry {ministry} already processed until {end_date_in_db}.")
        #         return
        #     else:
        #         print(f"[INFO] Ministry {ministry} last processed until {end_date_in_db}.")
        #         start = end_date_in_db
        #         print(f"[INFO] Resuming from {start}")

        print(f"[INFO] Processing ministry: {ministry} with step size: {step_days} days")

        for d in date_range(start, end, step_days):

            start_date = d.strftime("%Y-%m-%d")
            end_date = (d + timedelta(days=step_days)).strftime("%Y-%m-%d")
            
            print(f"Processing from {start_date} to {end_date}")
            execute_rca(start_date, end_date, ministry)
            
    except Exception as e:
        print(f"[ERROR] Main execution failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()