# JetBot/asgi.py
import os
import django
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from django.conf import settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "JetBot.settings")
django.setup()

import interview.routing
from authentication.middleware import JWTAuthMiddleware  # <-- use your JWT WS middleware

django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": JWTAuthMiddleware(          # <-- swap here
        URLRouter(interview.routing.websocket_urlpatterns)
    ),
})
