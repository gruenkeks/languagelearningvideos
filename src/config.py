import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# API Keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")

# Validate required keys
def validate_config():
    missing_keys = []
    if not GEMINI_API_KEY:
        missing_keys.append("GEMINI_API_KEY")
    if not REPLICATE_API_TOKEN:
        missing_keys.append("REPLICATE_API_TOKEN")
        
    if missing_keys:
        raise ValueError(f"Missing required environment variables: {', '.join(missing_keys)}. Please check your .env file.")

# System settings
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")
FINAL_VIDEO_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "final_videos")

# Ensure directories exist
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(FINAL_VIDEO_DIR, exist_ok=True)

