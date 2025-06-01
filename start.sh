#!/bin/bash

# Install dependencies
pip install -r requirements.txt

# Update packages
apt update && apt upgrade -y

# Start the app
gunicorn app:app --bind 0.0.0.0:5000
