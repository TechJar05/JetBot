# JetBot/asgi.py
import os

# 1) Configure settings BEFORE any Django imports that touch models/auth/etc.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "JetBot.settings")

import django
django.setup()

# 2) Now safe to import Django/Channels stuff
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from django.conf import settings

# 3) Import your JWT WS middleware AFTER setup
from authentication.middleware import JWTAuthMiddleware

# 4) Import routing AFTER setup
import interview.routing

# Create base Django ASGI app
django_asgi_app = get_asgi_application()

# Base ASGI application (HTTP + WebSocket)
application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": JWTAuthMiddleware(
        URLRouter(interview.routing.websocket_urlpatterns)
    ),
})

# 5) Optionally mount static files (only in DEBUG)
if settings.DEBUG:
    from starlette.applications import Starlette
    from starlette.routing import Mount
    from starlette.staticfiles import StaticFiles

    application = Starlette(routes=[
        Mount("/static", app=StaticFiles(directory=settings.STATIC_ROOT), name="static"),
        Mount("", app=application),  # your Django/Channels app
    ])
