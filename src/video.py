import os
import textwrap
import subprocess
from typing import List, Dict

import whisper
from PIL import Image, ImageDraw, ImageFont
import numpy as np

from src.config import OUTPUT_DIR, FINAL_VIDEO_DIR

# Global config for Speech Bubbles
BUBBLE_COLOR = (255, 255, 255, 230)  # White with slight transparency
REPEATED_BUBBLE_COLOR = (193, 154, 107, 230)  # Light brown for repeated turtle
TEXT_COLOR = (0, 0, 0)
PADDING = 20
FONT_SIZE = 36
MAX_CHARS_PER_LINE = 35

# Load the base Whisper model for better alignment precision
print("Loading Whisper base model for audio alignment...")
whisper_model = whisper.load_model("base")

def get_exact_sentence_timestamps(audio_path: str, known_sentences: List[str]) -> List[Dict]:
    """
    Uses Whisper to find the exact start and end times for a known list of sentences.
    """
    import difflib
    
    # 1. Ask whisper for word-level timestamps
    result = whisper_model.transcribe(audio_path, word_timestamps=True)
    
    whisper_words = []
    for segment in result.get("segments", []):
        for word in segment.get("words", []):
            # Clean punctuation and whitespace for matching
            clean_text = word["word"].strip().lower()
            clean_text = ''.join(c for c in clean_text if c.isalnum())
            if clean_text:
                whisper_words.append({
                    "text": clean_text,
                    "start": word["start"],
                    "end": word["end"]
                })

    sentence_timestamps = []
    
    # Flatten known sentences into words with their sentence index
    target_words_with_idx = []
    for i, sentence in enumerate(known_sentences):
        clean_sentence = ''.join(c for c in sentence.lower() if c.isalnum() or c.isspace())
        words = clean_sentence.split()
        for w in words:
            target_words_with_idx.append((i, w))

    if not target_words_with_idx or not whisper_words:
        # Fallback if text is empty or whisper failed completely
        current_time = 0.0
        for sentence in known_sentences:
            sentence_timestamps.append({
                "text": sentence,
                "start": current_time,
                "end": current_time + 2.0,
                "duration": 2.0
            })
            current_time += 2.0
        return sentence_timestamps

    target_word_texts = [w for _, w in target_words_with_idx]
    whisper_word_texts = [w["text"] for w in whisper_words]
    
    matcher = difflib.SequenceMatcher(None, target_word_texts, whisper_word_texts)
    sentence_to_whisper_indices = {i: [] for i in range(len(known_sentences))}

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            for k in range(j2 - j1):
                sent_idx = target_words_with_idx[i1 + k][0]
                sentence_to_whisper_indices[sent_idx].append(j1 + k)
        elif tag == 'replace':
            for k in range(j2 - j1):
                target_k = int(k * (i2 - i1) / (j2 - j1))
                sent_idx = target_words_with_idx[i1 + target_k][0]
                sentence_to_whisper_indices[sent_idx].append(j1 + k)
        elif tag == 'insert':
            # Whisper has extra words. Assign them to the closest sentence.
            sent_idx = target_words_with_idx[i1][0] if i1 < len(target_words_with_idx) else target_words_with_idx[-1][0]
            for k in range(j2 - j1):
                sentence_to_whisper_indices[sent_idx].append(j1 + k)

    for i, sentence in enumerate(known_sentences):
        indices = sentence_to_whisper_indices[i]
        
        if not indices:
            last_end = sentence_timestamps[-1]["end"] if sentence_timestamps else 0.0
            sentence_timestamps.append({
                "text": sentence,
                "start": last_end,
                "end": last_end + 1.0,
                "duration": 1.0
            })
            continue
            
        start_time = whisper_words[indices[0]]["start"]
        end_time = whisper_words[indices[-1]]["end"]
        
        # Removed arbitrary padding here because it caused audio overlapping into the next sentence
        
        # Ensure times don't go backwards due to misalignment
        if sentence_timestamps:
            prev_start = sentence_timestamps[-1]["start"]
            if start_time < prev_start:
                start_time = prev_start
            if end_time <= start_time:
                end_time = start_time + 0.5
                
        duration = end_time - start_time
        
        sentence_timestamps.append({
            "text": sentence,
            "start": start_time,
            "end": end_time,
            "duration": duration
        })
        
    # FIX FOR OVERLAPPING TEXT AND AUDIO:
    # Ensure no bubble stays on screen when the next one starts, and that audio slices
    # capture trailing consonants without bleeding into the next sentence.
    for i in range(len(sentence_timestamps) - 1):
        current_end = sentence_timestamps[i].get("end", 0)
        next_start = sentence_timestamps[i+1].get("start", 0)
        
        # If this bubble ends AFTER the next one starts, they overlap! Split the difference.
        if current_end > next_start:
            midpoint = (current_end + next_start) / 2.0
            sentence_timestamps[i]["end"] = midpoint
            sentence_timestamps[i+1]["start"] = midpoint
        else:
            # If there's a gap between sentences, we can safely expand outward a tiny bit 
            # to capture leading/trailing consonants, but never overlap!
            gap = next_start - current_end
            padding = min(0.1, gap / 2.0)  # Max 100ms padding per side
            sentence_timestamps[i]["end"] += padding
            sentence_timestamps[i+1]["start"] -= padding
            
        sentence_timestamps[i]["duration"] = sentence_timestamps[i]["end"] - sentence_timestamps[i]["start"]
            
    # Extra fix to ensure there are no tiny negative gaps which mess up FFmpeg concat
    for i in range(len(sentence_timestamps)):
        # Re-calculate duration for the last item as well
        if i == len(sentence_timestamps) - 1:
            sentence_timestamps[i]["duration"] = sentence_timestamps[i]["end"] - sentence_timestamps[i]["start"]
            
        # Make absolutely sure duration is positive
        if sentence_timestamps[i]["duration"] < 0:
            sentence_timestamps[i]["duration"] = 0.1
            sentence_timestamps[i]["end"] = sentence_timestamps[i]["start"] + 0.1

    return sentence_timestamps

