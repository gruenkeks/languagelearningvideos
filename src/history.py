import os
import json
from datetime import datetime

HISTORY_DIR = "video_history"

def ensure_history_dir():
    if not os.path.exists(HISTORY_DIR):
        os.makedirs(HISTORY_DIR)

def save_history(title: str, conversations: list, language: str):
    ensure_history_dir()
    
    # Extract only bullet points / short summaries of conversations
    conv_summaries = []
    for conv in conversations:
        # Some conversations might be dicts or objects depending on where they come from
        if isinstance(conv, dict):
            title_val = conv.get('title', '')
        else:
            title_val = getattr(conv, 'title', '')
        # We don't have descriptions in the final conversation objects usually, we have title.
        conv_summaries.append(title_val)
        
    data = {
        "timestamp": datetime.now().isoformat(),
        "language": language,
        "title": title,
        "conversation_summaries": conv_summaries
    }
    
    safe_title = "".join(x for x in title if x.isalnum() or x in " -_").strip().replace(" ", "_").lower()[:50]
    filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{language}_{safe_title}.json"
    filepath = os.path.join(HISTORY_DIR, filename)
    
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print(f"Saved history to {filepath}")
    except Exception as e:
        print(f"Failed to save history: {e}")

def get_history_context(language: str = None, max_videos: int = 90) -> str:
    """
    Reads the last `max_videos` from the history directory.
    Returns a formatted string containing the titles and summaries to be used as context.
    """
    ensure_history_dir()
    
    files = [f for f in os.listdir(HISTORY_DIR) if f.endswith('.json')]
    # Sort files by name (which starts with timestamp) in descending order to get latest first
    files.sort(reverse=True)
    
    history_entries = []
    
    count = 0
    for file in files:
        if count >= max_videos:
            break
            
        filepath = os.path.join(HISTORY_DIR, file)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            if language and data.get("language") != language:
                continue
                
            title = data.get("title", "")
            summaries = data.get("conversation_summaries", [])
            
            entry = f"Title: {title}\nTopics covered: {', '.join(summaries)}"
            history_entries.append(entry)
            count += 1
        except Exception as e:
            print(f"Error reading history file {file}: {e}")
            
    if not history_entries:
        return "No previous videos."
        
    return "\n".join(history_entries)
