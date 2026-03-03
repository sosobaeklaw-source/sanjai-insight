"""
Security Middleware
CORS, CSP headers, HMAC verification for webhooks.
"""

import hashlib
import hmac
import os
from typing import Optional

from fastapi import Request, Response
from fastapi.responses import JSONResponse


def create_security_headers_middleware():
    """Create middleware for security headers"""

    async def security_headers_middleware(request: Request, call_next):
        response: Response = await call_next(request)

        # Content Security Policy
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self' data:; "
            "connect-src 'self' https://api.telegram.org; "
            "frame-ancestors 'none';"
        )

        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

        # HSTS (only in production with HTTPS)
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        return response

    return security_headers_middleware


def create_cors_middleware(
    allow_origins: list[str] = None,
    allow_methods: list[str] = None,
    allow_headers: list[str] = None
):
    """Create CORS middleware with configurable origins"""

    if allow_origins is None:
        allow_origins = ["*"]  # Override in production

    if allow_methods is None:
        allow_methods = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]

    if allow_headers is None:
        allow_headers = ["*"]

    async def cors_middleware(request: Request, call_next):
        # Handle preflight
        if request.method == "OPTIONS":
            return Response(
                status_code=200,
                headers={
                    "Access-Control-Allow-Origin": ", ".join(allow_origins),
                    "Access-Control-Allow-Methods": ", ".join(allow_methods),
                    "Access-Control-Allow-Headers": ", ".join(allow_headers),
                    "Access-Control-Max-Age": "3600"
                }
            )

        # Process request
        response: Response = await call_next(request)

        # Add CORS headers
        response.headers["Access-Control-Allow-Origin"] = ", ".join(allow_origins)
        response.headers["Access-Control-Allow-Credentials"] = "true"

        return response

    return cors_middleware


class TelegramWebhookVerifier:
    """Verify Telegram webhook requests using HMAC"""

    def __init__(self, bot_token: Optional[str] = None):
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")

        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN not configured")

    def verify_signature(self, request_body: bytes, signature_header: str) -> bool:
        """
        Verify Telegram webhook signature.

        Args:
            request_body: Raw request body
            signature_header: X-Telegram-Bot-Api-Secret-Token header value

        Returns:
            True if signature is valid
        """
        if not signature_header:
            return False

        # Compute expected signature
        expected = hmac.new(
            self.bot_token.encode("utf-8"),
            request_body,
            hashlib.sha256
        ).hexdigest()

        # Compare signatures (constant time)
        return hmac.compare_digest(signature_header, expected)

    def create_middleware(self, webhook_path: str = "/telegram/webhook"):
        """Create FastAPI middleware for webhook verification"""

        async def telegram_webhook_middleware(request: Request, call_next):
            # Only verify webhook endpoints
            if not request.url.path.startswith(webhook_path):
                return await call_next(request)

            # Get signature header
            signature = request.headers.get("X-Telegram-Bot-Api-Secret-Token")

            if not signature:
                return JSONResponse(
                    status_code=401,
                    content={"error": "Missing signature header"}
                )

            # Read body
            body = await request.body()

            # Verify signature
            if not self.verify_signature(body, signature):
                return JSONResponse(
                    status_code=403,
                    content={"error": "Invalid signature"}
                )

            # Signature valid - process request
            return await call_next(request)

        return telegram_webhook_middleware


def create_request_logging_middleware():
    """Create middleware for request logging"""
    import logging

    logger = logging.getLogger("security")

    async def request_logging_middleware(request: Request, call_next):
        # Log request
        client_ip = request.client.host if request.client else "unknown"
        logger.info(
            "Request: %s %s from %s",
            request.method,
            request.url.path,
            client_ip
        )

        # Process request
        response: Response = await call_next(request)

        # Log response
        logger.info(
            "Response: %s %s -> %d",
            request.method,
            request.url.path,
            response.status_code
        )

        return response

    return request_logging_middleware


def verify_internal_request(request: Request, shared_secret: Optional[str] = None) -> bool:
    """
    Verify internal service-to-service requests.

    Args:
        request: FastAPI request
        shared_secret: Shared secret for HMAC (from env if not provided)

    Returns:
        True if request is from trusted internal service
    """
    shared_secret = shared_secret or os.getenv("INTERNAL_SHARED_SECRET")

    if not shared_secret:
        return False

    # Get signature from header
    signature = request.headers.get("X-Internal-Signature")
    if not signature:
        return False

    # Get request body
    body = request.state.body if hasattr(request.state, "body") else b""

    # Compute expected signature
    expected = hmac.new(
        shared_secret.encode("utf-8"),
        body,
        hashlib.sha256
    ).hexdigest()

    # Compare
    return hmac.compare_digest(signature, expected)


def create_internal_auth_middleware(shared_secret: Optional[str] = None):
    """Create middleware for internal service authentication"""

    async def internal_auth_middleware(request: Request, call_next):
        # Only apply to /internal/* endpoints
        if not request.url.path.startswith("/internal/"):
            return await call_next(request)

        # Store body in state for verification
        request.state.body = await request.body()

        # Verify request
        if not verify_internal_request(request, shared_secret):
            return JSONResponse(
                status_code=403,
                content={"error": "Forbidden: Invalid internal authentication"}
            )

        # Authenticated - process request
        return await call_next(request)

    return internal_auth_middleware


class SecurityMiddlewareStack:
    """Combine all security middlewares"""

    def __init__(
        self,
        enable_rate_limiting: bool = True,
        enable_cors: bool = True,
        enable_security_headers: bool = True,
        enable_telegram_verification: bool = True,
        enable_request_logging: bool = True,
        cors_origins: list[str] = None,
        telegram_webhook_path: str = "/telegram/webhook"
    ):
        self.middlewares = []

        if enable_request_logging:
            self.middlewares.append(create_request_logging_middleware())

        if enable_rate_limiting:
            from .rate_limiter import create_rate_limit_middleware
            self.middlewares.append(create_rate_limit_middleware())

        if enable_security_headers:
            self.middlewares.append(create_security_headers_middleware())

        if enable_cors:
            self.middlewares.append(create_cors_middleware(allow_origins=cors_origins))

        if enable_telegram_verification:
            verifier = TelegramWebhookVerifier()
            self.middlewares.append(verifier.create_middleware(telegram_webhook_path))

    def apply_to_app(self, app):
        """Apply all middlewares to FastAPI app"""
        from fastapi.middleware.base import BaseHTTPMiddleware

        for middleware in reversed(self.middlewares):  # Apply in reverse order
            app.middleware("http")(middleware)