def draw_speech_bubble(text: str, speaker: str, width: int = 1920, height: int = 1080, is_repeated: bool = False) -> np.ndarray:
    """
    Creates an image frame with a transparent background containing
    a speech bubble pointing to the left or right speaker.
    """
    # Create a blank transparent image
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Try to load a generic TTF font; fallback to default
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", FONT_SIZE)
    except IOError:
        try:
            font = ImageFont.truetype("arial.ttf", FONT_SIZE)
        except IOError:
            font = ImageFont.load_default(size=FONT_SIZE)

    # Wrap the text
    wrapped_text = textwrap.fill(text, width=MAX_CHARS_PER_LINE)
    
    # Calculate bounding box of the text
    left, top, right, bottom = draw.textbbox((0, 0), wrapped_text, font=font)
    text_w = right - left
    text_h = bottom - top

    bubble_w = text_w + (PADDING * 2)
    bubble_h = text_h + (PADDING * 2)

    # Calculate position based on speaker
    # Left speaker bubble is placed on the left side (x=100)
    # Right speaker bubble is placed on the right side (x=width - bubble_w - 100)
    y_pos = height // 3  # Place in the top/middle third
    
    if speaker == "left":
        x_pos = 100
    else:
        x_pos = width - bubble_w - 100

    # Draw rounded rectangle for the bubble
    shape = [(x_pos, y_pos), (x_pos + bubble_w, y_pos + bubble_h)]
    bubble_color = REPEATED_BUBBLE_COLOR if is_repeated else BUBBLE_COLOR
    draw.rounded_rectangle(shape, radius=30, fill=bubble_color)

    # Draw Text
    text_x = x_pos + PADDING
    text_y = y_pos + PADDING
    draw.text((text_x, text_y), wrapped_text, fill=TEXT_COLOR, font=font)
    
    # Draw Turtle if repeated
    if is_repeated:
        try:
            turtle_img = Image.open("turtle.png").convert("RGBA")
            # Resize turtle to be small (e.g. 60x60)
            turtle_size = 60
            turtle_img = turtle_img.resize((turtle_size, turtle_size), Image.Resampling.LANCZOS)
            
            # Place at the top left of the speech bubble
            # We want it to overlap the corner slightly
            turtle_x = x_pos - (turtle_size // 2)
            turtle_y = y_pos - (turtle_size // 2)
            
            img.paste(turtle_img, (turtle_x, turtle_y), turtle_img)
        except Exception as e:
            print(f"Could not load turtle.png: {e}")

    return np.array(img)

def render_final_video(conversation_data: List[Dict], video_title: str) -> str:
    """
    Uses FFmpeg's concat demuxer to instantly assemble static background images and 
    speech bubbles into a final MP4 video, completely bypassing frame-by-frame rendering.
    """
    import concurrent.futures
    import threading

    safe_title = "".join(x for x in video_title if x.isalnum() or x in " -_").strip().replace(" ", "_").lower()
    output_path = os.path.join(FINAL_VIDEO_DIR, f"{safe_title}.mp4")

    temp_videos = [None] * len(conversation_data)
    files_to_cleanup = []
    
    # Lock for Whisper to avoid thread-safety issues with PyTorch
    whisper_lock = threading.Lock()

    def process_conversation(conv_idx, item):
        local_cleanup = []
        audio_path = os.path.abspath(item["audio_path"])
        dialogue = item["dialogue"]
        bg_image_path = os.path.abspath(item["bg_path"])
        
        # Add original inputs to cleanup
        local_cleanup.append(audio_path)
        local_cleanup.append(bg_image_path)

        # Load Background Image and Audio Duration
        bg_img = Image.open(bg_image_path).convert("RGBA")
        width, height = bg_img.size
        
        # Get exact sentence timestamps using Whisper
        sentences_only = [line.text for line in dialogue]
        with whisper_lock:
            timestamps = get_exact_sentence_timestamps(audio_path, sentences_only)

        import copy
        # REBUILD AUDIO: Repeat each sentence with pauses
        from pydub import AudioSegment
        
        orig_audio = AudioSegment.from_file(audio_path)
        
        # AudioSegment lengths can sometimes be slightly different than mathematical length.
        orig_audio_len_ms = len(orig_audio)
        
        silence_1s = AudioSegment.silent(duration=1000)
        silence_2s = AudioSegment.silent(duration=2000)
        
        new_audio = AudioSegment.empty()
        new_timestamps = []
        new_dialogue = []
        is_repeated_flags = []
        current_new_time = 0.0
        
        for i, line in enumerate(dialogue):
            ts = timestamps[i]
            
            # Use exact timestamps from the refined get_exact_sentence_timestamps
            start_ms = int(ts.get("start", 0) * 1000)
            end_ms = int(ts.get("end", 0) * 1000)
            
            # Fallback if whisper failed to get a reasonable duration
            if end_ms <= start_ms:
                end_ms = start_ms + 1000
                
            # Make sure we don't slice past the end of the audio!
            if end_ms > orig_audio_len_ms:
                end_ms = orig_audio_len_ms
                
            sentence_audio = orig_audio[start_ms:end_ms]
            
            # Get the exact duration of the sliced clip
            duration_s = len(sentence_audio) / 1000.0
            
            # 1. First play of the sentence
            new_timestamps.append({
                "start": current_new_time,
                "end": current_new_time + duration_s,
                "duration": duration_s
            })
            new_dialogue.append(copy.deepcopy(line)) # Need to use a full copy to prevent reference issues
            is_repeated_flags.append(False)
            new_audio += sentence_audio
            current_new_time += duration_s
            
            # Pause
            new_audio += silence_1s
            current_new_time += 1.0
            
            # 2. Repeated play of the sentence (30% slower)
            slow_speed = 0.70 # 30% slower
            
            # Use FFmpeg atempo filter to slow down audio without changing pitch
            temp_in = os.path.join(OUTPUT_DIR, f"temp_audio_in_{conv_idx}_{i}.wav")
            temp_out = os.path.join(OUTPUT_DIR, f"temp_audio_out_{conv_idx}_{i}.wav")
            
            sentence_audio.export(temp_in, format="wav")
            
            # atempo filter keeps the pitch while changing speed
            ffmpeg_atempo_cmd = [
                "ffmpeg", "-y",
                "-i", temp_in,
                "-filter:a", f"atempo={slow_speed}",
                temp_out
            ]
            subprocess.run(ffmpeg_atempo_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            slow_audio = AudioSegment.from_file(temp_out)
            
            # Cleanup temp files
            try:
                os.remove(temp_in)
                os.remove(temp_out)
            except OSError:
                pass
                
            slow_duration_s = len(slow_audio) / 1000.0
            
            new_timestamps.append({
                "start": current_new_time,
                "end": current_new_time + slow_duration_s,
                "duration": slow_duration_s
            })
            new_dialogue.append(copy.deepcopy(line))
            is_repeated_flags.append(True)
            new_audio += slow_audio
            current_new_time += slow_duration_s
            
            # Pause before next sentence
            new_audio += silence_2s
            current_new_time += 2.0
            
        # Add a tiny bit of trailing silence to make sure we don't chop the very end of the final word
        trailing_silence = AudioSegment.silent(duration=500)
        new_audio += trailing_silence
        current_new_time += 0.5
            
        # Export the new structured audio
        spaced_audio_path = audio_path.replace(".wav", f"_spaced_{conv_idx}.wav")
        new_audio.export(spaced_audio_path, format="wav")
        local_cleanup.append(spaced_audio_path)
        
        # Override variables to use our new spaced timeline
        audio_path = spaced_audio_path
        total_duration = current_new_time
        # Update the original dict item so other functions see the new dialogue
        item["dialogue"] = new_dialogue 
        dialogue = new_dialogue
        timestamps = new_timestamps

        concat_lines = []
        current_time = 0.0

        # Now, build the video based on the NEW dialogue list and NEW timestamps
        for i, line in enumerate(dialogue):
            is_repeated = is_repeated_flags[i]
            ts = timestamps[i]
            start_time = ts.get("start", 0)
            end_time = ts.get("end", 0)
            
            # 1. Gap before the bubble (just the background image)
            if start_time > current_time:
                # Add a tiny 0.001 buffer to avoid floating point precision making gap negative
                gap_duration = max(0.001, start_time - current_time)
                concat_lines.append(f"file '{bg_image_path}'")
                concat_lines.append(f"duration {gap_duration:.3f}")

            # 2. The bubble frame
            bubble_duration = max(0.1, end_time - start_time)
            if bubble_duration > 0:
                # Draw the bubble
                bubble_array = draw_speech_bubble(line.text, line.speaker, width=width, height=height, is_repeated=is_repeated)
                bubble_img = Image.fromarray(bubble_array, "RGBA")
                
                # Instantly composite the bubble onto the background using PIL (milliseconds)
                frame_img = Image.alpha_composite(bg_img, bubble_img)
                # Ensure the frame filename is unique per repeated line
                frame_path = os.path.abspath(os.path.join(OUTPUT_DIR, f"temp_frame_{conv_idx}_{i}.png"))
                
                # Save the static frame to disk
                frame_img.convert("RGB").save(frame_path)
                local_cleanup.append(frame_path)

                concat_lines.append(f"file '{frame_path}'")
                concat_lines.append(f"duration {bubble_duration:.3f}")

            current_time = end_time

        # 3. Gap after the last bubble until the audio ends
        # Add a tiny buffer (0.1s) to prevent negative durations due to floating point math
        if current_time < total_duration - 0.001:
            gap_duration = max(0.001, total_duration - current_time)
            concat_lines.append(f"file '{bg_image_path}'")
            concat_lines.append(f"duration {gap_duration:.3f}")

        # FFmpeg quirk: The last image in a concat file must be specified twice
        concat_lines.append(f"file '{bg_image_path}'")

        # Write the FFmpeg concat instructions to a text file
        concat_file_path = os.path.join(OUTPUT_DIR, f"concat_{conv_idx}.txt")
        with open(concat_file_path, "w") as f:
            f.write("\n".join(concat_lines))
        local_cleanup.append(concat_file_path)

        # 4. Run FFmpeg to assemble this conversation
        conv_output = os.path.join(OUTPUT_DIR, f"temp_conv_{conv_idx}.mp4")
        
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_file_path,
            "-i", audio_path,
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            conv_output
        ]
        
        print(f"Assembling conversation {conv_idx+1} via FFmpeg...")
        subprocess.run(ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        local_cleanup.append(conv_output)
        
        return conv_idx, conv_output, local_cleanup

    # Process all conversations in parallel
    print("Processing conversation videos in parallel...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as executor:
        futures = {executor.submit(process_conversation, i, item): i for i, item in enumerate(conversation_data)}
        for future in concurrent.futures.as_completed(futures):
            idx, conv_output, local_cleanup = future.result()
            temp_videos[idx] = conv_output
            files_to_cleanup.extend(local_cleanup)

    # 5. Concatenate all the conversation videos together instantly
    final_concat_list = os.path.join(OUTPUT_DIR, "final_concat.txt")
    with open(final_concat_list, "w") as f:
        for vid in temp_videos:
            f.write(f"file '{os.path.abspath(vid)}'\n")
    files_to_cleanup.append(final_concat_list)

    concat_cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", final_concat_list,
        "-c", "copy", # Copy without re-encoding! Instant!
        output_path
    ]
    
    print("Concatenating final video...")
    subprocess.run(concat_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 6. Cleanup all temporary files
    for file in files_to_cleanup:
        try:
            os.remove(file)
        except OSError:
            pass
            
    # Extra safety: Clean the entire OUTPUT_DIR to ensure no temp files remain
    try:
        for filename in os.listdir(OUTPUT_DIR):
            file_path = os.path.join(OUTPUT_DIR, filename)
            if os.path.isfile(file_path):
                os.remove(file_path)
    except Exception as e:
        print(f"Error clearing output directory: {e}")

    return output_path
