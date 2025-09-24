# interview/consumers.py
import json
import base64
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer
from all_services.stt_services import DeepgramStream
from dotenv import load_dotenv
from django.conf import settings
# Access the API key from the environment
load_dotenv()

# Optional: toggle this to True while debugging
DEBUG_WS = True

class InterviewConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.interview_id = self.scope["url_route"]["kwargs"]["interview_id"]
        self.user = self.scope.get("user")
        self.dg = None

        # Require an authenticated student
        if not self.user or not self.user.is_authenticated or getattr(self.user, "role", None) != "student":
            await self.close(code=4401)
            return

        # Accept connection
        await self.accept()

        # Deepgram API key (use env var in production!)
        api_key = settings.DEEPGRAM_API_KEY
        if not api_key:
            await self.safe_send({"type": "error", "message": "Deepgram API key missing"})
            await self.close()
            return

        # Transcript callback
        async def on_transcript(payload: dict):
            try:
                ptype = payload.get("type")
                if ptype == "Results":
                    channel = payload.get("channel", {})
                    alts = channel.get("alternatives", [])
                    if alts and (text := alts[0].get("transcript")):
                        is_final = bool(payload.get("is_final", False))
                        await self.safe_send({
                            "type": "transcript",
                            "final": is_final,
                            "text": text
                        })
                elif DEBUG_WS:
                    await self.safe_send({"type": "info", "message": f"DG:{ptype}"})
            except Exception:
                pass

        # Start Deepgram connection
        self.dg = DeepgramStream(api_key, on_transcript=on_transcript)
        try:
            await self.dg.start()
        except Exception as e:
            await self.safe_send({"type": "error", "message": f"Deepgram failed: {e}"})
            await self.close()
            return

        # Let client know it’s ready
        await asyncio.sleep(0.05)
        await self.safe_send({
            "type": "info",
            "message": f"Interview {self.interview_id} connected. Start sending audio chunks."
        })

    async def receive(self, text_data=None, bytes_data=None):
        # --- Handle raw binary audio (preferred path) ---
        if bytes_data and self.dg:
            try:
                if len(bytes_data) > 512 * 1024:  # 512 KB safety limit
                    return
                await self.dg.send_audio(bytes_data)
                if DEBUG_WS:
                    await self.safe_send({
                        "type": "info",
                        "message": f"Audio chunk received ({len(bytes_data)} bytes)"
                    })
            except Exception as e:
                await self.safe_send({"type": "error", "message": f"Audio send failed: {e}"})
            return

        # --- Handle JSON control messages ---
        if text_data:
            try:
                msg = json.loads(text_data)
            except Exception:
                await self.safe_send({"type": "error", "message": "Invalid JSON"})
                return

            mtype = msg.get("type")

            if mtype == "control":
                action = msg.get("action")
                if action == "stop":
                    await self.safe_send({"type": "info", "message": "Stopping stream"})
                    try:
                        if self.dg:
                            await self.dg.flush_and_close()
                    finally:
                        await self.close()
                elif DEBUG_WS:
                    await self.safe_send({"type": "info", "message": f"Unknown control: {action}"})
            else:
                # Fallback echo for debugging
                await self.safe_send({"type": "echo", "payload": msg})

    async def disconnect(self, close_code):
        try:
            if self.dg:
                await self.dg.flush_and_close()
        except Exception:
            pass

    # --- Safe send wrapper ---
    async def safe_send(self, data: dict):
        try:
            await super().send(text_data=json.dumps(data))
        except Exception:
            pass
