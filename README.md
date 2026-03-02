# Practical Languages Video Generator

A fully automated pipeline that generates language-learning YouTube videos (German, French, Spanish, Italian, etc.), including audio, subtitles, backgrounds, and thumbnails, and automatically queues them on a remote server for scheduled uploading to distinct YouTube channels.

## System Architecture

1. **Local Generation (Mac)**: Streamlit app (`app.py`) orchestrates Gemini 3 Flash Preview (dialogue/metadata), Replicate (background images), Gemini TTS (audio), MoviePy (video assembly), and MediaPipe (thumbnail generation).
2. **The Upload Queue (Mac -> Hetzner)**: Videos and metadata are pushed directly via SFTP (`src/upload.py`) to the Hetzner VPS into `/root/youtube_queue/`.
3. **Remote Server Automation (Hetzner -> YouTube)**: A scheduled cron job uploads videos to their respective language-specific YouTube channels.

## Hetzner YouTube Uploader Instructions

The remote server handles chunked, resumable uploads to YouTube to prevent OOM errors on the 4GB Hetzner server. 

### Automated Execution (Cron)
The server is configured to automatically pull one video per language from the queue and upload it to YouTube three times a day (10:00, 15:00, and 20:00 UTC).

The crontab on the Hetzner server is configured as:
```bash
0 10,15,20 * * * /usr/bin/python3 /root/server_scripts/hetzner_youtube_uploader.py >> /root/upload_log.txt 2>&1
```

### Manual Execution (For Testing/Debugging)
If you want to manually trigger the upload script on Hetzner to clear the queue or test an upload, follow these steps:

1. **SSH into the Hetzner Server**:
   Open your local terminal and connect:
   ```bash
   ssh root@116.203.110.27
   ```

2. **Run the Script**:
   Execute the python script directly. It will scan the queue, upload the oldest video for each language, and delete the files upon success.
   ```bash
   /usr/bin/python3 /root/server_scripts/hetzner_youtube_uploader.py
   ```
   *Note: If the queue is empty, it will simply output "No videos found in queue" and exit cleanly.*

3. **Check the Queue (Optional)**:
   If you want to see what is currently waiting to be uploaded:
   ```bash
   ls -la /root/youtube_queue/
   ```

### Updating Authentication Tokens
If an OAuth token expires or needs to be refreshed:
1. Run `python3 server_scripts/local_auth.py [Language]` locally on your Mac.
2. Upload the newly generated `youtube_oauth_token_[Language].json` file to `/root/` on the Hetzner server.
