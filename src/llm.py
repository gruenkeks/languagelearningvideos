import random
from typing import List
from pydantic import BaseModel, Field
from google import genai
from src.config import GEMINI_API_KEY

# Initialize Gemini Client
client = genai.Client(vertexai=True, api_key=GEMINI_API_KEY, http_options={"base_url": "https://aiplatform.googleapis.com/"})

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
    video_title: str = Field(description="An engaging, YouTube-optimized title for the video (MUST be under 100 characters)")
    video_description: str = Field(description="A brief, YouTube-optimized description of the video scenario")
    conversation_ideas: List[ConversationIdea] = Field(description="List of distinct conversation ideas within this topic")

class VideoContent(BaseModel):
    video_title: str = Field(description="An engaging, YouTube-optimized title for the video (MUST be under 100 characters)")
    video_description: str = Field(description="A brief, YouTube-optimized description of the video scenario")
    conversations: List[Conversation] = Field(description="List of distinct conversations within this topic")

class TopicList(BaseModel):
    topics: List[str] = Field(description="List of 3-5 practical language learning topics/scenarios")

class ThumbnailText(BaseModel):
    left_bubble: str = Field(description="Very short, catchy text for the left speaker's bubble (2-4 words maximum). Must fit in a small bubble on a thumbnail.")
    right_bubble: str = Field(description="Very short, catchy text for the right speaker's bubble (2-4 words maximum). Must make sense as a reply or connection to the left bubble.")
    left_head_x: float = Field(description="The X coordinate of the left character's head (0.0 to 1.0, where 0.0 is left edge, 1.0 is right edge).")
    left_head_y: float = Field(description="The Y coordinate of the left character's head (0.0 to 1.0, where 0.0 is top edge, 1.0 is bottom edge).")
    right_head_x: float = Field(description="The X coordinate of the right character's head (0.0 to 1.0, where 0.0 is left edge, 1.0 is right edge).")
    right_head_y: float = Field(description="The Y coordinate of the right character's head (0.0 to 1.0, where 0.0 is top edge, 1.0 is bottom edge).")

