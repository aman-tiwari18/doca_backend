#!/bin/bash

# Complaint Fetcher Cron Wrapper Script
# This script runs the Python complaint fetcher with proper environment setup

# Change to the API directory
cd /home/aman/Downloads/consumer_affairs_dashboard-aws/api

# Run the Python script using the virtual environment
../venv/bin/python cron/fetch_complaints.py

# Exit with the Python script's exit code
exit $?
