# JetBot/asgi.py
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "JetBot.settings")

import django
django.setup()

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from django.conf import settings
from authentication.middleware import JWTAuthMiddleware
import interview.routing

django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": JWTAuthMiddleware(
        URLRouter(interview.routing.websocket_urlpatterns)
    ),
})

# Optional: serve static in DEBUG
if settings.DEBUG:
    from starlette.applications import Starlette
    from starlette.routing import Mount
    from starlette.staticfiles import StaticFiles

    application = Starlette(routes=[
        Mount("/static", app=StaticFiles(directory=settings.STATIC_ROOT), name="static"),
        Mount("", app=application),
    ])
# uvicorn JetBot.asgi:application --port 8000 --reload  