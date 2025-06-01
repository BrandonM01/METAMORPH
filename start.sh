#!/bin/bash

# Install Python packages (only if not already installed)
pip install --no-cache-dir \
flask flask_sqlalchemy Flask-Migrate Flask-Login \
python-dotenv PyDrive Pillow ffmpeg-python stripe \
google-auth-oauthlib google-api-python-client gunicorn \
Werkzeug opencv-python numpy

# Optional: install ffmpeg system-wide
apt update && apt install -y ffmpeg

# Run Flask app with Gunicorn on port 80
gunicorn -w 1 -b 0.0.0.0:80 app:app
