"""Per-request current-user context.

Lets deeply-nested LLM/embedding call sites (notably the copilot realtime
subsystem) resolve the right user's provider config without threading a
user_id through every signature. Set once at a request/connection boundary;
provider functions read it as a fallback when no explicit user_id is passed.

Each HTTP request / websocket connection serves exactly one user, and
asyncio.create_task / to_thread copy the context, so there is no cross-user
leakage.
"""

import contextvars

_current_user_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_user_id", default=None
)


def set_current_user(user_id: str | None):
    """Bind the current user for this context. Returns the token for reset()."""
    return _current_user_id.set(user_id)

def reset_current_user(token) -> None:
    _current_user_id.reset(token)


def get_current_user_id() -> str | None:
    return _current_user_id.get()


class CurrentUserMiddleware:
    """ASGI middleware that binds the request's authenticated user into the
    contextvar, so per-user provider resolvers work without threading user_id
    through every call site. Best-effort — a missing/invalid token leaves it unset.

    WebSocket connections set the user explicitly in their handler (the bearer
    token arrives out-of-band), so this only needs to cover plain HTTP."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        from backend.auth import decode_token

        uid = None
        for key, value in scope.get("headers", []):
            if key == b"authorization":
                parts = value.decode("latin-1").split(" ", 1)
                if len(parts) == 2 and parts[0].lower() == "bearer":
                    uid = decode_token(parts[1])
                break
        token = set_current_user(uid) if uid else None
        try:
            await self.app(scope, receive, send)
        finally:
            if token is not None:
                reset_current_user(token)
