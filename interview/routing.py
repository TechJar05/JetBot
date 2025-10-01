# interview/routing.py
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # TTS WebSocket: asks questions via ElevenLabs
    re_path(r'ws/tts/(?P<interview_id>\d+)/$', consumers.TTSConsumer.as_asgi()),

    # STT WebSocket: records answers via AssemblyAI
    re_path(r'ws/stt/(?P<interview_id>\d+)/$', consumers.STTConsumer.as_asgi()),
]
