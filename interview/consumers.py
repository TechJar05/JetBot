import json
import asyncio
import websockets
import aiohttp
from urllib.parse import urlencode
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from authentication.models import Interview

# -------------------------
# CONFIG
# -------------------------
ELEVENLABS_API_KEY = "sk_fd451ccf28b2fca77d0a86297894245f614c0a403c2a0e14"
VOICE_ID = "vWovrQmwpIKB9L65OBCh"
MODEL_ID = "eleven_flash_v2_5"
ASSEMBLYAI_API_KEY = "32c3f5ecfc734011b13dd74e53f71f8c"


# -------------------------
# HELPERS
# -------------------------
@database_sync_to_async
def get_interview(interview_id, user):
    try:
        return Interview.objects.get(id=interview_id, student=user)
    except Interview.DoesNotExist:
        return None


import re

@database_sync_to_async
def save_full_transcript(interview, transcripts):
    """
    Save all Q&A pairs to Interview.full_transcript
    and clean repeated question phrases from answers.
    """
    cleaned_pairs = []

    for i, (q, a) in enumerate(transcripts):
        # Normalize whitespace
        question = q.strip()
        answer = a.strip()

        # Remove question-like repetitions from the answer
        # Example: "Can you share your experience..." → remove if it appears in the answer start
        q_lower = re.escape(question.lower())
        a_lower = answer.lower()

        # Remove full or partial question phrases from start of answer
        cleaned_answer = re.sub(
            rf"^{q_lower}[:\s,.-]*", "", a_lower
        )

        # Also handle partial question fragments that match 5+ starting words
        q_words = question.split()
        if len(q_words) >= 5:
            partial_pattern = re.escape(" ".join(q_words[:5]).lower())
            cleaned_answer = re.sub(
                rf"^{partial_pattern}[:\s,.-]*", "", cleaned_answer
            )

        # Restore capitalization of first letter
        cleaned_answer = cleaned_answer.strip().capitalize()

        cleaned_pairs.append((question, cleaned_answer))

    full_text = "\n".join([f"Q{i+1}: {q}\nA{i+1}: {a}" for i, (q, a) in enumerate(cleaned_pairs)])
    interview.full_transcript = full_text.strip()
    interview.save(update_fields=["full_transcript"])



