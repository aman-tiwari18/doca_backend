from repository.semantic_search import semanticSearchCount, semanticSearch, semanticSearchBasic
from repository.keyword_search import keywordSearchCount, keywordSearch
import json
from pathlib import Path
import sys

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

CATEGORIES_PATH = config["CATEGORIES_PATH"]
CATEGORIES_SUBCATEGORIES_WITH_PROMPT_PATH = config["CATEGORIES_SUBCATEGORIES_WITH_PROMPT_PATH"]

with open(CATEGORIES_PATH, 'r') as f:
    categories = json.load(f)

with open(CATEGORIES_SUBCATEGORIES_WITH_PROMPT_PATH, 'r') as f:
    categories_with_prompt = json.load(f)

categories = categories["ConsumerGrievanceCategories"]

categories_with_prompt = categories_with_prompt["ConsumerGrievancePrompts"]

category_dict = {
    "words": {},
    "count": {},
    "doc_ids": {}
}

category_dict_with_prompt = {
    "words": {},
    "count": {},
    "doc_ids": {}
}

# def get_category_data(start_date, end_date, threshold, CityName="All", stateName="All", complaintType="All", complaintMode="All", companyName="All", complaintStatus="All"):
    
#     # # Load existing category_dict if available
#     # with open("category_dict.json", "r") as infile:
#     #     myjsonfile = json.load(infile)
    
#     # # if category dict exists, load and return it
#     # if myjsonfile and myjsonfile.get("words"):
#     #     return myjsonfile
    
#     count = 1
#     for category in categories:
#         # print("Processing category:", category)
#         myindex = "0." + str(count)
#         category_name = category["category"]
#         category_dict["words"][myindex] = category_name
        
#         result = semanticSearchBasic(
#             es_client,
#             category_name,
#             start_date,
#             end_date,
#             embed_model,
#             INDEX_NAME,
#             CityName=CityName,
#             stateName=stateName,
#             complaintType=complaintType,
#             complaintMode=complaintMode,
#             companyName=companyName,
#             complaintStatus=complaintStatus,
#             threshold=threshold
#         )
#         print("Result for category:", category_name, "is", result["total_counts"])

#         category_dict["count"][myindex] = result["total_counts"]
#         category_dict["doc_ids"][myindex] = result["complaintNumbers"]
        
#         subcount = 1
#         for subcategory in category.get("subcategories", []):
#             subcategory_name = subcategory
#             subcategory_key = f"{myindex}.{str(subcount)}"
#             category_dict["words"][subcategory_key] = subcategory_name

#             # get count and doc_ids for subcategory
#             result = semanticSearchBasic(
#                 es_client,
#                 subcategory_name,
#                 start_date,
#                 end_date,
#                 embed_model,
#                 INDEX_NAME,
#                 CityName=CityName,
#                 stateName=stateName,
#                 complaintType=complaintType,
#                 complaintMode=complaintMode,
#                 companyName=companyName,
#                 complaintStatus=complaintStatus,
#                 threshold=1.3
#             )
#             category_dict["count"][subcategory_key] = result["total_counts"]
#             category_dict["doc_ids"][subcategory_key] = result["complaintNumbers"]
#             subcount += 1
#         count += 1
#         with open("category_dict.json", "w") as outfile:
#             json.dump(category_dict, outfile)
#     return category_dict


def get_category_data_with_prompt(start_date, end_date, threshold, CityName="All", stateName="All", complaintType="All", complaintMode="All", companyName="All", complaintStatus="All"):
    """
    Function to get category data using prompts for semantic search
    """
    count = 1
    for category in categories_with_prompt:
        myindex = "0." + str(count)
        category_name = category["category"]
        categoryPrompt = category.get("categoryPrompt", "")
        
        # Use only the prompt for search if available
        search_text = categoryPrompt if categoryPrompt else category_name
        # Store both category name and prompt for reference
        category_dict_with_prompt["words"][myindex] = {
            "category": category_name,
            "prompt": categoryPrompt
        }
        
        result = semanticSearchBasic(
            es_client,
            search_text,  # Using prompt for search
            start_date,
            end_date,
            embed_model,
            INDEX_NAME,
            CityName=CityName,
            stateName=stateName,
            complaintType=complaintType,
            complaintMode=complaintMode,
            companyName=companyName,
            complaintStatus=complaintStatus,
            threshold=threshold
        )
        print(f"Result for category '{category_name}' using prompt: {result['total_counts']}")

        category_dict_with_prompt["count"][myindex] = result["total_counts"]
        category_dict_with_prompt["doc_ids"][myindex] = result["complaintNumbers"]
        
        subcount = 1
        subcategory_prompts = category.get("subcategoryPrompts", {})
        for subcategory_name, sub_prompt in subcategory_prompts.items():
            subcategory_key = f"{myindex}.{str(subcount)}"
            
            # Use only the prompt for search
            sub_search_text = sub_prompt
            # Store both subcategory name and prompt for reference
            category_dict_with_prompt["words"][subcategory_key] = {
                "subcategory": subcategory_name,
                "prompt": sub_prompt
            }

            result = semanticSearchBasic(
                es_client,
                sub_search_text,  # Using prompt for search
                start_date,
                end_date,
                embed_model,
                INDEX_NAME,
                CityName=CityName,
                stateName=stateName,
                complaintType=complaintType,
                complaintMode=complaintMode,
                companyName=companyName,
                complaintStatus=complaintStatus,
                threshold=1.3
            )
            category_dict_with_prompt["count"][subcategory_key] = result["total_counts"]
            category_dict_with_prompt["doc_ids"][subcategory_key] = result["complaintNumbers"]
            subcount += 1
            
        count += 1
        
    # Save results to file
    with open("category_dict_with_prompt.json", "w") as outfile:
        json.dump(category_dict_with_prompt, outfile)
    
    return category_dict_with_prompt
