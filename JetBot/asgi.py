# JetBot/asgi.py
import os
import django
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.core.asgi import get_asgi_application
from starlette.staticfiles import StaticFiles
from django.conf import settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "JetBot.settings")
django.setup()

import interview.routing  

# Django ASGI app
django_asgi_app = get_asgi_application()

# Protocol Router
application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(
            interview.routing.websocket_urlpatterns
        )
    ),
})

# Mount static files for ASGI
if settings.DEBUG:  # serve static only in dev
    from starlette.applications import Starlette
    from starlette.routing import Mount

    application = Starlette(routes=[
        Mount("/static", app=StaticFiles(directory=settings.STATIC_ROOT), name="static"),
        Mount("", app=application),  # your Django/Channels app
    ])
