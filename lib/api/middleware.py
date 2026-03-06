import json
import time

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from lib.core.logging import setup_logging

logger = setup_logging(__name__)


async def log_request_middleware(
    request: Request, call_next: RequestResponseEndpoint
) -> Response:
    start_time = time.time()

    # Log request details
    request_body = None
    if request.method in ['POST', 'PUT', 'PATCH']:
        try:
            request_body = await request.body()
            # Decode if possible
            if request_body:
                request_body = json.loads(request_body)
        except Exception:
            pass
    logger.info(
        f'Incoming {request.method} {request.url.path}',
        extra={
            'method': request.method,
            'path': request.url.path,
            'query': str(request.url.query) if request.url.query else None,
            'request_body': request_body,
        },
    )

    try:
        response = await call_next(request)
        duration = time.time() - start_time

        # Log response details
        response_body = None
        if response.status_code < 500:
            try:
                response_body = response.body
                if response_body:
                    response_body = json.loads(response_body)
            except Exception:
                pass
        log_fn = logger.error if 500 <= response.status_code < 600 else logger.info
        log_fn(
            f'{request.method} {request.url.path} returned {response.status_code} ({duration:.3f}s)',
            extra={
                'method': request.method,
                'path': request.url.path,
                'status_code': response.status_code,
                'duration_seconds': duration,
                'response_body': response_body,
            },
        )
        return response
    except Exception as e:
        duration = time.time() - start_time
        logger.exception(
            f'Unhandled exception in {request.method} {request.url.path} ({duration:.3f}s)',
            extra={
                'method': request.method,
                'path': request.url.path,
                'duration_seconds': duration,
            },
        )
        # Return generic 500 response
        return JSONResponse(
            status_code=500,
            content={'detail': 'Internal server error'},
        )
