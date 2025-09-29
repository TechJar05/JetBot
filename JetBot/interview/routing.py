# interview/routing.py
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r"ws/interview/(?P<interview_id>\d+)/$", consumers.InterviewConsumer.as_asgi()),
]
