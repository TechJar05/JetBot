# interview/services/stt_service.py
import asyncio
import json
import aiohttp

# Build URL with query params per docs
# Adjust model/language/flags as you like
DEEPGRAM_REALTIME_URL = (
    "wss://api.deepgram.com/v1/listen"
    "?encoding=opus"
    "&sample_rate=48000"
    "&channels=1"
    "&multichannel=false"
    "&punctuate=true"
    "&interim_results=true"
    "&model=nova-2"
    "&language=en"
    # "&endpointing=10"           # optional: finalize quicker on pauses
    # "&vad_events=true"          # optional: speech-start events
    # "&smart_format=true"        # optional: phone, dates, etc.
)

class DeepgramStream:
    """
    Realtime Deepgram client using aiohttp.
    - Call start()
    - Repeatedly send_audio(bytes) with webm/opus chunks
    - You'll receive transcripts via on_transcript(payload)
    - Call flush_and_close() to finalize
    """
    def __init__(self, api_key: str, on_transcript):
        self.api_key = "5933167cd46c63282343c2b0255fd067029fec2e"
        self.on_transcript = on_transcript
        self.session: aiohttp.ClientSession | None = None
        self.ws: aiohttp.ClientWebSocketResponse | None = None
        self._recv_task: asyncio.Task | None = None
        self._closed = False

    async def start(self):
        # Per docs: Authorization: token <DEEPGRAM_API_KEY>
        self.session = aiohttp.ClientSession(
            headers={"Authorization": f"token {self.api_key}"}
        )
        self.ws = await self.session.ws_connect(
            DEEPGRAM_REALTIME_URL,
            heartbeat=15,
            autoping=True,
            ssl=True,
        )
        # No explicit "start" message needed when config is in the URL.
        self._recv_task = asyncio.create_task(self._receiver())

    async def send_audio(self, chunk: bytes):
        if self.ws and not self.ws.closed:
            await self.ws.send_bytes(chunk)  # send audio as binary

    async def _receiver(self):
        try:
            async for msg in self.ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                    except Exception:
                        continue
                    # You'll see:
                    #  - Results (with is_final true/false)
                    #  - Metadata
                    #  - CloseStreamResponse / finalize, etc.
                    try:
                        await self.on_transcript(data)
                    except Exception:
                        pass
                elif msg.type in (aiohttp.WSMsgType.ERROR,
                                  aiohttp.WSMsgType.CLOSE,
                                  aiohttp.WSMsgType.CLOSED):
                    break
        except Exception:
            pass

    async def flush_and_close(self):
        if self._closed:
            return
        self._closed = True
        try:
            if self.ws and not self.ws.closed:
                # Ask server to finalize buffered audio/results
                try:
                    await self.ws.send_str(json.dumps({"type": "CloseStream"}))
                except Exception:
                    pass
                await asyncio.sleep(0.2)
                await self.ws.close()
        finally:
            if self._recv_task:
                self._recv_task.cancel()
            if self.session:
                await self.session.close()
