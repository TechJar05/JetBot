# interview/services/stt_service.py
import asyncio
import json
import aiohttp
import logging

# Set up logging
logger = logging.getLogger(__name__)

# ✅ Use encoding=webm because frontend sends audio/webm;codecs=opus from MediaRecorder
DEEPGRAM_REALTIME_URL = "wss://api.deepgram.com/v1/listen?model=nova-2&language=en&punctuate=true&interim_results=true"



class DeepgramStream:
    """
    Realtime Deepgram client using aiohttp.
    - Call start()
    - Repeatedly send_audio(bytes) with webm/opus chunks
    - You'll receive transcripts via on_transcript(payload)
    - Call flush_and_close() to finalize
    """
    def __init__(self, api_key: str, on_transcript):
        self.api_key = api_key
        self.on_transcript = on_transcript
        self.session: aiohttp.ClientSession | None = None
        self.ws: aiohttp.ClientWebSocketResponse | None = None
        self._recv_task: asyncio.Task | None = None
        self._closed = False
        self._audio_chunks_sent = 0

        logger.info(f"DeepgramStream initialized with API key: {api_key[:10]}...")

    async def start(self):
        try:
            logger.info("Starting Deepgram WebSocket connection...")
            logger.info(f"Connecting to: {DEEPGRAM_REALTIME_URL}")

            headers = {"Authorization": f"token {self.api_key}"}
            logger.info(f"Using headers: Authorization: token {self.api_key[:10]}...")

            self.session = aiohttp.ClientSession(headers=headers)

            self.ws = await self.session.ws_connect(
                DEEPGRAM_REALTIME_URL,
                heartbeat=15,
                autoping=True,
                ssl=True,
                timeout=aiohttp.ClientTimeout(total=30),
            )

            logger.info("✅ Successfully connected to Deepgram WebSocket!")

            # Start the message receiver task
            self._recv_task = asyncio.create_task(self._receiver())

            await asyncio.sleep(0.1)
            await self._send_keepalive()

        except Exception as e:
            logger.error(f"❌ Failed to start Deepgram connection: {e}")
            raise

    async def _send_keepalive(self):
        try:
            if self.ws and not self.ws.closed:
                keepalive = json.dumps({"type": "KeepAlive"})
                await self.ws.send_str(keepalive)
                logger.info("📡 Sent keepalive to Deepgram")
        except Exception as e:
            logger.warning(f"Failed to send keepalive: {e}")

    async def send_audio(self, chunk: bytes):
        if self._closed:
            logger.warning("Attempted to send audio to closed stream")
            return

        if not self.ws or self.ws.closed:
            logger.warning("WebSocket not available for audio sending")
            return

        try:
            await self.ws.send_bytes(chunk)
            self._audio_chunks_sent += 1

            if self._audio_chunks_sent % 10 == 0:
                logger.info(
                    f"📤 Sent {self._audio_chunks_sent} audio chunks to Deepgram "
                    f"(latest: {len(chunk)} bytes)"
                )

        except Exception as e:
            logger.error(f"❌ Failed to send audio chunk: {e}")

    async def _receiver(self):
        logger.info("🎧 Starting Deepgram message receiver...")
        try:
            async for msg in self.ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        await self._handle_deepgram_message(data)
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse Deepgram message: {msg.data[:100]}...")
                    except Exception as e:
                        logger.error(f"Error handling Deepgram message: {e}")

                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"Deepgram WebSocket error: {msg.data}")
                    break

                elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED):
                    logger.info("Deepgram WebSocket closed")
                    break

        except Exception as e:
            logger.error(f"❌ Deepgram receiver error: {e}")

    async def _handle_deepgram_message(self, data: dict):
        msg_type = data.get("type", "unknown")

        if msg_type == "Results":
            await self._handle_transcript_result(data)
        elif msg_type == "Metadata":
            logger.info(f"📋 Deepgram metadata: {data}")
        elif msg_type == "SpeechStarted":
            logger.info("🎤 Speech detection started")
        elif msg_type == "UtteranceEnd":
            logger.info("🔚 Utterance ended")
        elif msg_type == "Error":
            logger.error(f"❌ Deepgram error: {data}")
        else:
            logger.debug(f"🔍 Unknown Deepgram message type '{msg_type}': {data}")

        try:
            await self.on_transcript(data)
        except Exception as e:
            logger.warning(f"Error in transcript callback: {e}")

    async def _handle_transcript_result(self, data: dict):
        try:
            channel = data.get("channel", {})
            alternatives = channel.get("alternatives", [])

            if not alternatives:
                return

            best_alt = alternatives[0]
            transcript = best_alt.get("transcript", "")
            confidence = best_alt.get("confidence", 0)
            is_final = data.get("is_final", False)

            if transcript.strip():
                status = "FINAL" if is_final else "INTERIM"
                logger.info(f"📝 [{status}] Transcript (conf: {confidence:.2f}): '{transcript}'")

        except Exception as e:
            logger.error(f"Error processing transcript result: {e}")

    async def flush_and_close(self):
        if self._closed:
            return

        logger.info("🔒 Closing Deepgram connection...")
        self._closed = True

        try:
            if self.ws and not self.ws.closed:
                try:
                    close_msg = json.dumps({"type": "CloseStream"})
                    await self.ws.send_str(close_msg)
                    logger.info("📤 Sent CloseStream message")
                except Exception as e:
                    logger.warning(f"Failed to send CloseStream: {e}")

                await asyncio.sleep(0.5)
                await self.ws.close()

        except Exception as e:
            logger.warning(f"Error during close: {e}")

        finally:
            if self._recv_task:
                self._recv_task.cancel()
                try:
                    await self._recv_task
                except asyncio.CancelledError:
                    pass

            if self.session:
                await self.session.close()

            logger.info("✅ Deepgram connection closed")


# Test function to verify API key and connection
async def test_deepgram_connection(api_key: str):
    async def dummy_callback(data):
        print(f"Test received: {data}")

    stream = DeepgramStream(api_key, dummy_callback)

    try:
        await stream.start()
        await asyncio.sleep(2)

        test_chunk = b"\x00" * 1000
        await stream.send_audio(test_chunk)

        await asyncio.sleep(3)
        print("✅ Deepgram connection test completed")

    except Exception as e:
        print(f"❌ Deepgram connection test failed: {e}")

    finally:
        await stream.flush_and_close()
