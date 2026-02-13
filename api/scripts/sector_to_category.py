import json
import os

# File paths
base_dir = os.path.dirname(os.path.abspath(__file__))
sector_file = os.path.join(base_dir, "../../resources/sectors_mapping.json")
category_file = os.path.join(base_dir, "../../resources/category_mapping.json")
output_file = os.path.join(base_dir, "../../resources/sector_category_map.json")

with open(sector_file, "r", encoding="utf-8") as f:
    sectors = json.load(f)

with open(category_file, "r", encoding="utf-8") as f:
    categories = json.load(f)

sector_map = {
    sector["sectorCode"]: sector["sectorName"]
    for sector in sectors
    if sector.get("status") == "1"
}

result = {}

for cat in categories:

    # if cat.get("status") != "1":
    #     continue

    sector_code = cat.get("sectorCode")
    category_name = cat.get("categoryName")

    if sector_code in sector_map:

        sector_name = sector_map[sector_code]

        if sector_name not in result:
            result[sector_name] = []

        result[sector_name].append(category_name)

with open(output_file, "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=4)

print("Saved to:", output_file)
