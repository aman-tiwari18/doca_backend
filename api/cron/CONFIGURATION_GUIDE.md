# Complaint Fetcher - Configuration Guide

## Overview
The complaint fetcher script has been updated to handle API rate limiting and provides two modes of operation:
- **BASIC MODE** (default): Fast, inserts only basic complaint data from the history API
- **DETAILED MODE**: Slower, fetches full details for each complaint from the details API

## Current Issue: API Rate Limiting

The Consumer Helpline API has strict rate limits:
- **429 Too Many Requests**: Triggered when making too many requests too quickly
- **401 Unauthorized**: Can occur after rate limiting or authentication issues

## Configuration Options

Edit `/home/aman/Downloads/consumer_affairs_dashboard-aws/api/cron/fetch_complaints.py` and modify these settings:

```python
# Rate limiting configuration
FETCH_DETAILS = False  # Set to True to fetch detailed info (slower but more complete)
DELAY_BETWEEN_REQUESTS = 2.0  # Seconds between API calls
MAX_RETRIES_ON_RATE_LIMIT = 3  # Number of retries when rate limited
RATE_LIMIT_BACKOFF = 30  # Initial wait time (seconds) when rate limited
```

### FETCH_DETAILS

**Default: `False` (BASIC MODE)**

- **`False` (BASIC MODE - RECOMMENDED)**:
  - ✅ Fast execution (~5-10 seconds for 1000 complaints)
  - ✅ No rate limiting issues
  - ✅ Inserts basic complaint data:
    - Complaint number, sector, category
    - Status, registration date
    - State code (mapped from state name)
  - ❌ Missing detailed information (user emails, comments, etc.)

- **`True` (DETAILED MODE)**:
  - ✅ Complete data with all fields
  - ✅ Includes user details, comments, company info
  - ❌ Very slow (~30-60 minutes for 1000 complaints)
  - ❌ High risk of rate limiting (429 errors)
  - ❌ May trigger authentication errors (401)

### DELAY_BETWEEN_REQUESTS

**Default: `2.0` seconds**

Time to wait between each API call when fetching details.

- **Recommended values**:
  - `1.0` - Aggressive (may still hit rate limits)
  - `2.0` - Balanced (current default)
  - `5.0` - Conservative (safest, but very slow)

### MAX_RETRIES_ON_RATE_LIMIT

**Default: `3`**

Number of times to retry when receiving a 429 error.

### RATE_LIMIT_BACKOFF

**Default: `30` seconds**

Initial wait time when rate limited. Uses exponential backoff:
- 1st retry: 30 seconds
- 2nd retry: 60 seconds
- 3rd retry: 120 seconds

## Recommended Configurations

### For Production (Recommended)

```python
FETCH_DETAILS = False  # Basic mode
DELAY_BETWEEN_REQUESTS = 2.0
```

**Run frequency**: Every 1-6 hours via cron

**Pros**:
- Fast and reliable
- No rate limiting issues
- Gets all new complaints quickly

**Cons**:
- Missing detailed information

### For One-Time Detailed Fetch (Use Carefully)

```python
FETCH_DETAILS = True  # Detailed mode
DELAY_BETWEEN_REQUESTS = 5.0  # Very conservative
MAX_RETRIES_ON_RATE_LIMIT = 5
RATE_LIMIT_BACKOFF = 60
```

**Run frequency**: Manually, or once daily during off-peak hours (e.g., 3 AM)

**Pros**:
- Complete data

**Cons**:
- Very slow (1-2 hours for 1000 complaints)
- May still hit rate limits
- Not suitable for frequent cron jobs

### Hybrid Approach (Best of Both Worlds)

**Step 1**: Use BASIC mode for regular updates
```python
FETCH_DETAILS = False
```
Run every 1-6 hours via cron

**Step 2**: Create a separate script for batch detail updates
- Run once daily or weekly
- Process complaints in smaller batches (e.g., 100 at a time)
- Use longer delays (5-10 seconds)

## Data Captured in Each Mode

### BASIC MODE (FETCH_DETAILS = False)

Fields inserted:
- `complainNumber`
- `userId` (default: 0)
- `sectorCode`
- `categoryCode`
- `complaintStatus`
- `complaintRegDate`
- `stateCode` (mapped from stateName)

### DETAILED MODE (FETCH_DETAILS = True)

Additional fields:
- `userEmailId`
- `userContactNumber`
- `complaintDetails`
- `converganceCompanyName`
- `nonConverganceCompanyName`
- `complaintMode`
- `productValue`
- `agentRemark`
- `userComment`
- `userCommentDate`
- `govtDepartment`
- `docketType`
- `grievanceClassification`
- `grievanceExpectation`
- `companyRegisteredGrievance`
- `grievanceAmount`
- `companyGrievanceNo`
- `gstInfo`

## Monitoring

### Check Current Mode
```bash
tail -20 /home/aman/Downloads/consumer_affairs_dashboard-aws/api/cron_fetch.log | grep "Configuration:"
```

### Monitor for Rate Limiting
```bash
tail -f /home/aman/Downloads/consumer_affairs_dashboard-aws/api/cron_fetch.log | grep -E "(429|401|Rate limited)"
```

### Check Processing Speed
```bash
tail -f /home/aman/Downloads/consumer_affairs_dashboard-aws/api/cron_fetch.log | grep "Processed"
```

## Troubleshooting

### Getting 429 Errors
1. Increase `DELAY_BETWEEN_REQUESTS` to 5.0 or higher
2. Reduce batch size by limiting PER_PAGE
3. Switch to BASIC mode (`FETCH_DETAILS = False`)

### Getting 401 Errors
1. Check API credentials (USERNAME, PASSWORD)
2. May occur after prolonged rate limiting
3. Wait 10-15 minutes before retrying

### Script Running Too Slow
1. Switch to BASIC mode (`FETCH_DETAILS = False`)
2. Reduce `DELAY_BETWEEN_REQUESTS` (carefully)
3. Process details separately in batches

## Example Cron Schedules

### BASIC MODE (Recommended)
```cron
# Every 2 hours
0 */2 * * * /home/aman/Downloads/consumer_affairs_dashboard-aws/api/cron/run_fetch_complaints.sh >> /home/aman/Downloads/consumer_affairs_dashboard-aws/api/cron_cron.log 2>&1
```

### DETAILED MODE (Use Sparingly)
```cron
# Once daily at 3 AM
0 3 * * * /home/aman/Downloads/consumer_affairs_dashboard-aws/api/cron/run_fetch_complaints.sh >> /home/aman/Downloads/consumer_affairs_dashboard-aws/api/cron_cron.log 2>&1
```

## Summary

**For most use cases, use BASIC MODE** (`FETCH_DETAILS = False`):
- Fast and reliable
- No rate limiting issues
- Captures essential complaint data
- Can run frequently via cron

Only use DETAILED MODE for special cases where you need complete information and can tolerate slow execution times.
