from pathlib import Path
import sys
import re
import numpy as np
import pandas as pd
import requests
import re
import json
from typing import List, Annotated
from nltk.corpus import stopwords
from datetime import datetime, timedelta

# BERTopic & NLP
from bertopic import BERTopic
from pydantic import BaseModel

# ---------------------------- Path Management ----------------------------
# Move up 3 levels to reach `/xyz/resources`
resources_dir = Path(__file__).resolve().parents[2] / "resources"
sys.path.append(str(resources_dir))

# ---------------------------- Import Internal Modules ----------------------------
from utility import connectDB, closeDB
from bertopic.dimensionality import BaseDimensionalityReduction


# similarity funtion to check if two list are more than or equal to 80% similar 
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
    similarity_ratio = len(intersection) / len(set1.union(set2))

    return similarity_ratio >= threshold


def get_parent_level(key):
    return ".".join(key.split(".")[:-1])

def get_next_available_index(existing_keys, parent_level):
    children = [k for k in existing_keys if k.startswith(parent_level + ".")]
    indices = []
    for k in children:
        match = re.match(rf"^{re.escape(parent_level)}\.(\d+)$", k)
        if match:
            indices.append(int(match.group(1)))
    return max(indices, default=0) + 1


def merge_rca_results_with_levels(first_half_data, second_half_data, similarity_threshold=0.5):
    if not first_half_data:
        return second_half_data
    if not second_half_data:
        return first_half_data
    
    merged_data = {
        "words": dict(first_half_data["words"]),
        "count": dict(first_half_data["count"]),
        "doc_ids": dict((k, list(set(v))) for k, v in first_half_data["doc_ids"].items())
    }

    for key2, topic2 in second_half_data["words"].items():
        parent_level = get_parent_level(key2)
        topic_words2 = set(topic2.split(','))
        found = False

        # Try to find a matching topic in the same level
        for key1, topic1 in merged_data["words"].items():
            if get_parent_level(key1) == parent_level:
                topic_words1 = set(topic1.split(','))
                if is_similar(topic_words1, topic_words2, 0.6):
                    # Merge topics
                    merged_data["words"][key1] = ",".join(sorted(topic_words1.union(topic_words2)))
                    merged_data["count"][key1] += second_half_data["count"][key2]
                    merged_data["doc_ids"][key1] = list(set(merged_data["doc_ids"][key1] + second_half_data["doc_ids"][key2]))
                    found = True
                    break

        if not found:
            # Generate new key under the same parent
            next_index = get_next_available_index(merged_data["words"].keys(), parent_level)
            new_key = f"{parent_level}.{next_index}"
            merged_data["words"][new_key] = topic2
            merged_data["count"][new_key] = second_half_data["count"][key2]
            merged_data["doc_ids"][new_key] = second_half_data["doc_ids"][key2]

    return merged_data

def get_all_date_ranges(ministry):
    """
    Fetch all date ranges from the database.
    """
    get_date_ranges = f"SELECT start_date, end_date FROM realrca"
    date_ranges = []

    con = connectDB()
    if con is None:
        print("[ERROR] Database connection failed.")
        return []
    
    cursor = con.cursor()
    cursor.execute(get_date_ranges)
    for row in cursor.fetchall():
        date_ranges.append((row[0], row[1]))
    
    cursor.close()
    closeDB(con)
    
    return [(str(start_date), str(end_date)) for start_date, end_date in date_ranges]


def parsedate(d):
    return datetime.strptime(d, "%Y-%m-%d")


def find_closest_start_end(input_start, input_end, date_ranges):
    input_start = datetime.strptime(input_start, "%Y-%m-%d")
    input_end = datetime.strptime(input_end, "%Y-%m-%d")

    closest_start = None
    closest_end = None
    min_start_diff = float('inf')
    min_end_diff = float('inf')

    for start_str, end_str in date_ranges:
        start = datetime.strptime(start_str, "%Y-%m-%d")
        end = datetime.strptime(end_str, "%Y-%m-%d")
        print(f"Checking range: {start_str} to {end_str}")
        start_diff = abs((start - input_start).days)
        if start_diff < min_start_diff:
            min_start_diff = start_diff
            closest_start = start_str
           
        print(f"Start diff: {start_diff}, Closest start: {closest_start}")
        end_diff = abs((end - input_end).days)
        if end_diff < min_end_diff:
            min_end_diff = end_diff
            closest_end = end_str

    # if output is one 
    if closest_start == closest_end:
        for start_str, end_str in date_ranges:
            if closest_start == start_str:
                closest_end = end_str
                break

    return closest_start, closest_end

# def get_closest_date_range_data(start_date, end_date, ministry):
#     """
#     Get the closest date range data from the RCA data.
#     """
    
#     date_ranges = get_all_date_ranges(ministry)
#     closest_start, closest_end = find_closest_start_end(start_date, end_date, date_ranges)
#     print(f"Closest date range found: {closest_start} to {closest_end}")
#     get_rca_data_within_date_range = f"SELECT rcadata FROM realrca WHERE start_date>='{closest_start}' AND end_date<='{closest_end}'"
    
#     con = connectDB()
#     if con is None:
#         print("[ERROR] Database connection failed.")
#         return []
    
#     rca_data = []
#     cursor = con.cursor()
#     cursor.execute(get_rca_data_within_date_range)
#     for row in cursor.fetchall():
#         data = json.loads(row[0])
#         rca_data.append(data)
    
#     cursor.close()
#     closeDB(con)
#     return rca_data
    
import json

def get_closest_date_range_data(start_date, end_date, ministry):
    """
    Get the closest date range data from the RCA data.
    """

    date_ranges = get_all_date_ranges(ministry)
    closest_start, closest_end = find_closest_start_end(
        start_date, end_date, date_ranges
    )

    print(f"Closest date range found: {closest_start} to {closest_end}")

    # ✅ Parameterized query
    query = """
        SELECT rcadata
        FROM realrca
        WHERE start_date >= %s
          AND end_date   <= %s
    """

    con = connectDB()
    if con is None:
        print("[ERROR] Database connection failed.")
        return []

    rca_data = []

    try:
        cursor = con.cursor()
        cursor.execute(query, (closest_start, closest_end))

        for (row_data,) in cursor.fetchall():
            rca_data.append(json.loads(row_data))

    except Exception as e:
        print(f"[ERROR] Failed to fetch RCA data: {e}")

    finally:
        cursor.close()
        closeDB(con)

    return rca_data


class CachedRcaRequest(BaseModel):
    """
    Request model for Real-time RCA.
    """
    startDate: str
    endDate: str
    ministry: str
    state: str = 'All'
    district: str = 'All'
    number_of_clusters: int = 11


def cachedrca(item: CachedRcaRequest):
    '''
    to get the topics from the embeddings of the documents of the given ministry

    Parameters:
    ------------
    1) ministry : str,   The ministry for which the topics are to be extracted   {CBODT, DOAAC, DPOST, DORLD, MORLY, MOLBR}
    2) startDate : str,    The start date for the documents to be considered
    3) endDate : str,      The end date for the documents to be considered
    4) number_of_clusters : int,   The number of topics to be extracted, topic might be -1 (outliers) {One less than the number of topics to be extracted}
    
    '''
    
    rca_data = get_closest_date_range_data(item.startDate, item.endDate, item.ministry)
    if not rca_data:
        return {"status": "NoDataFound"}
    
    merge_data = {}
    for i in range(len(rca_data)):
        updated_merge_data = merge_rca_results_with_levels(rca_data[i], merge_data)
        merge_data = updated_merge_data
    
    return merge_data
    

