# Subcategory with Counts API - Implementation Summary

## Overview
A new merged API endpoint that combines GPT subcategory generation with semantic/keyword RCA analysis to provide comprehensive subcategory insights with counts and complaint numbers.

## New API Endpoint

### **POST** `/subcategory_with_counts`

**Location:** `api/router/distributions.py`

**Description:** 
This endpoint merges two existing APIs:
1. `/get_ai_subcategory_gpt` - Generates subcategories using GPT
2. `/get_semantic_rca` - Fetches counts and complaint numbers

### Request Model: `SubcategoryWithCountsRequest`

```json
{
  "input_prompt": "string (required)",
  "value": 1,                    // 1=Semantic, 2=Keyword
  "start_date": "2025-01-01",
  "end_date": "2025-03-30",
  "threshold": 1.5,
  "CityName": "All",
  "stateName": "All",
  "complaintType": "All",
  "complaintMode": "All",
  "companyName": "All",
  "complaintStatus": "All",
  "complaint_numbers": ["NA"],
  "max_retries": 3
}
```

### Response Format

```json
{
  "success": true,
  "total_subcategories": 5,
  "subcategories": [
    {
      "subcategory": "property fires",
      "prompt": "Find grievances related to property fires...",
      "count": 1250,
      "complaintNumbers": ["COM/2025/001", "COM/2025/002", ...]
    },
    {
      "subcategory": "vehicle fires",
      "prompt": "Search for grievances concerning vehicle fires...",
      "count": 856,
      "complaintNumbers": ["COM/2025/100", "COM/2025/101", ...]
    }
  ]
}
```

## How It Works

### Step 1: GPT Subcategory Generation
- The `input_prompt` is sent to GPT-4o-mini
- GPT analyzes the input and identifies distinct subcategories
- For each subcategory, GPT generates a specific search prompt
- Returns JSON with subcategories and their prompts

### Step 2: RCA Analysis for Each Subcategory
- For each generated subcategory:
  - Uses the subcategory's prompt to search complaints
  - Calls either `semanticSearchBasic` (value=1) or `keywordSearchBasic` (value=2)
  - Fetches total counts and complaint numbers
  - Applies all filters (date, location, status, etc.)

### Step 3: Results Aggregation
- Combines all results into a unified response
- Sorts subcategories by count (descending)
- Returns comprehensive data with prompts and complaint numbers

## Repository Function

**Function:** `getSubcategoryWithCounts()`  
**Location:** `api/repository/distributions.py`

### Dependencies Used:
- `repository.semantic_search.semanticSearchBasic`
- `repository.keyword_search.keywordSearchBasic`
- `OpenAI GPT-4o-mini API`

### Key Features:
- ✅ Automatic retry mechanism for GPT API calls (configurable)
- ✅ JSON response cleaning and validation
- ✅ Error handling for individual subcategory failures
- ✅ Supports both semantic and keyword search
- ✅ Respects all filter parameters (dates, location, status, etc.)

## Helper Functions Added

### `call_gpt_api(prompt: str) -> str`
- Calls OpenAI GPT-4o-mini with the provided prompt
- Returns the generated content or error label

### `clean_json_response(response: str) -> str`
- Removes markdown code blocks
- Extracts valid JSON from GPT responses
- Handles various response formats

## Example Usage

```bash
curl -X POST "http://localhost:8000/subcategory_with_counts" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "input_prompt": "Analyze fire-related complaints including property fires, vehicle fires, and electrical fires with their keywords and examples",
    "value": 1,
    "start_date": "2025-01-01",
    "end_date": "2025-03-30",
    "threshold": 1.5,
    "stateName": "All"
  }'
```

## Files Modified

1. **`api/router/distributions.py`**
   - Added `SubcategoryWithCountsRequest` model
   - Added `/subcategory_with_counts` endpoint
   - Imported `getSubcategoryWithCounts` from repository

2. **`api/repository/distributions.py`**
   - Added `getSubcategoryWithCounts()` function
   - Added `call_gpt_api()` helper
   - Added `clean_json_response()` helper
   - Imported OpenAI and time modules

## Configuration Required

Ensure `OPENAI_API_KEY` is set in `resources/config.json`:

```json
{
  "OPENAI_API_KEY": "sk-..."
}
```

## Error Handling

- **GPT API failures:** Retries up to `max_retries` times
- **Invalid JSON from GPT:** Automatic cleaning and fallback logic
- **Individual subcategory errors:** Continues processing other subcategories
- **Search failures:** Returns subcategory with count=0 and error message

## Performance Considerations

- GPT API calls may take 2-5 seconds depending on prompt complexity
- Each subcategory RCA search adds ~1-2 seconds
- Total time = GPT time + (number_of_subcategories × RCA_time)
- Results are sorted by count for better UX

## Testing Recommendations

1. Test with simple input prompts first
2. Verify GPT generates valid subcategories
3. Check that all filters are applied correctly
4. Validate complaint numbers returned
5. Test error scenarios (invalid dates, missing config, etc.)

## Future Enhancements

- [ ] Add caching for repeated subcategory prompts
- [ ] Implement parallel RCA calls for faster processing
- [ ] Add pagination for large subcategory lists
- [ ] Support custom GPT models via parameter
- [ ] Add metrics tracking (response time, success rate)

---

**Implementation Date:** January 28, 2026  
**Status:** ✅ Complete and Running
