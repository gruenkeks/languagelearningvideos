import os
import streamlit as st
import base64
import atexit
import shutil

from src.config import validate_config, OUTPUT_DIR, FINAL_VIDEO_DIR
from src.llm import generate_topics, generate_video_content, generate_video_outline
from src.image import generate_background_image
from src.tts import generate_audio_for_conversations
from src.video import render_final_video
from src.thumbnail import create_thumbnail
from src.upload import upload_video_package

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
    if "final_video_paths" not in st.session_state:
        st.session_state.final_video_paths = {}
    if "final_thumbnail_paths" not in st.session_state:
        st.session_state.final_thumbnail_paths = {}
    if "video_metadata" not in st.session_state:
        st.session_state.video_metadata = {}
    if "video_costs" not in st.session_state:
        st.session_state.video_costs = {}

    st.divider()
    st.header("🤖 Autopilot Mode")
    st.markdown("Let the AI choose a broad topic and conversation count, then click confirm to run.")
    
    col_auto1, col_auto2 = st.columns([1, 2])
    with col_auto1:
        if st.button("✨ Suggest Autopilot Plan", type="primary"):
            with st.spinner("Finding a fresh, broad topic..."):
                try:
                    import random
                    from src.history import get_history_context
                    from src.llm import generate_topics
                    history_context = get_history_context("German")
                    topics = generate_topics(count=1, history_context=history_context)
                    if topics:
                        st.session_state.autopilot_topic = topics[0]
                        st.session_state.autopilot_convos = random.randint(7, 12)
                        st.session_state.autopilot_ready = True
                except Exception as e:
                    st.error(f"Autopilot failed: {e}")

    with col_auto2:
        if st.session_state.get("autopilot_ready", False):
            st.info(f"**Proposed Topic:** {st.session_state.autopilot_topic} | **Conversations:** {st.session_state.autopilot_convos}")
            if st.button("🚀 Confirm & Run Autopilot"):
                st.session_state.selected_topic = st.session_state.autopilot_topic
                st.session_state.num_convos_slider = st.session_state.autopilot_convos
                st.session_state.sentences_range_slider = (35, 65)
                st.session_state.trigger_pipeline = True
                st.rerun()

    st.divider()

    st.header("Step 1: Choose a Topic")

    # Topic Generation
    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("🔄 Generate Fresh Topics"):
            with st.spinner("Generating topics via Gemini..."):
                try:
                    from src.history import get_history_context
                    history_context = get_history_context("German")
                    st.session_state.topics = generate_topics(history_context=history_context)
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

    st.markdown("**Target Languages:**")
    available_languages = ["German", "French", "Spanish", "Italian"]
    selected_languages = st.multiselect(
        "Select languages to generate videos for (default all):", 
        available_languages, 
        default=available_languages
    )

    st.divider()

    st.markdown("**Number of Conversations:**")
    if "num_convos_slider" not in st.session_state:
        st.session_state.num_convos_slider = 7
    num_conversations = st.slider("Select how many conversations you want in the video:", min_value=1, max_value=20, key="num_convos_slider")

    st.markdown("**Sentences per Conversation:**")
    if "sentences_range_slider" not in st.session_state:
        st.session_state.sentences_range_slider = (35, 65)
    sentences_range = st.slider(
        "Select the required range of sentences per conversation:",
        min_value=10,
        max_value=100,
        key="sentences_range_slider"
    )

    # Generation Trigger
    run_pipeline = False
    if st.session_state.selected_topic and selected_languages:
        manual_trigger = st.button("🚀 Generate Video Pipeline", type="primary")
        auto_trigger = st.session_state.get("trigger_pipeline", False)
        
        if manual_trigger or auto_trigger:
            if auto_trigger:
                st.session_state.trigger_pipeline = False  # Reset flag
            run_pipeline = True

    if run_pipeline:
            st.session_state.video_rendered = False
            st.session_state.final_video_paths = {}
            st.session_state.final_thumbnail_paths = {}
            st.session_state.video_metadata = {}
            st.session_state.video_costs = {}
            
            # Clean up OUTPUT_DIR to remove previous files before starting a new run
            try:
                for filename in os.listdir(OUTPUT_DIR):
                    file_path = os.path.join(OUTPUT_DIR, filename)
                    if os.path.isfile(file_path):
                        os.unlink(file_path)
            except Exception as e:
                pass
            
            # Use columns for progress tracking
            progress_container = st.container()
            with progress_container:
                # 0. Generate Outline
                with st.spinner("📝 Generating Video Outline..."):
                    from src.history import get_history_context
                    history_context = get_history_context()
                    outline, outline_usage = generate_video_outline(
                        st.session_state.selected_topic, 
                        num_conversations=num_conversations,
                        history_context=history_context
                    )
                    outline_cost = (outline_usage["prompt_tokens"] / 1_000_000 * 0.50) + (outline_usage["candidates_tokens"] / 1_000_000 * 3.0)
                
                shared_bg_paths = None
                shared_image_cost = 0.0
                
                for lang in selected_languages:
                    st.markdown(f"### Generating {lang} Video")
                    
                    lang_cost_details = {
                        "llm": outline_cost / len(selected_languages), 
                        "tts": 0.0, 
                        "image": 0.0, 
                        "total": 0.0
                    }

                    # 1. Content Generation
                    with st.spinner(f"📝 Generating {lang} Dialogue and Metadata (Gemini 3 Flash Preview)..."):
                        content, llm_usage = generate_video_content(
                            st.session_state.selected_topic,
                            language=lang,
                            num_conversations=num_conversations,
                            min_sentences=sentences_range[0],
                            max_sentences=sentences_range[1],
                            outline=outline
                        )
                        st.session_state.video_metadata[lang] = {
                            "title": content.video_title,
                            "description": content.video_description,
                            "conversations": content.conversations
                        }
                        llm_cost = (llm_usage["prompt_tokens"] / 1_000_000 * 0.50) + (llm_usage["candidates_tokens"] / 1_000_000 * 3.0)
                        lang_cost_details["llm"] += llm_cost
                        st.success(f"✅ {lang} Content Generated! (Cost: ${llm_cost:.4f})")
                    
                    # 2. Image Generation
                    if shared_bg_paths is None:
                        with st.spinner("🖼️ Generating Anime Backgrounds (Replicate)..."):
                            shared_bg_paths = []
                            for conv in content.conversations:
                                # Use the LLM-generated image prompt which explicitly forbids text
                                path = generate_background_image(conv.image_prompt, f"{content.video_title}_{conv.title}")
                                shared_bg_paths.append(path)
                                # Target resolution 1: $5 per 1000 megapixels => 0.005 per MP
                                # Image is 1024x576 = 589824 pixels
                                img_cost = (1024 * 576 / 1_000_000) * 0.005
                                shared_image_cost += img_cost
                            st.success(f"✅ Background Images Generated! (Cost: ${shared_image_cost:.4f})")
                    else:
                        st.info(f"⏭️ Reusing Background Images for {lang}.")
                    
                    lang_cost_details["image"] += shared_image_cost / len(selected_languages)
                    
                    # 3. Audio Generation
                    with st.spinner(f"🎙️ Generating {lang} Dialogue Audio (Gemini 2.5 Flash Preview TTS)..."):
                        audio_data, tts_usage = generate_audio_for_conversations(content.conversations, f"{content.video_title}_{lang}")
                        for i, item in enumerate(audio_data):
                            item["bg_path"] = shared_bg_paths[i]
                            
                        tts_cost = (tts_usage["prompt_tokens"] / 1_000_000 * 0.50) + (tts_usage["candidates_tokens"] / 1_000_000 * 10.0)
                        lang_cost_details["tts"] += tts_cost
                        st.success(f"✅ {lang} Dialogue Audio Generated! (Cost: ${tts_cost:.4f})")
                    
                    # 4. Video Compositing
                    with st.spinner(f"🎬 Compositing {lang} Video with Speech Bubbles (MoviePy/FFmpeg)..."):
                        final_mp4 = render_final_video(audio_data, f"{content.video_title}_{lang}")
                        st.session_state.final_video_paths[lang] = final_mp4
                        
                    # 4.5 Generate Final YouTube Metadata
                    with st.spinner(f"📝 Generating Final YouTube Metadata for {lang}..."):
                        from src.video import get_video_duration
                        from src.llm import generate_final_metadata
                        from src.history import get_history_context
                        
                        duration_sec = get_video_duration(final_mp4)
                        minutes = duration_sec / 60
                        if minutes < 1:
                            duration_str = "Under 1 minute"
                        elif minutes >= 57.5:
                            duration_str = f"{round(minutes / 60)} hour" + ("s" if round(minutes / 60) > 1 else "")
                        else:
                            rounded_minutes = max(1, 5 * round(minutes / 5))
                            duration_str = f"{rounded_minutes} minutes"
                            
                        final_meta, meta_usage = generate_final_metadata(
                            topic=st.session_state.selected_topic,
                            language=lang,
                            duration_str=duration_str,
                            num_conversations=num_conversations,
                            history_context=get_history_context(lang)
                        )
                        st.session_state.video_metadata[lang]["title"] = final_meta.title
                        st.session_state.video_metadata[lang]["description"] = final_meta.description
                        
                        meta_cost = (meta_usage["prompt_tokens"] / 1_000_000 * 0.50) + (meta_usage["candidates_tokens"] / 1_000_000 * 3.0)
                        lang_cost_details["llm"] += meta_cost
                        
                    # 5. Thumbnail Generation
                    with st.spinner(f"🖼️ Generating {lang} Thumbnail..."):
                        thumb_path, thumb_usage = create_thumbnail(
                            st.session_state.selected_topic, 
                            lang, 
                            shared_bg_paths, 
                            content
                        )
                        if thumb_path:
                            st.session_state.final_thumbnail_paths[lang] = thumb_path
                            thumb_cost = (thumb_usage["prompt_tokens"] / 1_000_000 * 0.50) + (thumb_usage["candidates_tokens"] / 1_000_000 * 3.0)
                            lang_cost_details["llm"] += thumb_cost
                        
                        lang_cost_details["total"] = lang_cost_details["llm"] + lang_cost_details["tts"] + lang_cost_details["image"]
                        st.session_state.video_costs[lang] = lang_cost_details
                        st.success(f"✅ {lang} Video & Thumbnail Rendered! (Total Cost: ${lang_cost_details['total']:.4f})")
                        
                st.session_state.video_rendered = True

    # Final Output Dashboard
    if st.session_state.video_rendered and st.session_state.final_video_paths:
        st.divider()
        st.header("🎉 Final Output Dashboard")

        # --- Upload All Button ---
        if st.button("🚀 Upload ALL languages to Hetzner", type="primary"):
            with st.spinner("Uploading all packages to Hetzner Server via SFTP..."):
                all_success = True
                for l, p in st.session_state.final_video_paths.items():
                    t_path = st.session_state.final_thumbnail_paths.get(l)
                    m_payload = {
                        "title": st.session_state.video_metadata[l].get("title", ""),
                        "description": st.session_state.video_metadata[l].get("description", "")
                    }
                    try:
                        # Use Streamlit session state keys which accurately track user edits to text inputs
                        title = st.session_state.get(f"title_{l}", st.session_state.video_metadata[l].get("title", ""))
                        description = st.session_state.get(f"desc_{l}", st.session_state.video_metadata[l].get("description", ""))
                        
                        # Fallback if somehow it's totally empty
                        if not title or title.strip() == "":
                            title = f"Language Learning Video - {l}"
                            
                        m_payload = {
                            "title": title[:100], # YouTube API limits title to 100 chars
                            "description": description
                        }
                        res = upload_video_package(p, t_path, l, m_payload)
                        st.success(f"✅ {l} uploaded successfully to Hetzner Queue!")
                        
                        from src.history import save_history
                        save_history(title, st.session_state.video_metadata[l].get("conversations", []), l)
                        
                        # Clean up local files
                        if os.path.exists(p):
                            os.remove(p)
                        if t_path and os.path.exists(t_path):
                            os.remove(t_path)
                    except Exception as e:
                        all_success = False
                        st.error(f"❌ Hetzner upload failed for {l}: {str(e)}")
                
                if all_success:
                    st.success("🎉 All languages successfully uploaded to Hetzner!")
                st.info("🧹 Local videos and thumbnails deleted to save space.")

        for lang, path in st.session_state.final_video_paths.items():
            st.subheader(f"Video: {lang}")
            
            # Show cost analysis
            cost = st.session_state.video_costs[lang]
            st.info(f"**Cost Analysis for {lang}:** LLM: ${cost['llm']:.4f} | TTS: ${cost['tts']:.4f} | Images: ${cost['image']:.4f} | **Total: ${cost['total']:.4f}**")

            # Layout for Video and Text
            vid_col, text_col = st.columns([1, 1])

            with vid_col:
                # Streamlit native video player
                if os.path.exists(path):
                    st.video(path)
                    
                    # Download Video Button
                    with open(path, "rb") as file:
                        btn = st.download_button(
                            label=f"⬇️ Download {lang} Full MP4",
                            data=file,
                            file_name=os.path.basename(path),
                            mime="video/mp4",
                            key=f"download_{lang}"
                        )
                else:
                    st.info(f"The {lang} video has been uploaded and removed from the local disk to save space.")
                
                # Show Thumbnail if available
                thumb_path = st.session_state.final_thumbnail_paths.get(lang)
                if thumb_path and os.path.exists(thumb_path):
                    st.image(thumb_path, caption=f"{lang} Thumbnail")
                    with open(thumb_path, "rb") as t_file:
                        st.download_button(
                            label=f"⬇️ Download {lang} Thumbnail",
                            data=t_file,
                            file_name=os.path.basename(thumb_path),
                            mime="image/jpeg",
                            key=f"download_thumb_{lang}"
                        )
                elif thumb_path:
                    st.info(f"The {lang} thumbnail has been uploaded and removed locally.")
                
                st.divider()
                if st.button(f"☁️ Upload {lang} to Hetzner Queue", key=f"upload_hetzner_{lang}"):
                    with st.spinner(f"Uploading {lang} package to Hetzner Server via SFTP..."):
                        try:
                            # Use Streamlit session state keys which accurately track user edits to text inputs
                            title = st.session_state.get(f"title_{lang}", st.session_state.video_metadata[lang].get("title", ""))
                            description = st.session_state.get(f"desc_{lang}", st.session_state.video_metadata[lang].get("description", ""))
                            
                            # Fallback if somehow it's totally empty
                            if not title or title.strip() == "":
                                title = f"Language Learning Video - {lang}"
                            
                            metadata_payload = {
                                "title": title[:100], # YouTube API limits title to 100 chars
                                "description": description
                            }
                            
                            res = upload_video_package(path, thumb_path, lang, metadata_payload)
                            st.success("✅ Uploaded successfully to Hetzner Queue!")
                            
                            from src.history import save_history
                            save_history(title, st.session_state.video_metadata[lang].get("conversations", []), lang)
                            
                            # Clean up local files
                            if os.path.exists(path):
                                os.remove(path)
                            if thumb_path and os.path.exists(thumb_path):
                                os.remove(thumb_path)
                            st.info("🧹 Local video and thumbnail deleted to save space.")
                        except Exception as e:
                            st.error(f"❌ Hetzner upload failed: {str(e)}")

            with text_col:
                st.subheader("YouTube Details")
                metadata = st.session_state.video_metadata[lang]
                st.text_input(f"YouTube Title ({lang})", value=metadata.get("title", ""), key=f"title_{lang}")
                st.text_area(f"YouTube Description ({lang})", value=metadata.get("description", ""), height=150, key=f"desc_{lang}")
                
                with st.expander(f"Show Generated Dialogue ({lang})"):
                    for conv_idx, conv in enumerate(metadata.get("conversations", [])):
                        st.markdown(f"### {conv.title}")
                        for idx, line in enumerate(conv.dialogue):
                            st.markdown(f"**[{line.speaker.upper()}]** {line.text}")
                            st.markdown(f"*(Translation: {line.translation})*")
                        st.divider()
            st.divider()

if __name__ == "__main__":
    main()
