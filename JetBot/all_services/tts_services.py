# all_services/tts_services.py
import os
import json
import websockets
import inspect

# ELEVEN_API_KEY = os.getenv("ELEVEN_API_KEY")
# VOICE_ID = os.getenv("ELEVEN_VOICE_ID", "YOUR_VOICE_ID")
# MODEL_ID = os.getenv("ELEVEN_MODEL_ID", "eleven_monolingual_v1")

ELEVEN_API_KEY = "sk_fd451ccf28b2fca77d0a86297894245f614c0a403c2a0e14"
VOICE_ID = "vWovrQmwpIKB9L65OBCh"
MODEL_ID = "eleven_multilingual_v2"

ELEVEN_WS_URL = (
    f"wss://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}/stream-input"
    f"?model_id={MODEL_ID}"
)

import logging

logging.warning(f"Using websockets version: {websockets.__version__}")

async def stream_tts(question_text: str, send_chunk):
    """
    Stream audio from ElevenLabs WS and forward chunks via send_chunk callback.
    send_chunk(audio_b64: str, is_final: bool)
    """
    async with websockets.connect(ELEVEN_WS_URL) as ws:
        # Initialize connection (with key, voice, and PCM format)
        await ws.send(json.dumps({
            "text": " ",
            "xi_api_key": ELEVEN_API_KEY,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.8,
                "use_speaker_boost": False,
                "speed": 0.9,
            },
            "output_format": "pcm_16000",
            "generation_config": {
                "chunk_length_schedule": [50, 120, 160, 250]
            }
        }))

        # Send the actual question
        await ws.send(json.dumps({
            "text": question_text + " "
        }))

        # Flush to finalize
        await ws.send(json.dumps({
            "text": "",
            "flush": True
        }))

        # Stream audio back
        async for msg in ws:
            data = json.loads(msg)
            if "audio" in data:
                await send_chunk(data["audio"], data.get("isFinal", False))
            if data.get("isFinal"):
                break
