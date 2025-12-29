import mysql.connector as sql
import json, os, sqlalchemy
from elasticsearch import Elasticsearch
from sentence_transformers import SentenceTransformer
import torch

def load_config(filepath=None):
    """Load JSON configuration from a file."""
    if filepath is None:
        filepath = os.path.join(os.path.dirname(__file__), "config.json")
        
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Config file not found: {filepath}")
    
    with open(filepath, "r") as file:
        return json.load(file)


def load_es_query(filepath=None):
    """Load JSON configuration from a file."""
    if filepath is None:
        filepath = os.path.join(os.path.dirname(__file__), "es_query.json")

    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Config file not found: {filepath}")
    
    with open(filepath, "r") as file:
        return json.load(file)


# Example usage
try:
    config = load_config()
except Exception as e:
    print(f"Error: {e}")



# connect to database
def connectDB():
    connection = sql.connect(host=config["DB"]["HOST"], database=config["DB"]["NAME"], user=config["DB"]["USER"], password=config["DB"]["PWD"])
    return connection



# close database
def closeDB(connection):
    connection.close()


# def getES():
#     # Connect to Elasticsearch
#     # Elasticsearch([{'host': 'localhost', 'port': 9200,'timeout':12000}],sniff_on_start=True,sniffer_timeout=60,sniff_on_connection_fail=True)
#     return Elasticsearch([{'host': config["ES"]["HOST"], 'port': config["ES"]["PORT"]}])


def getES():
    return Elasticsearch(
        "https://localhost:9200",
        basic_auth=(
            config["ES"]["USERNAME"],
            config["ES"]["PASSWORD"]
        ),
        verify_certs=False,
        request_timeout=30
    )

#Database Connection
def connectDB_alchemy(engine=False):
    DB_STRING = f"mysql+mysqlconnector://{config['DB']['USER']}:{config['DB']['PWD']}@{config['DB']['HOST']}/{config['DB']['NAME']}"
    engine = sqlalchemy.create_engine(DB_STRING)
    if engine:
        return engine
    connection = engine.connect()
    return connection


_embed_model = None

def getEmbed():
    global _embed_model
    if _embed_model is not None:
        return _embed_model

    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(f"Using device: {device}")
    print(torch.cuda.is_available())  # Should print: True
    print(torch.cuda.device_count())  # Should print: Number of GPUs (e.g., 1)
    # print(torch.cuda.get_device_name(0))  # Should print your GPU name

    _embed_model = SentenceTransformer(config['INDIC_BERT_PATH'], device=device) #Load Model
    return _embed_model
