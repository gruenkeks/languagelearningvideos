import os
import streamlit as st
import base64
import atexit
import shutil

from src.config import validate_config, OUTPUT_DIR, FINAL_VIDEO_DIR
from src.llm import generate_topics, generate_video_content
from src.image import generate_background_image
from src.tts import generate_audio_for_conversations
from src.video import render_final_video

# Cleanup function to clear directories when program stops
def cleanup_on_exit():
    for directory in [OUTPUT_DIR, FINAL_VIDEO_DIR]:
        if os.path.exists(directory):
            try:
                for filename in os.listdir(directory):
                    file_path = os.path.join(directory, filename)
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                print(f"Cleared directory: {directory}")
            except Exception as e:
                print(f"Failed to clear {directory}: {e}")

# Register the cleanup function
atexit.register(cleanup_on_exit)

def main():
    st.set_page_config(page_title="Language Video Gen", page_icon="🎥", layout="wide")

    st.title("🎥 Language Learning Video Generator")
    st.markdown("Automate the creation of A1/A2 language learning dialogue videos.")

    # Validate Config
    try:
        validate_config()
    except Exception as e:
        st.error(f"Configuration Error: {e}")
        st.info("Please create a `.env` file with `GEMINI_API_KEY` and `REPLICATE_API_TOKEN`.")
        st.stop()

    # Session State Initialization
    if "topics" not in st.session_state:
        st.session_state.topics = []
    if "selected_topic" not in st.session_state:
        st.session_state.selected_topic = ""
    if "video_rendered" not in st.session_state:
        st.session_state.video_rendered = False
    if "final_video_path" not in st.session_state:
        st.session_state.final_video_path = ""
    if "video_metadata" not in st.session_state:
        st.session_state.video_metadata = {}

    st.header("Step 1: Choose a Topic")

    # Topic Generation
    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("🔄 Generate Fresh Topics"):
            with st.spinner("Generating topics via Gemini..."):
                try:
                    st.session_state.topics = generate_topics()
                except Exception as e:
                    st.error(f"Failed to generate topics: {e}")

    with col2:
        if st.session_state.topics:
            topic_choice = st.radio("Select a generated topic:", ["-- Select --"] + st.session_state.topics)
            if topic_choice != "-- Select --":
                st.session_state.selected_topic = topic_choice

    # Custom Topic Input
    st.markdown("**OR** Provide a Custom Topic:")
    custom_topic = st.text_input("Enter a specific scenario (e.g., 'Asking for directions in Berlin'):", value="")
    if custom_topic:
        st.session_state.selected_topic = custom_topic

    if st.session_state.selected_topic:
        st.success(f"Selected Topic: **{st.session_state.selected_topic}**")

    st.divider()

    st.markdown("**Number of Conversations:**")
    num_conversations = st.slider("Select how many conversations you want in the video (default 1):", min_value=1, max_value=20, value=1)

    st.markdown("**Sentences per Conversation:**")
    sentences_range = st.slider(
        "Select the required range of sentences per conversation:",
        min_value=10,
        max_value=100,
        value=(50, 70)
    )

    # Generation Trigger
    if st.session_state.selected_topic:
        if st.button("🚀 Generate Video Pipeline", type="primary"):
            st.session_state.video_rendered = False
            
            # Use columns for progress tracking
            progress_container = st.container()
            with progress_container:
                # 1. Content Generation
                with st.spinner("📝 Generating Dialogue and Metadata (Gemini 3 Flash Preview)..."):
                    content = generate_video_content(
                        st.session_state.selected_topic, 
                        num_conversations=num_conversations,
                        min_sentences=sentences_range[0],
                        max_sentences=sentences_range[1]
                    )
                    st.session_state.video_metadata = {
                        "title": content.video_title,
                        "description": content.video_description,
                        "conversations": content.conversations
                    }
                    st.success("✅ Content Generated!")
                
                # 2. Image Generation
                with st.spinner("🖼️ Generating Anime Backgrounds (Replicate)..."):
                    bg_paths = []
                    for conv in content.conversations:
                        # Use the LLM-generated image prompt which explicitly forbids text
                        path = generate_background_image(conv.image_prompt, f"{content.video_title}_{conv.title}")
                        bg_paths.append(path)
                    st.success("✅ Background Images Generated!")
                
                # 3. Audio Generation
                with st.spinner("🎙️ Generating Dialogue Audio (Gemini 2.5 Flash Preview TTS)..."):
                    audio_data = generate_audio_for_conversations(content.conversations, content.video_title)
                    for i, item in enumerate(audio_data):
                        item["bg_path"] = bg_paths[i]
                    st.success("✅ Dialogue Audio Generated!")
                
                # 4. Video Compositing
                with st.spinner("🎬 Compositing Video with Speech Bubbles (MoviePy)..."):
                    final_mp4 = render_final_video(audio_data, content.video_title)
                    st.session_state.final_video_path = final_mp4
                    st.session_state.video_rendered = True
                    st.success("✅ Video Rendered Successfully!")

    # Final Output Dashboard
    if st.session_state.video_rendered and st.session_state.final_video_path:
        st.divider()
        st.header("🎉 Final Output Dashboard")

        # Layout for Video and Text
        vid_col, text_col = st.columns([1, 1])

        with vid_col:
            # Streamlit native video player
            st.video(st.session_state.final_video_path)
            
            # Download Button
            with open(st.session_state.final_video_path, "rb") as file:
                btn = st.download_button(
                    label="⬇️ Download Full MP4",
                    data=file,
                    file_name=os.path.basename(st.session_state.final_video_path),
                    mime="video/mp4"
                )

        with text_col:
            st.subheader("YouTube Details")
            st.text_input("YouTube Title", value=st.session_state.video_metadata.get("title", ""))
            st.text_area("YouTube Description", value=st.session_state.video_metadata.get("description", ""), height=150)
            
            with st.expander("Show Generated Dialogue"):
                for conv_idx, conv in enumerate(st.session_state.video_metadata.get("conversations", [])):
                    st.markdown(f"### {conv.title}")
                    for idx, line in enumerate(conv.dialogue):
                        st.markdown(f"**[{line.speaker.upper()}]** {line.text}")
                        st.markdown(f"*(Translation: {line.translation})*")
                    st.divider()

if __name__ == "__main__":
    main()