def generate_topics(language: str = "German", count: int = 3, history_context: str = "") -> List[str]:
    """Generates fresh, practical language learning topics."""
    prompt = f"""Generate {count} completely FRESH, very broad, and common everyday situations 
    for someone learning {language} at an A1/A2 level. 
    Examples: "In the train", "Buying groceries", "At school", "At the doctor", "In a restaurant".
    Do NOT make them overly specific (e.g. NOT "Buying a Monthly Public Transport Ticket at a Service Center"). Keep them broad so that many different small dialogues can happen within this setting.
    
    {'IMPORTANT: The following videos/topics have ALREADY been done. DO NOT repeat these ideas or use very similar situations:' if history_context and history_context != 'No previous videos.' else ''}
    {history_context if history_context and history_context != 'No previous videos.' else ''}
    
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

def generate_video_outline(topic: str, num_conversations: int = 1, history_context: str = "") -> tuple[VideoOutline, dict]:
    """Generates the high-level outline and ideas for the requested number of conversations."""
    import time
    
    prompt = f"""You are creating an outline for a language learning video. 
    The overarching scenario is: "{topic}".
    Generate {num_conversations} distinct conversation ideas/scenarios related to this topic.
    For EACH conversation idea, randomly choose the gender of the left speaker and the right speaker (one male, one female).
    
    {'IMPORTANT CONTEXT - The following topics have already been covered in previous videos. Ensure your new conversation ideas are FRESH and DO NOT repeat these specific situations:' if history_context and history_context != 'No previous videos.' else ''}
    {history_context if history_context and history_context != 'No previous videos.' else ''}
    
    IMPORTANT: The `video_title` and `video_description` MUST be highly engaging, professional, and SEO-optimized for YouTube, directly inspired by top-performing language learning channels.
    They MUST be written in English, but the video is for learning a foreign language. 
    Whenever you need to mention the target language being learned, you MUST use the EXACT placeholder "[LANGUAGE]" instead of the actual language name.
    Do NOT write "English" as the language being learned. Use "[LANGUAGE]".
    
    Guidelines for `video_title`:
    - CRITICAL: The title MUST be strictly UNDER 100 characters long! Keep it punchy and concise.
    - Make it catchy and descriptive. Include the target language placeholder ([LANGUAGE]), the level (A1-A2), a hook, and the topic.
    - Example: "Daily [LANGUAGE] Dialogues (A1-A2) | Learn [LANGUAGE] Fast"
    
    Guidelines for `video_description`:
    - Use emojis and a clear structure.
    - Write a captivating intro hook (e.g. "Real Dialogues That Will Transform Your Speaking! ⭐️ With this video, you'll learn the way it's really spoken...").
    - Include a "🌟 What You'll Learn" section with bullet points.
    - Include a "💡 The Method" section.
    - Include a "🚀 Who This Video Is For" section.
    - Include a "📚 Bonus Features" section.
    - End with a call to action and plenty of relevant hashtags (e.g., #Learn[LANGUAGE] #[LANGUAGE]Dialogues #Speaking #Everyday[LANGUAGE]).
    
    Return a structured JSON containing the YouTube-optimized 'video_title', the rich 'video_description', and the 'conversation_ideas' array.
    """
    
    max_retries = 3
    retry_delay = 2.0
    total_usage = {"prompt_tokens": 0, "candidates_tokens": 0}
    
    for attempt in range(max_retries):
        response = client.models.generate_content(
            model='gemini-3-flash-preview',
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=VideoOutline,
                temperature=0.7,
            ),
        )
        
        usage = {
            "prompt_tokens": response.usage_metadata.prompt_token_count if response.usage_metadata else 0,
            "candidates_tokens": response.usage_metadata.candidates_token_count if response.usage_metadata else 0
        }
        total_usage["prompt_tokens"] += usage["prompt_tokens"]
        total_usage["candidates_tokens"] += usage["candidates_tokens"]
        
        parsed = response.parsed
        
        # Check title length constraint
        title_length = len(parsed.video_title.replace("[LANGUAGE]", "Spanish")) # Check with longest language name
        if title_length <= 100:
            return parsed, total_usage
            
        print(f"Attempt {attempt + 1}: Generated title is too long ({title_length} chars). Title: {parsed.video_title}")
        
        if attempt < max_retries - 1:
            time.sleep(retry_delay)
            # Tweak the prompt to insist on brevity
            prompt += "\nCRITICAL REMINDER: The previous `video_title` was too long. You MUST make the `video_title` significantly shorter (under 80 characters) this time."
        else:
            print("Max retries reached. Truncating title to fit YouTube limits.")
            # Hard truncate at 95 to leave room for the language replacement
            parsed.video_title = parsed.video_title[:90] + "..."
            return parsed, total_usage

def generate_conversation_dialogue(
    idea: ConversationIdea, 
    language: str = "German", 
    min_sentences: int = 50, 
    max_sentences: int = 70
) -> tuple[Conversation, dict]:
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
            usage = {
                "prompt_tokens": response.usage_metadata.prompt_token_count if response.usage_metadata else 0,
                "candidates_tokens": response.usage_metadata.candidates_token_count if response.usage_metadata else 0
            }
            return response.parsed, usage
        except Exception as e:
            if "429" in str(e) or attempt < max_retries - 1:
                print(f"Rate limit or error hit for dialogue generation (attempt {attempt + 1}). Sleeping for {retry_delay}s...")
                time.sleep(retry_delay)
                retry_delay *= 2
            else:
                raise

def generate_thumbnail_text(topic: str, context_dialogue: str, language: str, image_path: str) -> tuple[ThumbnailText, dict]:
    """Generates two very short, punchy speech bubble texts for a YouTube thumbnail."""
    import PIL.Image
    img = PIL.Image.open(image_path)
    
    prompt = f"""You are creating text for a YouTube thumbnail for a language learning video.
    The topic is: "{topic}".
    Here is a snippet of dialogue that happens in the scene:
    {context_dialogue}
    
    Create one very short, catchy line for the person on the left, and one for the person on the right.
    Both MUST be in {language}.
    Each line MUST be extremely short (1 to 4 words max) so it can be read easily on a small thumbnail.
    Example Left: "Was ist los?" Example Right: "Ich weiß nicht!"
    Example Left: "Wo ist mein Gepäck?" Example Right: "Ein Moment, bitte!"
    
    ALSO, analyze the image and find the heads of the two characters.
    Provide the exact coordinates (X and Y as a float between 0.0 and 1.0) for the left character's head and the right character's head.
    (0.0, 0.0) is the top-left corner, and (1.0, 1.0) is the bottom-right corner.
    
    Return the structured JSON containing the bubble texts and the head coordinates.
    """
    
    response = client.models.generate_content(
        model='gemini-3-flash-preview',
        contents=[img, prompt],
        config=genai.types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ThumbnailText,
            temperature=0.7,
        ),
    )
    usage = {
        "prompt_tokens": response.usage_metadata.prompt_token_count if response.usage_metadata else 0,
        "candidates_tokens": response.usage_metadata.candidates_token_count if response.usage_metadata else 0
    }
    return response.parsed, usage

def generate_video_content(topic: str, language: str = "German", num_conversations: int = 1, min_sentences: int = 50, max_sentences: int = 70, outline: VideoOutline = None, history_context: str = "") -> tuple[VideoContent, dict]:
    """Orchestrates the two-step generation process: first the outline, then individual conversations in parallel."""
    import streamlit as st # Only for progress reporting if called from UI
    import concurrent.futures
    import time
    
    total_usage = {"prompt_tokens": 0, "candidates_tokens": 0}

    # Step 1: Generate the outline if not provided
    if outline is None:
        outline, outline_usage = generate_video_outline(topic, num_conversations, history_context)
        total_usage["prompt_tokens"] += outline_usage["prompt_tokens"]
        total_usage["candidates_tokens"] += outline_usage["candidates_tokens"]
    
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
        
        # Add a small staggered delay based on index
        time.sleep(idx * 0.1)
        
        conv, conv_usage = generate_conversation_dialogue(
            idea=idea,
            language=language,
            min_sentences=min_sentences,
            max_sentences=max_sentences
        )
        
        # Ensure the generated conversation retains the original outline metadata
        conv.title = idea.title
        conv.left_gender = idea.left_gender
        conv.right_gender = idea.right_gender
        return idx, conv, conv_usage

    # Execute up to 12 concurrent API calls (Vertex AI allows higher limits)
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
        futures = {executor.submit(process_idea, (i, idea)): i for i, idea in enumerate(outline.conversation_ideas)}
        
        for future in concurrent.futures.as_completed(futures):
            idx, conv, conv_usage = future.result()
            conversations[idx] = conv
            total_usage["prompt_tokens"] += conv_usage["prompt_tokens"]
            total_usage["candidates_tokens"] += conv_usage["candidates_tokens"]
            completed_count += 1
            
            if has_streamlit and num_conversations > 1:
                status_text.text(f"Completed {completed_count}/{num_conversations} conversations...")
                progress_bar.progress(completed_count / num_conversations)
            
    if has_streamlit and num_conversations > 1:
        progress_bar.empty()
        status_text.empty()

    return VideoContent(
        video_title=outline.video_title.replace("[LANGUAGE]", language),
        video_description=outline.video_description.replace("[LANGUAGE]", language),
        conversations=conversations
    ), total_usage

class YouTubeMetadata(BaseModel):
    title: str = Field(description="An engaging, YouTube-optimized title for the video (MUST be under 100 characters)")
    description: str = Field(description="A highly formatted, beautifully spaced YouTube-optimized description")

def generate_final_metadata(topic: str, language: str, duration_str: str, num_conversations: int, history_context: str = "") -> tuple[YouTubeMetadata, dict]:
    """Generates the final beautifully formatted YouTube title and description."""
    import time
    prompt = f"""You are creating the final YouTube title and description for a language learning video. 
    The overarching scenario is: "{topic}".
    Language being learned: {language}
    Video duration: {duration_str}
    Number of distinct conversations/dialogues in the video: {num_conversations}
    
    IMPORTANT: You must write the final title and description in English, but mention the target language being learned ({language}).

    Guidelines for `title`:
    - CRITICAL: MUST be strictly UNDER 100 characters long! Keep it punchy and concise.
    - Structure it like top language channels. Feel free to use the video duration or the number of conversations in the title if it sounds good.
    - Examples of style:
      "1 hour: practice speaking {language} | {num_conversations} everyday dialogues (A1 - A2)"
      "35 Minutes of Basic {language} Conversations (A1-A2) Dialogues that Everyone Should Know"
      "Simple {language} Conversations for Beginners | 10 Real-Life {language} dialogues (A1-A2)"
      "Learning {language} for beginners: 4 important everyday stories (A1-A2)"
    - Vary the structure somewhat based on what fits best.
    
    Guidelines for `description`:
    - Format it beautifully! Use blank lines (newlines) between sections to make it easy to read.
    - Every bullet point should be on a NEW LINE. Do not cram them together.
    - Use emojis and a clear structure.
    - Include a captivating intro hook.
    - Include a "🌟 What You'll Learn" section with clearly separated bullet points (one per line).
    - Include a "💡 The Method" section.
    - Include a "🚀 Who This Video Is For" section.
    - Include a "📚 Bonus Features" section.
    - End with a call to action and hashtags (e.g., #Learn{language} #{language}Dialogues).
    """
    
    max_retries = 3
    retry_delay = 2.0
    
    for attempt in range(max_retries):
        response = client.models.generate_content(
            model='gemini-3-flash-preview',
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=YouTubeMetadata,
                temperature=0.7,
            ),
        )
        
        usage = {
            "prompt_tokens": response.usage_metadata.prompt_token_count if response.usage_metadata else 0,
            "candidates_tokens": response.usage_metadata.candidates_token_count if response.usage_metadata else 0
        }
        
        parsed = response.parsed
        
        if len(parsed.title) <= 100:
            return parsed, usage
            
        if attempt < max_retries - 1:
            time.sleep(retry_delay)
            prompt += "\nCRITICAL REMINDER: The previous `title` was too long. You MUST make the `title` significantly shorter (under 100 characters) this time."
        else:
            parsed.title = parsed.title[:95] + "..."
            return parsed, usage


