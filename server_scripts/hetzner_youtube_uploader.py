import os
import sys
import json
import time
from datetime import datetime, timedelta
import httplib2
import random

# Google API libraries
import google.oauth2.credentials
import google_auth_oauthlib.flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

# The folder where the Streamlit app drops the files
QUEUE_DIR = "/root/youtube_queue"

# Client secrets file from Google Cloud Console (OAuth 2.0 Client IDs, NOT an API Key)
CLIENT_SECRETS_FILE = "client_secret.json"

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
API_SERVICE_NAME = "youtube"
API_VERSION = "v3"

VALID_PRIVACY_STATUSES = ("public", "private", "unlisted")

def get_authenticated_service(language):
    """Authenticates the user and returns the YouTube API service for the specific language channel."""
    creds = None
    
    # Path to the specific language token
    token_file = f"/root/youtube_oauth_token_{language}.json"
    
    # Check if we already have a saved token
    if os.path.exists(token_file):
        with open(token_file, 'r') as f:
            creds_data = json.load(f)
            creds = google.oauth2.credentials.Credentials(**creds_data)
            
    # If no valid credentials available, raise an error
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print(f"Refreshing expired access token for {language}...")
            # We can't automatically refresh without a Request object in some google-auth versions,
            # but usually it's handled. For safety, we fall back to manual if it fails.
            pass 
        else:    
            raise Exception(f"Missing or invalid authentication token for language '{language}'. "
                            f"Make sure you run local_auth.py for {language} and upload "
                            f"the resulting token to {token_file} on the server.")
            
    return build(API_SERVICE_NAME, API_VERSION, credentials=creds)

def initialize_upload(youtube, options):
    """Initializes the resumable upload to YouTube."""
    tags = None
    if options.get("tags"):
        tags = [tag.strip() for tag in options.get("tags", "").split(",")]

    body = {
        "snippet": {
            "title": options.get("title", "Test Video Title"),
            "description": options.get("description", "Test Description"),
            "tags": tags,
            "categoryId": "27" # 27 = Education
        },
        "status": {
            "privacyStatus": options.get("privacyStatus", "private"),
            "selfDeclaredMadeForKids": False
        }
    }

    print(f"Uploading {options['file']}...")
    
    # Resumable upload of the video file
    insert_request = youtube.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=MediaFileUpload(options["file"], chunksize=-1, resumable=True)
    )

    return resumable_upload(insert_request)

def resumable_upload(request):
    """Executes the resumable upload."""
    response = None
    error = None
    retry = 0
    MAX_RETRIES = 10
    RETRIABLE_STATUS_CODES = [500, 502, 503, 504]
    
    while response is None:
        try:
            print("Uploading file...")
            status, response = request.next_chunk()
            if response is not None:
                if 'id' in response:
                    print(f"Video id '{response['id']}' was successfully uploaded.")
                    return response['id']
                else:
                    exit("The upload failed with an unexpected response: %s" % response)
        except HttpError as e:
            if e.resp.status in RETRIABLE_STATUS_CODES:
                error = "A retriable HTTP error %d occurred:\n%s" % (e.resp.status, e.content)
            else:
                raise
        except (httplib2.HttpLib2Error, IOError) as e:
            error = "A retriable error occurred: %s" % e

        if error is not None:
            print(error)
            retry += 1
            if retry > MAX_RETRIES:
                exit("No longer attempting to retry.")

            max_sleep = 2 ** retry
            sleep_seconds = random.random() * max_sleep
            print(f"Sleeping {sleep_seconds} seconds and then retrying...")
            time.sleep(sleep_seconds)

def upload_thumbnail(youtube, video_id, thumbnail_path):
    """Uploads a custom thumbnail to the specific video."""
    print(f"Uploading thumbnail {thumbnail_path}...")
    request = youtube.thumbnails().set(
        videoId=video_id,
        media_body=MediaFileUpload(thumbnail_path)
    )
    response = request.execute()
    print("Thumbnail uploaded successfully.")

def process_queue():
    """Scans the queue directory, groups by language, processes the oldest video for each language, and cleans up."""
    if not os.path.exists(QUEUE_DIR):
        print(f"Queue directory {QUEUE_DIR} does not exist.")
        return
        
    # Find all JSON metadata files
    json_files = [f for f in os.listdir(QUEUE_DIR) if f.endswith('_metadata.json')]
    
    if not json_files:
        print("No videos found in queue.")
        return
        
    # Group files by language
    files_by_language = {}
    for json_file in json_files:
        json_path = os.path.join(QUEUE_DIR, json_file)
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
                language = metadata.get("language", "German")
                if language not in files_by_language:
                    files_by_language[language] = []
                files_by_language[language].append((json_file, metadata))
        except Exception as e:
            print(f"Error reading metadata file {json_file}: {e}")
            continue

    if not files_by_language:
        print("No valid videos found in queue.")
        return

    # Process one video (the oldest) per language
    for language, files in files_by_language.items():
        # Sort by modification time to get the oldest
        files.sort(key=lambda x: os.path.getmtime(os.path.join(QUEUE_DIR, x[0])))
        target_json, metadata = files[0]
        
        json_path = os.path.join(QUEUE_DIR, target_json)
        video_file = os.path.join(QUEUE_DIR, metadata['video_file'])
        thumbnail_file = os.path.join(QUEUE_DIR, metadata['thumbnail_file'])
        
        if not os.path.exists(video_file):
            print(f"Error: Video file {video_file} not found for {language}!")
            continue
            
        try:
            print(f"\n--- Processing upload for language: {language} ---")
            youtube = get_authenticated_service(language)
            
            # Prepare upload options
            options = {
                "file": video_file,
                "title": metadata.get("title", "Language Learning Video"),
                "description": metadata.get("description", "Learn a new language."),
                "tags": "language,learning,education",
                # We set to private by default for safety. Change to 'public' if you want it live immediately.
                "privacyStatus": "private" 
            }
            
            # 1. Upload the Video
            video_id = initialize_upload(youtube, options)
            
            # 2. Upload the Thumbnail
            if os.path.exists(thumbnail_file):
                upload_thumbnail(youtube, video_id, thumbnail_file)
                
            print(f"Upload process completely finished for {language}!")
            
            # 3. Clean up the files from the Hetzner server
            os.remove(video_file)
            if os.path.exists(thumbnail_file):
                os.remove(thumbnail_file)
            os.remove(json_path)
            print(f"Cleaned up files for {video_id} ({language}) from {QUEUE_DIR}")
            
        except Exception as e:
            print(f"An error occurred during processing for {language}: {e}")
            
    print("\nQueue processing complete for all languages.")

if __name__ == '__main__':
    process_queue()