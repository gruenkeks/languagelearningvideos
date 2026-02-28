import os
import random
import textwrap
import math
import re
from typing import List, Tuple
from PIL import Image, ImageDraw, ImageFont
import numpy as np

from src.config import OUTPUT_DIR
from src.llm import generate_thumbnail_text, VideoContent

# Global config for Thumbnail Speech Bubbles
BUBBLE_COLOR = (255, 255, 255, 255)
TEXT_COLOR = (0, 0, 0)
PADDING = 30
FONT_SIZE = 60

def fix_punctuation(text: str) -> str:
    """Removes unwanted spaces before punctuation."""
    return re.sub(r'\s+([!?,.;:])', r'\1', text)

def draw_dynamic_speech_bubble(draw: ImageDraw.Draw, text: str, head_pos: Tuple[int, int], speaker: str, width: int, height: int):
    """
    Draws a large speech bubble with a tail pointing to the head_pos.
    """
    text = fix_punctuation(text)
    
    # Start with default font size and dynamically shrink if needed
    current_font_size = FONT_SIZE
    max_bubble_w = width // 2 - 40  # Maximum width to ensure no overlaps
    
    while current_font_size > 20:
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", current_font_size)
        except IOError:
            try:
                font = ImageFont.truetype("arial.ttf", current_font_size)
            except IOError:
                font = ImageFont.load_default()
                
        # Wrap text tighter if font is large, looser if font is small
        wrap_width = max(10, int(15 * (FONT_SIZE / current_font_size)))
        wrapped_text = textwrap.fill(text, width=wrap_width)
        
        left, top, right, bottom = draw.multiline_textbbox((0, 0), wrapped_text, font=font, align="center")
        text_w = right - left
        text_h = bottom - top
        
        bubble_w = text_w + (PADDING * 2)
        bubble_h = text_h + (PADDING * 2)
        
        if bubble_w <= max_bubble_w:
            break
            
        current_font_size -= 4

    # Set boundaries for the bubbles to prevent overlap and off-screen drawing
    margin = 30
    
    # Add randomness to placement to make it look dynamic and natural
    rand_x = random.randint(-60, 60)
    
    # Ensure bubble is a safe distance above the head so the tail is clearly visible
    # Tail length is 30, so let's guarantee at least 50-100 pixels of clearance between bubble bottom and head
    gap = random.randint(60, 110)
    
    if speaker == "left":
        max_x = width // 2 - 20 - bubble_w
        x_pos = max(margin, head_pos[0] - bubble_w // 2 + rand_x)
        if x_pos > max_x:
            x_pos = max_x
        # Try to place it above the head with a safe gap
        y_pos = max(margin, head_pos[1] - bubble_h - gap)
    else:
        min_x = width // 2 + 20
        x_pos = min(width - margin - bubble_w, head_pos[0] - bubble_w // 2 + rand_x)
        if x_pos < min_x:
            x_pos = min_x
        y_pos = max(margin, head_pos[1] - bubble_h - gap)

    # Fallback to prevent clipping
    x_pos = max(margin, min(x_pos, width - margin - bubble_w))
    y_pos = max(margin, min(y_pos, height - margin - bubble_h))

    # Calculate tail coordinates
    bubble_bottom_y = y_pos + bubble_h
    
    # We want the tail to originate from the bottom edge, reasonably close to the head horizontally
    tail_base_x = max(x_pos + 40, min(x_pos + bubble_w - 40, head_pos[0]))
    
    tail_width = 40
    p1 = (tail_base_x - tail_width // 2, bubble_bottom_y - 10)
    p2 = (tail_base_x + tail_width // 2, bubble_bottom_y - 10)
    
    # Calculate distance to head
    dx = head_pos[0] - tail_base_x
    dy = head_pos[1] - bubble_bottom_y
    
    tail_length = 30  # Fixed tail length so all triangles are exactly the same size
    
    # If the head is somehow ABOVE the bubble, adjust tail to point upwards from top edge
    if dy < 0:
        bubble_top_y = y_pos
        p1 = (tail_base_x - tail_width // 2, bubble_top_y + 10)
        p2 = (tail_base_x + tail_width // 2, bubble_top_y + 10)
        dy = head_pos[1] - bubble_top_y
        
        dist = math.hypot(dx, dy)
        norm_dx = dx / dist if dist > 0 else 0
        norm_dy = dy / dist if dist > 0 else -1
            
        tip_x = tail_base_x + norm_dx * tail_length
        tip_y = bubble_top_y + norm_dy * tail_length
    else:
        dist = math.hypot(dx, dy)
        norm_dx = dx / dist if dist > 0 else 0
        norm_dy = dy / dist if dist > 0 else 1
            
        tip_x = tail_base_x + norm_dx * tail_length
        tip_y = bubble_bottom_y + norm_dy * tail_length

    p3 = (int(tip_x), int(tip_y))

    # Draw Tail (Triangle)
    draw.polygon([p1, p2, p3], fill=BUBBLE_COLOR)

    # Draw rounded rectangle for the bubble
    shape = [(x_pos, y_pos), (x_pos + bubble_w, y_pos + bubble_h)]
    draw.rounded_rectangle(shape, radius=25, fill=BUBBLE_COLOR)

    # Draw Text
    text_x = x_pos + PADDING
    text_y = y_pos + PADDING
    draw.multiline_text((text_x, text_y), wrapped_text, fill=TEXT_COLOR, font=font, align="center")

def apply_thumbnail_layout(img: Image.Image) -> Image.Image:
    """
    Composites the thumbnail background:
    - Shifts the image down so characters sit lower in the frame.
    - Adds a curved black gradient at the top (lower on sides, higher in middle) 
      to make space for speech bubbles on the sides while keeping the center visible.
    """
    width, height = img.size
    
    # Create a new black canvas
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 255))
    
    # Shift the image down by 22% to move characters lower
    shift_y = int(height * 0.22)
    canvas.paste(img, (0, shift_y))
    
    # Create a gradient overlay
    gradient = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(gradient)
    
    # The dip at the edges to accommodate the speech bubbles
    max_dip = int(height * 0.15)
    
    # The gradient transition takes 25% of the height
    grad_height = int(height * 0.25)
    
    for x in range(width):
        # Normalized x from -1 to 1
        nx = (x - width / 2) / (width / 2)
        # Oval curve
        y_shift = max_dip * (nx ** 6)
        
        # We need solid black to cover at LEAST down to shift_y, so we don't see the top edge of the image!
        local_solid_black_end = int(shift_y + y_shift)
        local_grad_end = local_solid_black_end + grad_height
        
        # Draw solid black from 0 to local_solid_black_end
        if local_solid_black_end > 0:
            draw.line([(x, 0), (x, local_solid_black_end)], fill=(0, 0, 0, 255))
            
        # Draw fade from local_solid_black_end to local_grad_end
        for y in range(local_solid_black_end, local_grad_end):
            if y >= height:
                break
            
            ratio = (y - local_solid_black_end) / grad_height
            alpha = int(255 * ((1 - ratio) ** 2))
            draw.point((x, y), fill=(0, 0, 0, alpha))
            
    # Composite the gradient over the canvas
    return Image.alpha_composite(canvas, gradient)

def create_thumbnail(topic: str, language: str, bg_paths: List[str], content: VideoContent) -> Tuple[str, dict]:
    """
    Creates a thumbnail by choosing a background from the second half of the video,
    generating short punchy texts, getting head coordinates via Gemini, 
    and drawing dynamic speech bubbles.
    """
    if not bg_paths or not content.conversations:
        return "", {"prompt_tokens": 0, "candidates_tokens": 0}
        
    # Choose random image from the second half
    start_idx = max(0, len(bg_paths) // 2)
    selected_idx = random.randint(start_idx, len(bg_paths) - 1)
    
    bg_image_path = bg_paths[selected_idx]
    conversation = content.conversations[selected_idx]
    
    # 1. Load and modify the image first for layout
    img = Image.open(bg_image_path).convert("RGBA")
    img = apply_thumbnail_layout(img)
    
    # Save a temporary version for Gemini to analyze
    safe_title = "".join(x for x in content.video_title if x.isalnum() or x in " -_").strip().replace(" ", "_").lower()
    temp_path = os.path.join(OUTPUT_DIR, f"{safe_title}_{language}_temp_thumb.jpg")
    img.convert("RGB").save(temp_path)
    
    # Get first 3-4 lines of dialogue as context
    dialogue_context = "\n".join([f"{line.speaker}: {line.text}" for line in conversation.dialogue[:4]])
    
    print(f"Generating thumbnail text and layout for {language}...")
    thumb_text, usage = generate_thumbnail_text(topic, dialogue_context, language, temp_path)
    
    # Clean up temp file
    try:
        os.remove(temp_path)
    except OSError:
        pass
    
    width, height = img.size
    draw = ImageDraw.Draw(img)
    
    # Extract head positions from Gemini response
    # Gemini returns 0.0 to 1.0 percentages
    left_head = (int(thumb_text.left_head_x * width), int(thumb_text.left_head_y * height))
    right_head = (int(thumb_text.right_head_x * width), int(thumb_text.right_head_y * height))
    
    # Fallbacks in case Gemini flips them or gives weird coordinates
    if left_head[0] > right_head[0]:
        left_head, right_head = right_head, left_head
        
    # Draw bubbles
    draw_dynamic_speech_bubble(draw, thumb_text.left_bubble, left_head, "left", width, height)
    draw_dynamic_speech_bubble(draw, thumb_text.right_bubble, right_head, "right", width, height)
    
    # Add flag in bottom-left corner
    flag_path = f"{language.lower()}-flag-round.png"
    if os.path.exists(flag_path):
        try:
            flag_img = Image.open(flag_path).convert("RGBA")
            # Resize flag to be appropriate for thumbnail (e.g., 15% of height)
            flag_size = int(height * 0.15)
            flag_img = flag_img.resize((flag_size, flag_size), Image.Resampling.LANCZOS)
            
            # Paste flag with margin
            flag_margin = 30
            img.paste(flag_img, (flag_margin, height - flag_size - flag_margin), flag_img)
        except Exception as e:
            print(f"Warning: Could not add flag for {language}: {e}")
    
    # Save thumbnail
    thumb_path = os.path.join(OUTPUT_DIR, f"{safe_title}_{language}_thumbnail.jpg")
    img.convert("RGB").save(thumb_path)
    
    return thumb_path, usage
