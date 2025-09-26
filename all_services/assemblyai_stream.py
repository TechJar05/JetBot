# all_services/assemblyai_stream.py
import json
import websockets
import asyncio

ASSEMBLYAI_URL = "wss://streaming.assemblyai.com/v3/ws"

class AssemblyAIStream:
    def __init__(self, api_key, sample_rate=16000, on_transcript=None):
        self.api_key = api_key
        self.sample_rate = sample_rate
        self.on_transcript = on_transcript
        self.ws = None

    async def start(self):
        uri = f"wss://streaming.assemblyai.com/v3/ws?sample_rate={self.sample_rate}"
        self.ws = await websockets.connect(
            uri,
            extra_headers={"Authorization": self.api_key},
        )

        # Immediately send "Begin"
        await self.ws.send(json.dumps({
            "type": "Begin",
            "sample_rate": self.sample_rate
        }))

        # Start listening for messages
        asyncio.create_task(self._listen())

    async def _listen(self):
        try:
            async for msg in self.ws:
                data = json.loads(msg)
                if self.on_transcript:
                    await self.on_transcript(data)
        except Exception as e:
            print("AssemblyAI WS closed:", e)

    async def send_audio(self, chunk: bytes):
        if self.ws:
            await self.ws.send(chunk)

    async def flush_and_close(self):
        if self.ws:
            await self.ws.send(json.dumps({"type": "Terminate"}))
            await self.ws.close()
            self.ws = None