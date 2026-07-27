import json
import logging
import time
from typing import Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.responses import Response

# Request-body keys whose values must never be logged. Matched as substrings so
# `current_password` / `new_password` are covered alongside `password`.
_REDACTED = '***'
_SENSITIVE_TOKENS = ('password',)


def _redact_sensitive(value: object) -> object:
    """Recursively mask any field whose key looks like a credential."""
    if isinstance(value, dict):
        return {
            key: _REDACTED
            if isinstance(key, str)
            and any(token in key.lower() for token in _SENSITIVE_TOKENS)
            else _redact_sensitive(val)
            for key, val in value.items()
        }
    if isinstance(value, list):
        return [_redact_sensitive(item) for item in value]
    return value


def make_log_request_middleware(logger: logging.Logger) -> Callable:
    async def log_request_middleware(request: Request, call_next: Callable) -> Response:
        start = time.time()

        # --- Read request body safely ---
        body_bytes = await request.body()
        request_body = None
        if body_bytes and request.headers.get('content-type', '').startswith(
            'application/json'
        ):
            try:
                request_body = json.loads(body_bytes)
            except Exception:
                request_body = '<invalid json>'

        if request_body is not None:
            request_body_str = str(_redact_sensitive(request_body))
        else:
            request_body_str = None

        # Log request start
        logger.info(
            'request_started method=%s path=%s query=%s request_body=%s',
            request.method,
            request.url.path,
            str(request.url.query) or None,
            request_body_str,
        )

        try:
            response = await call_next(request)

        except Exception:
            duration = time.time() - start
            logger.exception(
                'request_failed method=%s path=%s duration_seconds=%.3f',
                request.method,
                request.url.path,
                duration,
            )
            return JSONResponse(
                status_code=500,
                content={'detail': 'Internal server error'},
            )

        # Log request completion
        duration = time.time() - start
        log_level = logging.ERROR if response.status_code >= 500 else logging.INFO
        logger.log(
            log_level,
            'request_completed method=%s path=%s status_code=%d duration_seconds=%.3f',
            request.method,
            request.url.path,
            response.status_code,
            duration,
        )

        return response

    return log_request_middleware
