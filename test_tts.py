import os
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

text = "Hallo, wie geht es dir heute? Ich möchte gerne einen Kaffee bestellen."

response = client.models.generate_content(
    model='gemini-2.5-flash-preview-tts',
    contents=text,
    config=types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name="Aoede"
                )
            )
        )
    ),
)
print("Success")
