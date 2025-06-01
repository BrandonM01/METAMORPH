#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

# Ensure ffmpeg is installed (for environments where it isn't preinstalled)
if ! command -v ffmpeg &> /dev/null; then
    apt-get update && apt-get install -y ffmpeg
fi

# Upgrade pip and install dependencies
pip install --upgrade pip
pip install --no-cache-dir -r requirements.txt

# Start the app with Gunicorn on port 5000
gunicorn app:app --bind 0.0.0.0:5000
