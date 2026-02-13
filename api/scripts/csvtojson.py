import csv
import json

csv_file_path = "category.csv"
json_file_path = "category.json"


def csv_to_json(csv_file_path, json_file_path):
    """
    Convert CSV file to JSON file where each row becomes a JSON object
    with columns as fields.
    """

    data = []

    with open(csv_file_path, mode="r", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)  # Uses first row as keys

        for row in reader:
            data.append(row)

    with open(json_file_path, mode="w", encoding="utf-8") as json_file:
        json.dump(data, json_file, indent=4, ensure_ascii=False)

    print(f"JSON file created: {json_file_path}")
