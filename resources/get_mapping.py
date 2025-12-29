import pandas as pd

from utility import getES, load_config, getEmbed, connectDB_alchemy

connection = connectDB_alchemy()
if connection is None:
    print("Database connection failed.")
else:
    print("Database connection successful.")

# query = "select stCode as stateCode, stateName from mststate"

# df = pd.read_sql(query, connnection)

# #  sort the dataframe by stateCode
# df = df.sort_values(by='stateCode')


# # convert it into json format with stateCode as key and stateName as value
# state_dict = df.set_index('stateCode').T.to_dict('list')

# # convert key to a string
# state_dict = {int(k): v[0] for k, v in state_dict.items()}

# # save the dictionary into a json file
# import json
# with open('state_dict.json', 'w') as f:
#     json.dump(state_dict, f)

# print("State dictionary saved to state_dict.json")

# query = "select CityCode, CityName from mstcity"
# df = pd.read_sql(query, connnection)

# df = df.sort_values(by='CityCode')

# # convert it into json format with CityCode as key and CityName as value

# city_dict = df.set_index('CityCode').T.to_dict('list')

# city_dict = {int(k): v[0] for k, v in city_dict.items()}

# with open('city_dict.json', 'w') as f:
#     json.dump(city_dict, f)

# print("City dictionary saved to city_dict.json")

import json
# create a function that ask key and value and generate the dict and save it in this folder
def mapping_generator(key, value):
    
    query = f"select {key}, {value} from tblcompany"
    df = pd.read_sql(query, connection)
    df = df.sort_values(by=key)
    mapping_dict = df.set_index(key).T.to_dict('list')
    mapping_dict = {str(k): v[0] for k, v in mapping_dict.items()}
    with open(f'{key}_to_{value}_dict.json', 'w') as f:
        json.dump(mapping_dict, f)
    print(f"Mapping dictionary saved to {key}_to_{value}_dict.json")


# main function
if __name__ == "__main__":
    while True:
        key = input("Enter the key column name (or 'exit' to quit): ")
        if key.lower() == 'exit':
            break
        value = input("Enter the value column name: ")
        mapping_generator(key, value)
