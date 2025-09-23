# interview/services/stt_service.py
import asyncio
import json
import websockets

DEEPGRAM_REALTIME_URL = (
    "wss://api.deepgram.com/v1/listen"
    "?encoding=opus&sample_rate=48000&channels=1"
    "&multichannel=false&punctuate=true&interim_results=true"
)

class DeepgramStream:
    """
    Minimal Deepgram realtime WS client.
    Call .start(), then .send_audio(bytes) repeatedly.
    Subscribe to transcripts via on_transcript (async callback).
    Call .flush_and_close() when done.
    """
    def __init__(self, api_key: str, on_transcript):
        self.api_key = api_key
        self.on_transcript = on_transcript  # async def callback(dict)
        self.ws = None
        self._recv_task = None
        self._closed = False

    async def start(self):
        headers = [("Authorization", f"Token {self.api_key}")]
        self.ws = await websockets.connect(
            DEEPGRAM_REALTIME_URL,
            extra_headers=headers,
            ping_interval=15
        )
        # Tell Deepgram the stream format (important!)
        await self.ws.send(json.dumps({
            "type": "start",
            "encoding": "opus",
            "sample_rate": 48000,
            "channels": 1,
            "interim_results": True,
            "punctuate": True
        }))
        # Start receiver
        self._recv_task = asyncio.create_task(self._receiver())

    async def send_audio(self, chunk: bytes):
        """Send binary audio (webm/opus) to Deepgram."""
        if self.ws:
            await self.ws.send(chunk)

    async def _receiver(self):
        try:
            async for msg in self.ws:
                try:
                    data = json.loads(msg)
                except Exception:
                    continue
                # Deepgram sends transcripts in 'channel.alternatives[0].transcript'
                # interim results contain "is_final": False
                # finals contain "is_final": True
                try:
                    await self.on_transcript(data)
                except Exception:
                    # Don't crash the receiver if callback fails
                    pass
        except Exception:
            # Socket closed or network error
            pass

    async def flush_and_close(self):
        """Gracefully close the Deepgram stream."""
        if self._closed:
            return
        self._closed = True
        try:
            if self.ws:
                try:
                    # Tell Deepgram stream is finished
                    await self.ws.send(json.dumps({"type": "CloseStream"}))
                except Exception:
                    pass
                await asyncio.sleep(0.2)
                await self.ws.close()
        finally:
            if self._recv_task:
                self._recv_task.cancel()
