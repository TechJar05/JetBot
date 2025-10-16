# all_services/tts_services.py
"""
Helper to stream ElevenLabs TTS via their websocket.
Provides: async def stream_tts(question_text: str, send_chunk: callable)
where send_chunk(audio_b64: str, is_final: bool) is an async callable.

This implementation uses 'websockets' (async websockets client).
"""

import os
import json
import logging
import websockets
import asyncio

logger = logging.getLogger(__name__)


ELEVEN_API_KEY = os.getenv("ELEVENLABS_API_KEY")
VOICE_ID = os.getenv("VOICE_ID")
MODEL_ID = os.getenv("MODEL_ID")

ELEVEN_WS_URL = lambda: f"wss://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}/stream-input?model_id={MODEL_ID}"

async def stream_tts(question_text: str, send_chunk):
    """
    Connects to ElevenLabs and streams TTS. Calls send_chunk(audio_b64, is_final)
    for each received audio message. send_chunk may be an async function.
    """
    if not ELEVEN_API_KEY:
        raise RuntimeError("ElevenLabs API key not set (ELEVEN_API_KEY or ELEVENLABS_API_KEY)")

    uri = ELEVEN_WS_URL()
    try:
        async with websockets.connect(uri) as ws:
            # first message (handshake): include API key + voice settings
            init_message = {
                "text": " ",
                "xi_api_key": ELEVEN_API_KEY,
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.8,
                    "use_speaker_boost": False,
                    "speed": 1.0
                },
                "generation_config": {
                    "chunk_length_schedule": [120, 160, 250, 290]
                },
                "output_format": "pcm_16000"
            }
            await ws.send(json.dumps(init_message))

            # send main text
            await ws.send(json.dumps({"text": question_text}))
            # flush message to indicate end of input
            await ws.send(json.dumps({"text": "", "flush": True}))

            # stream incoming messages
            async for message in ws:
                try:
                    data = json.loads(message)
                except Exception:
                    logger.debug("Non-JSON message from ElevenLabs")
                    continue

                # audio chunks are base64 strings in "audio"
                if "audio" in data:
                    audio_b64 = data["audio"]
                    is_final = data.get("isFinal", False)
                    # call send_chunk (support sync or async callables)
                    if asyncio.iscoroutinefunction(send_chunk):
                        await send_chunk(audio_b64, is_final)
                    else:
                        send_chunk(audio_b64, is_final)

                if data.get("isFinal"):
                    # final chunk -> break
                    break

    except Exception as e:
        logger.exception("ElevenLabs TTS error")
        # propagate or swallow based on your preference. We'll raise to surface errors.
        raise
