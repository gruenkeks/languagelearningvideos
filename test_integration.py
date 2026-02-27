import os
import asyncio
from src.llm import generate_video_content
from src.tts import generate_audio_for_dialogue

content = generate_video_content("Ordering a coffee")
print("Generated dialogue:", [line.text for line in content.dialogue])

generate_audio_for_dialogue(content.dialogue, "test_video")
print("Done")



