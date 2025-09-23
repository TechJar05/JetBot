# interview/consumers.py
import json
import base64
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings
from all_services.stt_services import DeepgramStream

# Optional: toggle this to True while debugging
DEBUG_WS = False

class InterviewConsumer(AsyncWebsocketConsumer):
    """
    Frontend -> Server:
      { "type": "audio", "mime": "audio/webm;codecs=opus", "chunk": "<base64>" }
      { "type": "control", "action": "stop" }

    Server -> Frontend:
      { "type": "info", "message": "..." }
      { "type": "error", "message": "..." }
      { "type": "transcript", "final": bool, "text": "..." }
    """

    async def connect(self):
        self.interview_id = self.scope["url_route"]["kwargs"]["interview_id"]
        self.user = self.scope.get("user")
        self.dg = None

        # Require an authenticated student
        if not self.user or not self.user.is_authenticated or getattr(self.user, "role", None) != "student":
            await self.close(code=4401)
            return

        # Deepgram API key
        api_key = getattr(settings, "DEEPGRAM_API_KEY", "")
        await self.accept()  # accept WS early so we can emit errors to client
        if not api_key:
            await self.send_json({"type": "error", "message": "Deepgram API key missing on server"})
            await self.close()
            return

        # Transcript handler
        async def on_transcript(payload: dict):
            """
            Handles messages like:
              - Results (with is_final / transcript)
              - MetadataResponse
              - CloseStreamResponse / finalize
            """
            ptype = payload.get("type")
            if ptype == "Results":
                channel = payload.get("channel", {})
                alts = channel.get("alternatives", [])
                if not alts:
                    return
                text = alts[0].get("transcript", "")
                if not text:
                    return
                is_final = bool(payload.get("is_final", False))
                await self.send_json({"type": "transcript", "final": is_final, "text": text})

            elif ptype in ("MetadataResponse", "FinalizeResponse", "CloseStreamResponse"):
                # You can forward or ignore these; forwarding helps debugging
                if DEBUG_WS:
                    await self.send_json({"type": "info", "message": f"DG:{ptype}"})

            else:
                # Unknown/other messages (often harmless)
                if DEBUG_WS:
                    await self.send_json({"type": "info", "message": f"DG:other {ptype}"})


        # Start Deepgram realtime stream
        self.dg = DeepgramStream(api_key, on_transcript=on_transcript)
        try:
            await self.dg.start()
        except Exception as e:
            await self.send_json({"type": "error", "message": f"Deepgram connect failed: {e}"})
            await self.close()
            return

        await self.send_json({"type": "info", "message": f"Interview {self.interview_id} connected. Start sending audio chunks."})

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data:
            return

        # Parse JSON
        try:
            msg = json.loads(text_data)
        except Exception:
            await self.send_json({"type": "error", "message": "Invalid JSON"})
            return

        mtype = msg.get("type")

        # Audio payloads
        if mtype == "audio":
            if self.dg is None:
                await self.send_json({"type": "error", "message": "STT stream not ready"})
                return

            # Validate mime (best-effort)
            mime = str(msg.get("mime") or "")
            if "audio/webm" not in mime or "opus" not in mime:
                # Not fatal, but warn once per session if needed
                if DEBUG_WS:
                    await self.send_json({"type": "info", "message": f"Non-opus mime received: {mime}"})

            # Decode base64 and send
            b64 = msg.get("chunk")
            if not b64:
                await self.send_json({"type": "error", "message": "Missing audio chunk"})
                return

            try:
                chunk = base64.b64decode(b64)
            except Exception:
                await self.send_json({"type": "error", "message": "Invalid base64"})
                return

            # Drop obviously huge frames (protects your WS/STT)
            if len(chunk) > 512 * 1024:  # 512 KB safeguard
                if DEBUG_WS:
                    await self.send_json({"type": "info", "message": f"Chunk too large: {len(chunk)} bytes, dropping"})
                return

            try:
                await self.dg.send_audio(chunk)
                if DEBUG_WS:
                    await self.send_json({"type": "info", "message": f"server got audio ({len(chunk)} bytes)"})
            except Exception as e:
                await self.send_json({"type": "error", "message": f"Audio send failed: {e}"})

        # Control messages
        elif mtype == "control":
            action = msg.get("action")
            if action == "stop":
                await self.send_json({"type": "info", "message": "Stopping stream"})
                try:
                    if self.dg:
                        await self.dg.flush_and_close()
                finally:
                    await self.close()
            else:
                # Unknown control action
                if DEBUG_WS:
                    await self.send_json({"type": "info", "message": f"Unknown control: {action}"})

        else:
            # Echo for any other text payloads (handy while integrating)
            await self.send_json({"type": "echo", "payload": msg})

    async def disconnect(self, close_code):
        try:
            if self.dg:
                await self.dg.flush_and_close()
        except Exception:
            pass

    async def send_json(self, data: dict):
        await super().send(text_data=json.dumps(data))