# ============================================================
# TTS CONSUMER
# ============================================================
class TTSConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.interview_id = self.scope['url_route']['kwargs'].get("interview_id")
        self.user = self.scope.get("user", AnonymousUser())

        self.interview = await get_interview(self.interview_id, self.user)
        if not self.interview:
            await self.close(code=4001)
            return

        self.questions = self.interview.questions or []
        self.current_index = 0
        self.transcripts = []
        self.current_answer = ""  # Accumulate live answer text
        await self.accept()
        print(f"✅ TTS connected for interview {self.interview_id}")

    async def disconnect(self, close_code):
        # Save last pending answer (if any)
        if self.current_index > 0 and self.current_answer.strip():
            last_question = self.questions[self.current_index - 1]
            self.transcripts.append((last_question, self.current_answer.strip()))

        if self.transcripts:
            await save_full_transcript(self.interview, self.transcripts)
        print(f"❌ TTS disconnected for interview {self.interview_id}")

    async def receive(self, text_data):
        data = json.loads(text_data)
        command = data.get("command")

        # --------------------
        # NEXT QUESTION LOGIC
        # --------------------
        if command == "next":
            # ✅ Before asking next question — store the current answer (if any)
            if self.current_index > 0 and self.current_answer.strip():
                prev_question = self.questions[self.current_index - 1]
                self.transcripts.append((prev_question, self.current_answer.strip()))
                self.current_answer = ""  # reset buffer

            # Send next question (if available)
            if self.current_index < len(self.questions):
                question = self.questions[self.current_index]
                self.current_index += 1
                asyncio.create_task(self._send_question(question))
            else:
                # Interview complete → flush transcript
                if self.transcripts:
                    await save_full_transcript(self.interview, self.transcripts)
                await self.send(json.dumps({"isFinal": True, "text": "Interview Complete"}))

        # --------------------
        # LIVE ANSWER RECEIVING
        # --------------------
        elif command == "answer":
            text = data.get("text", "")
            # Append to current accumulated answer
            self.current_answer += " " + text.strip()

    async def _send_question(self, input_text: str):
        uri = f"wss://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}/stream-input?model_id={MODEL_ID}"
        try:
            async with websockets.connect(uri) as ws:
                # initial handshake
                init_message = {
                    "text": " ",
                    "voice_settings": {
                        "stability": 0.5,
                        "similarity_boost": 0.8,
                        "use_speaker_boost": False,
                        "speed": 1.0
                    },
                    "generation_config": {"chunk_length_schedule": [120, 160, 250, 290]},
                    "xi_api_key": ELEVENLABS_API_KEY,
                }
                await ws.send(json.dumps(init_message))
                await ws.send(json.dumps({"text": input_text}))
                await ws.send(json.dumps({"text": ""}))

                async for message in ws:
                    data = json.loads(message)
                    if data.get("audio"):
                        await self.send(json.dumps({
                            "audio": data["audio"],
                            "isFinal": data.get("isFinal", False)
                        }))
                    elif data.get("isFinal"):
                        await self.send(json.dumps({"isFinal": True, "text": input_text}))
                        break
                    elif data.get("error"):
                        await self.send(json.dumps({"error": data["error"]}))
                        break
        except Exception as e:
            await self.send(json.dumps({"error": f"ElevenLabs connection failed: {str(e)}"}))



# ============================================================
# STT CONSUMER
# ============================================================
class STTConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.interview_id = self.scope['url_route']['kwargs'].get("interview_id")
        self.user = self.scope.get("user", AnonymousUser())

        self.interview = await get_interview(self.interview_id, self.user)
        if not self.interview:
            await self.close(code=4001)
            return

        await self.accept()
        print(f"✅ STT connected for interview {self.interview_id}")

        # connect to AssemblyAI
        params = {"sample_rate": 16000, "format_turns": True}
        url = f"wss://streaming.assemblyai.com/v3/ws?{urlencode(params)}"
        self.session = aiohttp.ClientSession()
        self.assembly_ws = await self.session.ws_connect(url, headers={"Authorization": ASSEMBLYAI_API_KEY})
        self.receiver_task = asyncio.create_task(self._receive_from_assembly())

    async def disconnect(self, close_code):
        if hasattr(self, "assembly_ws") and not self.assembly_ws.closed:
            await self.assembly_ws.send_json({"type": "Terminate"})
            await self.assembly_ws.close()
        if hasattr(self, "receiver_task"):
            self.receiver_task.cancel()
            try:
                await self.receiver_task
            except asyncio.CancelledError:
                pass
        if hasattr(self, "session") and not self.session.closed:
            await self.session.close()
        print(f"❌ STT disconnected for interview {self.interview_id}")

    async def receive(self, text_data=None, bytes_data=None):
        try:
            if bytes_data:
                if hasattr(self, "assembly_ws") and not self.assembly_ws.closed:
                    await self.assembly_ws.send_bytes(bytes_data)
            elif text_data:
                msg = json.loads(text_data)
                if msg.get("command") == "terminate":
                    if hasattr(self, "assembly_ws") and not self.assembly_ws.closed:
                        await self.assembly_ws.send_json({"type": "Terminate"})
                    await self.close()
        except Exception as e:
            await self.send(json.dumps({"error": str(e)}))

    async def _receive_from_assembly(self):
        try:
            async for msg in self.assembly_ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    await self.send(json.dumps(data))
                elif msg.type == aiohttp.WSMsgType.BINARY:
                    pass
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    break
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            await self.send(json.dumps({"error": str(e)}))


