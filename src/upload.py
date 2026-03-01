import os
import json
import paramiko
from paramiko import SSHClient

# Hetzner server configuration
HETZNER_IP = "116.203.110.27"
HETZNER_USER = "root"
# We'll use the ed25519 key we found on your Mac
HETZNER_KEY_PATH = os.path.expanduser("~/.ssh/id_ed25519")
# The folder on the Hetzner server where videos will queue up
HETZNER_QUEUE_DIR = "/root/youtube_queue"

def get_sftp_client():
    """Connects to the Hetzner server via SSH and returns an SFTP client."""
    ssh = SSHClient()
    # Automatically add the server's host key (avoids the yes/no prompt)
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    if not os.path.exists(HETZNER_KEY_PATH):
        raise FileNotFoundError(f"SSH Key not found at {HETZNER_KEY_PATH}. Ensure you can connect to your server.")
        
    ssh.connect(
        hostname=HETZNER_IP,
        username=HETZNER_USER,
        key_filename=HETZNER_KEY_PATH,
        # Increase timeout for large files
        timeout=30 
    )
    
    sftp = ssh.open_sftp()
    
    # Ensure the remote queue directory exists
    try:
        sftp.stat(HETZNER_QUEUE_DIR)
    except FileNotFoundError:
        sftp.mkdir(HETZNER_QUEUE_DIR)
        
    return ssh, sftp

def upload_file_sftp(sftp, local_path: str, remote_filename: str) -> str:
    """Uploads a single file via SFTP with a progress callback (optional)."""
    remote_path = f"{HETZNER_QUEUE_DIR}/{remote_filename}"
    sftp.put(local_path, remote_path)
    return remote_path

def upload_video_package(video_path: str, thumbnail_path: str, language: str, metadata: dict) -> dict:
    """
    Main function to upload the video, thumbnail, and metadata directly to Hetzner via SFTP.
    """
    base_name = os.path.splitext(os.path.basename(video_path))[0]
    results = {}
    
    try:
        ssh, sftp = get_sftp_client()
        
        # 1. Upload Video
        if video_path and os.path.exists(video_path):
            remote_vid = upload_file_sftp(sftp, video_path, f"{base_name}.mp4")
            results['video_path'] = remote_vid
            
        # 2. Upload Thumbnail
        if thumbnail_path and os.path.exists(thumbnail_path):
            remote_thumb = upload_file_sftp(sftp, thumbnail_path, f"{base_name}_thumb.jpg")
            results['thumbnail_path'] = remote_thumb
            
        # 3. Add file names to metadata so the Hetzner script knows which files to look for
        metadata['video_file'] = f"{base_name}.mp4"
        metadata['thumbnail_file'] = f"{base_name}_thumb.jpg"
        metadata['language'] = language
        
        # 4. Create local JSON and Upload Metadata JSON
        json_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output", f"{base_name}_metadata.json")
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=4)
            
        remote_json = upload_file_sftp(sftp, json_path, f"{base_name}_metadata.json")
        results['metadata_path'] = remote_json
        
        # Clean up local json
        if os.path.exists(json_path):
            os.remove(json_path)
            
    finally:
        # Always close connections
        if 'sftp' in locals():
            sftp.close()
        if 'ssh' in locals():
            ssh.close()
            
    return results