# Cron Job Setup Guide for Complaint Fetcher

## Overview
This script fetches complaints from the Consumer Helpline API and stores them in the database.
It should be run periodically (e.g., every hour or daily) using cron.

## Prerequisites
- Python virtual environment set up at: `/home/aman/Downloads/consumer_affairs_dashboard-aws/venv`
- Database configured in `resources/config.json`
- API credentials configured in the script

## Setting Up the Cron Job

### Step 1: Test the Script Manually
Before setting up cron, test the script to ensure it works:

```bash
cd /home/aman/Downloads/consumer_affairs_dashboard-aws/api
../venv/bin/python cron/fetch_complaints.py
```

Check the log file for any errors:
```bash
tail -f cron_fetch.log
```

### Step 2: Create a Wrapper Script (Recommended)
Create a shell script to run the Python script with proper environment:

```bash
nano /home/aman/Downloads/consumer_affairs_dashboard-aws/api/cron/run_fetch_complaints.sh
```

Add the following content:
```bash
#!/bin/bash

# Change to the API directory
cd /home/aman/Downloads/consumer_affairs_dashboard-aws/api

# Run the Python script using the virtual environment
../venv/bin/python cron/fetch_complaints.py

# Exit with the Python script's exit code
exit $?
```

Make it executable:
```bash
chmod +x /home/aman/Downloads/consumer_affairs_dashboard-aws/api/cron/run_fetch_complaints.sh
```

### Step 3: Open Crontab
```bash
crontab -e
```

### Step 4: Add Cron Job Entry

Choose one of the following schedules:

#### Option 1: Run Every Hour
```cron
0 * * * * /home/aman/Downloads/consumer_affairs_dashboard-aws/api/cron/run_fetch_complaints.sh >> /home/aman/Downloads/consumer_affairs_dashboard-aws/api/cron_cron.log 2>&1
```

#### Option 2: Run Every 6 Hours
```cron
0 */6 * * * /home/aman/Downloads/consumer_affairs_dashboard-aws/api/cron/run_fetch_complaints.sh >> /home/aman/Downloads/consumer_affairs_dashboard-aws/api/cron_cron.log 2>&1
```

#### Option 3: Run Daily at 2 AM
```cron
0 2 * * * /home/aman/Downloads/consumer_affairs_dashboard-aws/api/cron/run_fetch_complaints.sh >> /home/aman/Downloads/consumer_affairs_dashboard-aws/api/cron_cron.log 2>&1
```

#### Option 4: Run Twice Daily (2 AM and 2 PM)
```cron
0 2,14 * * * /home/aman/Downloads/consumer_affairs_dashboard-aws/api/cron/run_fetch_complaints.sh >> /home/aman/Downloads/consumer_affairs_dashboard-aws/api/cron_cron.log 2>&1
```

### Step 5: Save and Exit
- If using `nano`: Press `Ctrl+X`, then `Y`, then `Enter`
- If using `vi`: Press `Esc`, type `:wq`, then `Enter`

### Step 6: Verify Cron Job is Scheduled
```bash
crontab -l
```

## Monitoring

### Check Application Logs
```bash
tail -f /home/aman/Downloads/consumer_affairs_dashboard-aws/api/cron_fetch.log
```

### Check Cron Execution Logs
```bash
tail -f /home/aman/Downloads/consumer_affairs_dashboard-aws/api/cron_cron.log
```

### Check System Cron Logs
```bash
grep CRON /var/log/syslog | tail -20
```

## Troubleshooting

### Cron Job Not Running
1. Check if cron service is running:
   ```bash
   sudo systemctl status cron
   ```

2. Verify the script has execute permissions:
   ```bash
   ls -l /home/aman/Downloads/consumer_affairs_dashboard-aws/api/cron/run_fetch_complaints.sh
   ```

3. Test the wrapper script manually:
   ```bash
   /home/aman/Downloads/consumer_affairs_dashboard-aws/api/cron/run_fetch_complaints.sh
   ```

### Script Errors
1. Check the application log:
   ```bash
   tail -100 /home/aman/Downloads/consumer_affairs_dashboard-aws/api/cron_fetch.log
   ```

2. Verify database connection in `resources/config.json`

3. Verify API credentials in the script

### Database Issues
1. Check if MySQL is running:
   ```bash
   sudo systemctl status mysql
   ```

2. Test database connection:
   ```bash
   mysql -u [username] -p [database_name]
   ```

## Stopping the Cron Job

To temporarily disable the cron job:
```bash
crontab -e
```
Then comment out the line by adding `#` at the beginning:
```cron
# 0 * * * * /home/aman/Downloads/consumer_affairs_dashboard-aws/api/cron/run_fetch_complaints.sh >> /home/aman/Downloads/consumer_affairs_dashboard-aws/api/cron_cron.log 2>&1
```

To completely remove the cron job:
```bash
crontab -e
```
Then delete the entire line and save.

## Performance Considerations

- The script fetches up to 1000 complaints per run
- Each complaint requires an additional API call for details (with 0.1s delay)
- Expect approximately 2-3 minutes per 1000 complaints
- Adjust the cron schedule based on the expected volume of new complaints

## Recommended Schedule

Based on typical usage:
- **High Volume (>1000 complaints/day)**: Run every 2-4 hours
- **Medium Volume (100-1000 complaints/day)**: Run every 6-12 hours
- **Low Volume (<100 complaints/day)**: Run once daily

## Notes

- The script automatically handles incremental updates (only fetches new complaints)
- On first run, it will backfill from 2025-01-01
- Subsequent runs fetch only complaints since the last run
- The script uses `ON DUPLICATE KEY UPDATE` to handle duplicate complaints gracefully
