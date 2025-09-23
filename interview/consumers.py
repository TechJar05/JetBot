# interview/consumers.py
import json
import base64
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings
from all_services.stt_services import DeepgramStream

class InterviewConsumer(AsyncWebsocketConsumer):
    """
    Message format from frontend:
      - For audio chunks (from MediaRecorder):
        { "type": "audio", "mime": "audio/webm;codecs=opus", "chunk": "<base64>" }

      - For control (optional):
        { "type": "control", "action": "stop" }

    Messages to frontend:
      - Partial transcript:
        { "type": "transcript", "final": false, "text": "..." }
      - Final transcript:
        { "type": "transcript", "final": true, "text": "..." }
      - System/info:
        { "type": "info", "message": "..." }
      - Errors:
        { "type": "error", "message": "..." }
    """

    async def connect(self):
        self.interview_id = self.scope["url_route"]["kwargs"]["interview_id"]
        self.user = self.scope.get("user")

        # (Optional) reject anonymous
        if not self.user or not self.user.is_authenticated or self.user.role != "student":
            await self.close(code=4401)  # unauthorized
            return

        # Prepare Deepgram stream
        api_key = getattr(settings, "DEEPGRAM_API_KEY", "")
        if not api_key:
            await self.accept()
            await self.send_json({"type": "error", "message": "Deepgram API key missing on server"})
            await self.close()
            return

        async def on_transcript(payload: dict):
            # Deepgram final/partial parsing
            # Example payload shape:
            # {"type":"Results","channel":{"alternatives":[{"transcript":"..."}]},"is_final":false}
            if payload.get("type") != "Results":
                return
            channel = payload.get("channel", {})
            alts = channel.get("alternatives", [])
            if not alts:
                return
            text = alts[0].get("transcript", "")
            is_final = payload.get("is_final", False)
            if text:
                await self.send_json({"type": "transcript", "final": bool(is_final), "text": text})

        self.dg = DeepgramStream(api_key, on_transcript=on_transcript)
        try:
            await self.dg.start()
        except Exception as e:
            await self.accept()
            await self.send_json({"type": "error", "message": f"Deepgram connect failed: {e}"})
            await self.close()
            return

        await self.accept()
        await self.send_json({"type": "info", "message": f"Interview {self.interview_id} connected. Start sending audio chunks."})

    async def receive(self, text_data=None, bytes_data=None):
        if text_data:
            try:
                msg = json.loads(text_data)
            except Exception:
                await self.send_json({"type": "error", "message": "Invalid JSON"})
                return

            mtype = msg.get("type")

            if mtype == "audio":
                # Expect base64 of webm/opus chunk
                b64 = msg.get("chunk")
                if not b64:
                    await self.send_json({"type": "error", "message": "Missing audio chunk"})
                    return
                try:
                    chunk = base64.b64decode(b64)
                except Exception:
                    await self.send_json({"type": "error", "message": "Invalid base64"})
                    return
                # send to Deepgram
                try:
                    await self.dg.send_audio(chunk)
                except Exception as e:
                    await self.send_json({"type": "error", "message": f"Audio send failed: {e}"})

            elif mtype == "control" and msg.get("action") == "stop":
                await self.send_json({"type": "info", "message": "Stopping stream"})
                await self.dg.flush_and_close()
                await self.close()

            else:
                # Echo for any other text payloads
                await self.send_json({"type": "echo", "payload": msg})

        # If bytes_data ever used, you can directly forward to Deepgram

    async def disconnect(self, close_code):
        try:
            if hasattr(self, "dg"):
                await self.dg.flush_and_close()
        except Exception:
            pass

    async def send_json(self, data: dict):
        await super().send(text_data=json.dumps(data))
