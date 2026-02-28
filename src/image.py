import replicate
import os
from src.config import REPLICATE_API_TOKEN, OUTPUT_DIR

# Initialize replicate client via env var natively used by replicate library
os.environ["REPLICATE_API_TOKEN"] = REPLICATE_API_TOKEN

def generate_background_image(prompt: str, video_title: str) -> str:
    """
    Generates a 16:9 Studio Ghibli style background image for the conversation.
    Downloads the resulting image and returns the local file path.
    """
    # Combine the base style constraints with the LLM-generated scene prompt
    final_prompt = f"Disney / Pixar 3D animation style, highly detailed, exactly two people facing each other in a conversational setup. {prompt}. The characters must be clearly distinct and standing on their respective sides. High quality, vibrant colors. Absolutely NO TEXT, NO LETTERS, NO WORDS, NO SPEECH BUBBLES, NO WATERMARKS in the image."
    
    output = replicate.run(
        "prunaai/z-image-turbo",
        input={
            "prompt": final_prompt,
            "width": 1024,
            "height": 576
        }
    )
    
    # Save the image
    safe_title = "".join(x for x in video_title if x.isalnum() or x in " -_").strip().replace(" ", "_").lower()
    file_path = os.path.join(OUTPUT_DIR, f"{safe_title}_bg.jpeg")
    
    with open(file_path, "wb") as f:
        f.write(output.read())
        
    return file_path

