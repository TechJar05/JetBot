# authentication/middleware.py
from urllib.parse import parse_qs
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from channels.db import database_sync_to_async
from rest_framework_simplejwt.tokens import UntypedToken

User = get_user_model()

@database_sync_to_async
def get_user_from_id(user_id):
    try:
        return User.objects.get(id=user_id)
    except User.DoesNotExist:
        return AnonymousUser()

class JWTAuthMiddleware:
    """Minimal JWT middleware for Channels (no BaseMiddleware dependency)."""
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        # read ?token=... from query string
        token = None
        try:
            qs = parse_qs(scope.get("query_string", b"").decode())
            token = (qs.get("token") or [None])[0]
        except Exception:
            token = None

        scope["user"] = AnonymousUser()
        if token:
            try:
                untyped = UntypedToken(token)        # validates signature & expiry
                payload = untyped.payload
                user_id = payload.get("user_id")
                if user_id is not None:
                    scope["user"] = await get_user_from_id(user_id)
            except Exception:
                scope["user"] = AnonymousUser()

        return await self.inner(scope, receive, send)
