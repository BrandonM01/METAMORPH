import os
from flask import session, redirect, url_for, request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# SCOPES: what permissions we request
SCOPES = ['https://www.googleapis.com/auth/drive.file']

def create_flow():
    client_config = {
        "web": {
            "client_id":     os.getenv("GOOGLE_CLIENT_ID"),
            "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
            "auth_uri":      "https://accounts.google.com/o/oauth2/auth",
            "token_uri":     "https://oauth2.googleapis.com/token",
            "redirect_uris": [os.getenv("GOOGLE_OAUTH_REDIRECT_URI")],
        }
    }
    return Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=os.getenv("GOOGLE_OAUTH_REDIRECT_URI")
    )

def start_auth():
    flow = create_flow()
    auth_url, _ = flow.authorization_url(
        prompt='consent',
        access_type='offline',
        include_granted_scopes='true'
    )
    return redirect(auth_url)

def handle_callback():
    flow = create_flow()
    flow.fetch_token(authorization_response=request.url)
    creds = flow.credentials
    # save tokens in session
    session['credentials'] = {
        'token':         creds.token,
        'refresh_token': creds.refresh_token,
        'token_uri':     creds.token_uri,
        'client_id':     creds.client_id,
        'client_secret': creds.client_secret,
        'scopes':        creds.scopes,
    }
    return redirect(url_for('settings'))

def upload_file_to_drive(file_path, filename):
    if 'credentials' not in session:
        return None

    creds = Credentials.from_authorized_user_info(session['credentials'], SCOPES)
    service = build('drive', 'v3', credentials=creds)

    metadata = {'name': filename}
    folder_id = os.getenv('GOOGLE_DRIVE_FOLDER_ID')
    if folder_id:
        metadata['parents'] = [folder_id]

    media = MediaFileUpload(file_path, resumable=True)
    uploaded = service.files().create(
        body=metadata,
        media_body=media,
        fields='id'
    ).execute()

    return uploaded.get('id')