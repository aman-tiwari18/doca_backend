import sys, json, re
import numpy as np
import pandas as pd
from typing import List


# BERTopic & NLP
from bertopic import BERTopic
from pydantic import BaseModel
from fastapi import APIRouter
from datetime import datetime
from sentence_transformers import SentenceTransformer
from elasticsearch import Elasticsearch
import nltk
from nltk.corpus import stopwords

# Download stopwords list (only once)
nltk.download('stopwords')
# Correct: get stopwords as a set (faster lookup)
stop_words = set(stopwords.words('english'))

# ---------------------------- Configuration & Elasticsearch ----------------------------
with open('../resources/config.json') as config_file:
    config = json.load(config_file)

ES = Elasticsearch([{
    'host': config["ES"]["HOST"],
    'port': config["ES"]["PORT"],
    'scheme': "http"
}], timeout=600)

INDEX_NAME = config["ES"]["INDEX_NAME"]
MODEL_NAME = config["INDIC_BERT_PATH"]
model = SentenceTransformer(MODEL_NAME)


def get_esData(grievance_id):

    try:
        response = ES.get(index=INDEX_NAME, id=grievance_id, _source =["complaintDetails", "complaintDetails_vector"])
        return [response["_source"]["complaintDetails_vector"], response["_source"]["complaintDetails"]]
    except:
        return [None, None]


def remove_stopwords(text):
    if not text:
        return ''
    # Use regex to extract words (removes punctuation as well)
    words = re.findall(r'\b\w+\b', text.lower())
    filtered_words = [word for word in words if word not in stop_words and len(word) > 2]
    return ' '.join(filtered_words)


class MyItem(BaseModel):
    number_of_clusters: int = 26
    grievanceID_list: List[str] = ["NA"]


def dynamicRca( number_of_clusters: int, grievanceID_list: List[str]):
    """
    Extracts topics from the embeddings of documents

    Parameters
    ----------
    number_of_clusters : int
        The number of clusters (topics) to extract. Note that one cluster may be assigned as -1 for outliers.
        Ideally, this should be one less than the total number of desired topics.

    grievanceID_list : list of str
        A list of grievance IDs corresponding to the documents to be used for topic extraction.

    Returns
    -------
    Dictionary containing extracted topic information.
    """


    # load your data here
    data = pd.DataFrame(grievanceID_list, columns=["grievance_id"])
        
    data[['complaintDetails_vector', 'complaintDetails']] = data['grievance_id'].apply(lambda x: pd.Series(get_esData(x)))
    data = data.dropna(subset = ['complaintDetails_vector'])

    doc_id = data["grievance_id"].to_list()
    complaintDetails = data["complaintDetails"].apply(lambda x: remove_stopwords(x)).to_list()
    obtained_embeddings = np.array(data["complaintDetails_vector"].apply(lambda x: np.array(x)).to_list())
    
    if len(doc_id) == 0:
        return {"status": "NoDataFound"}
    
    print("Data Loaded")

    topic_model = BERTopic()
    topics, _ = topic_model.fit_transform(complaintDetails, obtained_embeddings)
    
    # Extract the topics and their frequencies
    topic_info = topic_model.get_topic_info()
    
    # Get the top 25 topics
    top_topics = topic_info.head(number_of_clusters)  # Get 26 as one topic might be -1 (outliers)
    
    topic_dict = {}
    doc_topic_dict = {}

    count = 0
    for doc_index, topic_number in enumerate(topics):
        if topic_number != -1:  # excluding the outlier cluster
            if topic_number in doc_topic_dict:
                doc_topic_dict[topic_number].append(doc_id[doc_index])
            else:
                doc_topic_dict[topic_number] = [doc_id[doc_index]]
  
        count += 1  

    # Print the top 26 topics and their top 10 words
    for topic in top_topics['Topic']:
        if topic != -1:  # excluding the outlier cluster
            # Get top 10 words for the topic
            topic_words = topic_model.get_topic(topic)[:10]
            # Extract only the words (not the scores)
            words = [word for word, _ in topic_words]

            topic_dict[topic] = words
            topic_info = {
                'words': words,
                "count" : len(doc_topic_dict.get(topic, [])),
                'doc_ids': doc_topic_dict.get(topic, []),
            }
            topic_dict[topic] = topic_info
         
    return topic_dict