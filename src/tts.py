import os
import time
import struct
import mimetypes
from typing import List, Dict
from google import genai
from google.genai import types

from src.config import GEMINI_API_KEY, OUTPUT_DIR
from src.llm import Conversation

client = genai.Client(api_key=GEMINI_API_KEY)

def parse_audio_mime_type(mime_type: str) -> dict[str, int | None]:
    """Parses bits per sample and rate from an audio MIME type string."""
    bits_per_sample = 16
    rate = 24000
    parts = mime_type.split(";")
    for param in parts:
        param = param.strip()
        if param.lower().startswith("rate="):
            try:
                rate = int(param.split("=", 1)[1])
            except (ValueError, IndexError):
                pass
        elif param.startswith("audio/L"):
            try:
                bits_per_sample = int(param.split("L", 1)[1])
            except (ValueError, IndexError):
                pass
    return {"bits_per_sample": bits_per_sample, "rate": rate}

def convert_to_wav(audio_data: bytes, mime_type: str) -> bytes:
    """Generates a WAV file header for the given audio data and parameters."""
    parameters = parse_audio_mime_type(mime_type)
    bits_per_sample = parameters["bits_per_sample"]
    sample_rate = parameters["rate"]
    num_channels = 1
    data_size = len(audio_data)
    bytes_per_sample = bits_per_sample // 8
    block_align = num_channels * bytes_per_sample
    byte_rate = sample_rate * block_align
    chunk_size = 36 + data_size

    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",          # ChunkID
        chunk_size,       # ChunkSize (total file size - 8 bytes)
        b"WAVE",          # Format
        b"fmt ",          # Subchunk1ID
        16,               # Subchunk1Size (16 for PCM)
        1,                # AudioFormat (1 for PCM)
        num_channels,     # NumChannels
        sample_rate,      # SampleRate
        byte_rate,        # ByteRate
        block_align,      # BlockAlign
        bits_per_sample,  # BitsPerSample
        b"data",          # Subchunk2ID
        data_size         # Subchunk2Size (size of audio data)
    )
    return header + audio_data

def generate_audio_for_conversations(conversations: List[Conversation], video_title: str) -> tuple[List[Dict], dict]:
    """
    Generates a single multi-speaker audio file for each conversation using Gemini 2.5 Flash TTS in parallel.
    Returns a list of dictionaries containing conversation metadata and the audio file path, 
    and a dict with token usage.
    """
    import concurrent.futures
    import time
    
    # Check if we are running inside Streamlit for progress updates
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        has_streamlit = get_script_run_ctx() is not None
    except ImportError:
        has_streamlit = False

    if has_streamlit and len(conversations) > 1:
        import streamlit as st
        st.info(f"Generating {len(conversations)} dialogue audio tracks in parallel...")
        progress_bar = st.progress(0)
        status_text = st.empty()

    safe_title = "".join(x for x in video_title if x.isalnum() or x in " -_").strip().replace(" ", "_").lower()
    audio_data = [None] * len(conversations)
    total_usage = {"prompt_tokens": 0, "candidates_tokens": 0}
    
    model = "gemini-2.5-flash-preview-tts"
    completed_count = 0

    def process_audio(idx_and_conv):
        import random
        index, conv = idx_and_conv
        
        # Add a small random jitter to avoid hitting exact same millisecond rate limits
        time.sleep(random.uniform(0.5, 2.5))
        
        # Format the prompt for the multi-speaker model
        prompt_text = "Read aloud in a warm, welcoming tone at a slow and deliberate pace for language learners.\n"
        for line in conv.dialogue:
            speaker_tag = "Speaker 1" if line.speaker == "left" else "Speaker 2"
            prompt_text += f"{speaker_tag}: {line.text}\n"

        contents = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=prompt_text)],
            ),
        ]

        print(f"Generating multi-speaker audio for conversation {index + 1}...")
        
        left_voice = "Aoede" if conv.left_gender == "female" else "Charon"
        right_voice = "Aoede" if conv.right_gender == "female" else "Charon"

        generate_content_config = types.GenerateContentConfig(
            temperature=1,
            response_modalities=["audio"],
            speech_config=types.SpeechConfig(
                multi_speaker_voice_config=types.MultiSpeakerVoiceConfig(
                    speaker_voice_configs=[
                        types.SpeakerVoiceConfig(
                            speaker="Speaker 1",
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=left_voice)
                            ),
                        ),
                        types.SpeakerVoiceConfig(
                            speaker="Speaker 2",
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=right_voice)
                            ),
                        ),
                    ]
                ),
            ),
        )
        
        all_pcm_data = bytearray()
        mime_type = "audio/L16;rate=24000" # default fallback
        usage = {"prompt_tokens": 0, "candidates_tokens": 0}
        
        # Add retries for the stream
        max_retries = 3
        retry_delay = 5.0
        success = False
        
        for attempt in range(max_retries):
            all_pcm_data.clear()
            try:
                for chunk in client.models.generate_content_stream(
                    model=model,
                    contents=contents,
                    config=generate_content_config,
                ):
                    if chunk.usage_metadata:
                        usage["prompt_tokens"] = chunk.usage_metadata.prompt_token_count if chunk.usage_metadata.prompt_token_count else usage["prompt_tokens"]
                        usage["candidates_tokens"] = chunk.usage_metadata.candidates_token_count if chunk.usage_metadata.candidates_token_count else usage["candidates_tokens"]
                    if chunk.parts is None:
                        continue
                    if chunk.parts[0].inline_data and chunk.parts[0].inline_data.data:
                        inline_data = chunk.parts[0].inline_data
                        all_pcm_data.extend(inline_data.data)
                        mime_type = inline_data.mime_type
                success = True
                break
            except Exception as e:
                print(f"Attempt {attempt + 1}/{max_retries} failed for audio {index}. Exception: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    raise
                    
        if not success or not all_pcm_data:
            raise ValueError(f"Failed to generate audio for conversation {index}")

        # Convert to WAV and save
        wav_data = convert_to_wav(bytes(all_pcm_data), mime_type)
        file_path = os.path.join(OUTPUT_DIR, f"{safe_title}_conv_{index:03d}.wav")
        
        with open(file_path, "wb") as f:
            f.write(wav_data)
            
        import subprocess
        slow_file_path = os.path.join(OUTPUT_DIR, f"{safe_title}_conv_{index:03d}_slow.wav")
        
        # Use FFmpeg to slow down the audio by ~15% (atempo=0.85)
        subprocess.run([
            "ffmpeg", "-y", "-i", file_path, 
            "-filter:a", "atempo=0.85", 
            slow_file_path
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # Overwrite the original file with the slowed-down version
        os.replace(slow_file_path, file_path)
            
        return index, {
            "title": conv.title,
            "dialogue": conv.dialogue,
            "audio_path": file_path
        }, usage

    # Execute concurrent API calls
    # Note: Audio generation is heavier, so we restrict it to 3 concurrent workers to be safe with rate limits
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(process_audio, (i, conv)): i for i, conv in enumerate(conversations)}
        
        for future in concurrent.futures.as_completed(futures):
            idx, result, usage = future.result()
            audio_data[idx] = result
            total_usage["prompt_tokens"] += usage["prompt_tokens"]
            total_usage["candidates_tokens"] += usage["candidates_tokens"]
            completed_count += 1
            
            if has_streamlit and len(conversations) > 1:
                status_text.text(f"Completed {completed_count}/{len(conversations)} audio tracks...")
                progress_bar.progress(completed_count / len(conversations))
                
    if has_streamlit and len(conversations) > 1:
        progress_bar.empty()
        status_text.empty()

    return audio_data, total_usage
