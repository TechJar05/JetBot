# interview/consumers.py
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from authentication.models import Interview, User


class InterviewConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Extract interview_id from URL
        self.interview_id = self.scope["url_route"]["kwargs"]["interview_id"]

        # For now, accept connection unconditionally
        await self.accept()

        await self.send(text_data=json.dumps({
            "message": f"Interview {self.interview_id} connection established"
        }))

    async def receive(self, text_data=None, bytes_data=None):
        """
        This is triggered whenever the frontend sends data.
        For MVP, we'll just echo back text.
        Later, we will handle audio streaming here.
        """
        if text_data:
            data = json.loads(text_data)
            await self.send(text_data=json.dumps({
                "echo": data
            }))

    async def disconnect(self, close_code):
        print(f"Interview {self.interview_id} disconnected with code {close_code}")
