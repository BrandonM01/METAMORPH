import random
from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive

def scale_range(min_val, max_val, intensity):
    factor = intensity / 100
    return random.uniform(min_val * factor, max_val * factor)

def upload_to_google_drive(file_path, filename):
    gauth = GoogleAuth()
    gauth.LoadCredentialsFile("credentials.json")
    if gauth.credentials is None:
        gauth.LocalWebserverAuth()
    elif gauth.access_token_expired:
        gauth.Refresh()
    else:
        gauth.Authorize()
    gauth.SaveCredentialsFile("credentials.json")

    drive = GoogleDrive(gauth)
    folder_list = drive.ListFile({'q': "title='MetadataChangerBackup' and mimeType='application/vnd.google-apps.folder' and trashed=false"}).GetList()
    folder_id = folder_list[0]['id'] if folder_list else drive.CreateFile({'title': 'MetadataChangerBackup', 'mimeType': 'application/vnd.google-apps.folder'}).Upload().get('id')

    file_drive = drive.CreateFile({'title': filename, 'parents': [{'id': folder_id}]})
    file_drive.SetContentFile(file_path)
    file_drive.Upload()
