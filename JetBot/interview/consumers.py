# interview/consumers.py
import json
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.conf import settings
from dotenv import load_dotenv

from all_services.assemblyai_stream import AssemblyAIStream
from all_services.tts_services import stream_tts
from authentication.models import Interview

load_dotenv()
DEBUG_WS = True


class InterviewConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.interview_id = self.scope["url_route"]["kwargs"]["interview_id"]
        self.user = self.scope.get("user")
        self.dg = None
        self.questions = []
        self.current_q = 0

        # ✅ Only students can connect
        if not self.user or not self.user.is_authenticated or getattr(self.user, "role", None) != "student":
            await self.close(code=4401)
            return

        # ✅ Load interview & verify student ownership
        interview = await self.get_interview()
        if not interview:
            await self.close(code=4404)  # not found / not allowed
            return

        # ✅ Load questions from DB
        self.questions = interview.questions or []
        if not self.questions:
            await self.close(code=4404)
            return

        await self.accept()

        api_key = settings.DEEPGRAM_API_KEY
        if not api_key:
            await self.safe_send({"type": "error", "message": "Deepgram API key missing"})
            await self.close()
            return

        # ✅ Deepgram transcript callback
        async def on_transcript(payload: dict):
            try:
                if payload.get("type") == "Turn":
                    transcript = payload.get("transcript", "")
                    end_of_turn = payload.get("end_of_turn", False)

                    if transcript:
                        await self.safe_send({
                            "type": "transcript",
                            "final": end_of_turn,
                            "text": transcript
                        })
                        if end_of_turn:
                            await self.save_answer(transcript)
                            await self.safe_send({
                                "type": "answer_complete",
                                "message": "Answer captured. Continue or move to next question?"
                            })

                elif DEBUG_WS:
                    await self.safe_send({"type": "info", "message": f"DG:{payload.get('type')}"})
            except Exception as e:
                if DEBUG_WS:
                    await self.safe_send({"type": "error", "message": f"Transcript error: {e}"})

        # ✅ Start Deepgram stream
        self.stt = AssemblyAIStream(settings.ASSEMBLYAI_API_KEY, sample_rate=16000, on_transcript=on_transcript)
        try:
            await self.stt.start()
        except Exception as e:
            await self.safe_send({"type": "error", "message": f"Deepgram failed: {e}"})
            await self.close()
            return

        await asyncio.sleep(0.05)
        await self.safe_send({"type": "info", "message": f"Interview {self.interview_id} connected"})

    async def receive(self, text_data=None, bytes_data=None):
        # ✅ Handle raw audio chunks
        if bytes_data and self.stt:
            try:
                if len(bytes_data) > 512 * 1024:  # limit chunk size
                    return
                await self.stt.send_audio(bytes_data)
                if DEBUG_WS:
                    await self.safe_send({
                        "type": "info",
                        "message": f"Audio chunk {len(bytes_data)} bytes"
                    })
            except Exception as e:
                await self.safe_send({"type": "error", "message": f"Audio send failed: {e}"})
            return

        # ✅ Handle JSON messages
        if text_data:
            try:
                msg = json.loads(text_data)
            except Exception:
                await self.safe_send({"type": "error", "message": "Invalid JSON"})
                return

            if msg.get("type") == "control":
                action = msg.get("action")
                if action == "stop":
                    await self.safe_send({"type": "info", "message": "Stopping interview"})
                    try:
                        if self.stt:
                            await self.stt.flush_and_close()
                    finally:
                        await self.close()

                elif action == "start_interview":
                    await self.next_question()

                elif action == "next_question":
                    await self.next_question()

                elif action == "continue_answer":
                    await self.safe_send({"type": "info", "message": "Continuing same answer..."})

                elif DEBUG_WS:
                    await self.safe_send({"type": "info", "message": f"Unknown control: {action}"})

            else:
                await self.safe_send({"type": "echo", "payload": msg})

    async def next_question(self):
        if self.current_q >= len(self.questions):
            await self.safe_send({"type": "info", "message": "Interview complete"})
            return

        question = self.questions[self.current_q]
        self.current_q += 1

        # Save to DB
        await self.save_question(question)

        # ✅ Immediately tell frontend which question is being asked
        await self.safe_send({
            "type": "question",
            "text": question
        })

        # Stream TTS and forward audio
        async def forward_chunk(audio_b64, is_final):
            await self.safe_send({
                "type": "tts_chunk",
                "audio": audio_b64,
                "isFinal": is_final,
                "text": question if is_final else None
            })

        await stream_tts(question, forward_chunk)


    # -------------------------
    # DB Helpers
    # -------------------------
    @database_sync_to_async
    def get_interview(self):
        try:
            return Interview.objects.get(id=self.interview_id, student=self.user)
        except Interview.DoesNotExist:
            return None

    @database_sync_to_async
    def save_question(self, text):
        interview = Interview.objects.get(id=self.interview_id, student=self.user)
        interview.full_transcript = (interview.full_transcript or "") + f"\nQ: {text}"
        interview.save()

    @database_sync_to_async
    def save_answer(self, text):
        interview = Interview.objects.get(id=self.interview_id, student=self.user)
        interview.full_transcript = (interview.full_transcript or "") + f"\nA: {text}"
        interview.save()

    async def disconnect(self, close_code):
        try:
            if self.stt:
               await self.stt.flush_and_close()
        except Exception:
            pass

    async def safe_send(self, data: dict):
        try:
            await super().send(text_data=json.dumps(data))
        except Exception:
            pass
