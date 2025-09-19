# your_project_name/asgi.py
import os
import django
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "JetBot.settings")
django.setup()

import interview.routing  

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(
            interview.routing.websocket_urlpatterns
        )
    ),
})

# uvicorn JetBot.asgi:application --port 8000 --reload