import random
from typing import List
from pydantic import BaseModel, Field
from google import genai
from src.config import GEMINI_API_KEY

# Initialize Gemini Client
client = genai.Client(api_key=GEMINI_API_KEY)

# Define schemas for structured outputs
class DialogueLine(BaseModel):
    speaker: str = Field(description='Must be either "left" or "right"')
    text: str = Field(description="The spoken dialogue line in the target language (e.g. German)")
    translation: str = Field(description="English translation of the dialogue line")

class Conversation(BaseModel):
    title: str = Field(description="A short title for this specific conversation")
    left_gender: str = Field(description="The gender of the left speaker for this specific conversation, e.g., 'male' or 'female'")
    right_gender: str = Field(description="The gender of the right speaker for this specific conversation, e.g., 'male' or 'female'")
    image_prompt: str = Field(description="A detailed prompt for an AI image generator to create the background image for this scenario. MUST specify the characters, the setting, and EXPLICITLY state that there should be NO TEXT, NO WORDS, NO LETTERS, and NO WATERMARKS in the generated image.")
    dialogue: List[DialogueLine] = Field(description="Chronological list of dialogue lines between the two characters.")

class ConversationIdea(BaseModel):
    title: str = Field(description="A short title for this specific conversation")
    description: str = Field(description="A brief description of what the conversation will be about")
    left_gender: str = Field(description="The gender of the left speaker for this specific conversation, e.g., 'male' or 'female'")
    right_gender: str = Field(description="The gender of the right speaker for this specific conversation, e.g., 'male' or 'female'")

class VideoOutline(BaseModel):
    video_title: str = Field(description="An engaging, YouTube-optimized title for the video")
    video_description: str = Field(description="A brief, YouTube-optimized description of the video scenario")
    conversation_ideas: List[ConversationIdea] = Field(description="List of distinct conversation ideas within this topic")

class VideoContent(BaseModel):
    video_title: str = Field(description="An engaging, YouTube-optimized title for the video")
    video_description: str = Field(description="A brief, YouTube-optimized description of the video scenario")
    conversations: List[Conversation] = Field(description="List of distinct conversations within this topic")

class TopicList(BaseModel):
    topics: List[str] = Field(description="List of 3-5 practical language learning topics/scenarios")

def generate_topics(language: str = "German", count: int = 3) -> List[str]:
    """Generates fresh, practical language learning topics."""
    prompt = f"""Generate {count} completely FRESH, highly practical, and specific everyday scenarios 
    for someone learning {language} at an A1/A2 level. 
    Examples: "Reporting a Stolen Wallet to the Police", "Ordering Food at a Drive-Thru".
    Return ONLY a JSON object containing a list of strings called 'topics'."""
    
    response = client.models.generate_content(
        model='gemini-3-flash-preview',
        contents=prompt,
        config=genai.types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=TopicList,
            temperature=0.9, # Higher temperature for more variety
        ),
    )
    return response.parsed.topics

def generate_video_outline(topic: str, num_conversations: int = 1) -> VideoOutline:
    """Generates the high-level outline and ideas for the requested number of conversations."""
    prompt = f"""You are creating an outline for a language learning video. 
    The overarching scenario is: "{topic}".
    Generate {num_conversations} distinct conversation ideas/scenarios related to this topic.
    For EACH conversation idea, randomly choose the gender of the left speaker and the right speaker (one male, one female).
    Return a structured JSON containing a YouTube-optimized 'video_title', 'video_description', and the 'conversation_ideas' array.
    """
    
    response = client.models.generate_content(
        model='gemini-3-flash-preview',
        contents=prompt,
        config=genai.types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=VideoOutline,
            temperature=0.7,
        ),
    )
    return response.parsed

def generate_conversation_dialogue(
    idea: ConversationIdea, 
    language: str = "German", 
    min_sentences: int = 50, 
    max_sentences: int = 70
) -> Conversation:
    import time
    """Generates the actual line-by-line dialogue for a single conversation idea."""
    prompt = f"""Write a distinct, natural A1/A2 level language-learning conversation in {language} between two characters.
    The specific scenario for this conversation is: "{idea.title}" - {idea.description}.
    
    The conversation MUST have exactly between {min_sentences} and {max_sentences} sentences/lines total.
    There are exactly two characters: 
    - One is the "left" speaker (Gender: {idea.left_gender}).
    - One is the "right" speaker (Gender: {idea.right_gender}).
    
    Make the dialogue engaging, realistic, and highly practical for language learners.
    Also generate an `image_prompt` that describes the scene visually for an AI image generator. The image prompt MUST include explicit instructions that there can NOT be ANY text, letters, or words in the image.
    Return a structured JSON containing the 'title', 'left_gender', 'right_gender', 'image_prompt', and the chronological 'dialogue' array.
    """
    
    max_retries = 3
    retry_delay = 5.0
    
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model='gemini-3-flash-preview',
                contents=prompt,
                config=genai.types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=Conversation,
                    temperature=0.7,
                ),
            )
            return response.parsed
        except Exception as e:
            if "429" in str(e) or attempt < max_retries - 1:
                print(f"Rate limit or error hit for dialogue generation (attempt {attempt + 1}). Sleeping for {retry_delay}s...")
                time.sleep(retry_delay)
                retry_delay *= 2
            else:
                raise

def generate_video_content(topic: str, language: str = "German", num_conversations: int = 1, min_sentences: int = 50, max_sentences: int = 70) -> VideoContent:
    """Orchestrates the two-step generation process: first the outline, then individual conversations in parallel."""
    import streamlit as st # Only for progress reporting if called from UI
    import concurrent.futures
    import time
    
    # Step 1: Generate the outline
    outline = generate_video_outline(topic, num_conversations)
    
    # Step 2: Generate each conversation in parallel
    conversations = [None] * num_conversations
    
    # Check if we are running inside Streamlit for progress updates
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        has_streamlit = get_script_run_ctx() is not None
    except ImportError:
        has_streamlit = False

    if has_streamlit and num_conversations > 1:
        st.info(f"Generating {num_conversations} conversations in parallel...")
        progress_bar = st.progress(0)
        status_text = st.empty()
    
    completed_count = 0
    
    def process_idea(idx_and_idea):
        idx, idea = idx_and_idea
        
        # Add a small staggered delay based on index to prevent 20 simultaneous 
        # requests hitting the exact same millisecond and triggering a hard 429 rate limit
        time.sleep(idx * 0.5)
        
        conv = generate_conversation_dialogue(
            idea=idea,
            language=language,
            min_sentences=min_sentences,
            max_sentences=max_sentences
        )
        
        # Ensure the generated conversation retains the original outline metadata
        conv.title = idea.title
        conv.left_gender = idea.left_gender
        conv.right_gender = idea.right_gender
        return idx, conv

    # Execute up to 5 concurrent API calls at a time
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(process_idea, (i, idea)): i for i, idea in enumerate(outline.conversation_ideas)}
        
        for future in concurrent.futures.as_completed(futures):
            idx, conv = future.result()
            conversations[idx] = conv
            completed_count += 1
            
            if has_streamlit and num_conversations > 1:
                status_text.text(f"Completed {completed_count}/{num_conversations} conversations...")
                progress_bar.progress(completed_count / num_conversations)
            
    if has_streamlit and num_conversations > 1:
        progress_bar.empty()
        status_text.empty()

    return VideoContent(
        video_title=outline.video_title,
        video_description=outline.video_description,
        conversations=conversations
    )

