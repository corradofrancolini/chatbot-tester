"""
Authentication middleware for MCP server.

Simple API key authentication using Bearer tokens.
"""

import os
import logging
import secrets
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# Endpoints that don't require authentication
PUBLIC_PATHS = {
    "/health",
    "/",
    "/.well-known/oauth-authorization-server",  # OAuth discovery (mcp-remote checks this)
}


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Middleware for API key authentication."""

    async def dispatch(self, request, call_next):
        """Check API key for protected endpoints."""
        path = request.url.path

        # Allow public paths
        if path in PUBLIC_PATHS:
            return await call_next(request)

        # Get expected API key from environment
        expected_key = os.environ.get("MCP_API_KEY")

        # If no API key configured, allow all (development mode)
        if not expected_key:
            logger.warning("MCP_API_KEY not set - allowing unauthenticated access")
            return await call_next(request)

        # Get Authorization header
        auth_header = request.headers.get("Authorization", "")

        # Check Bearer token
        if auth_header.startswith("Bearer "):
            provided_key = auth_header[7:]  # Remove "Bearer " prefix

            # Constant-time comparison to prevent timing attacks
            if secrets.compare_digest(provided_key, expected_key):
                return await call_next(request)

        # Unauthorized
        logger.warning(f"Unauthorized access attempt from {request.client.host} to {path}")
        return JSONResponse(
            status_code=401,
            content={"error": "Unauthorized", "message": "Invalid or missing API key"}
        )


def generate_api_key(length: int = 32) -> str:
    """
    Generate a secure random API key.

    Args:
        length: Number of characters (default: 32)

    Returns:
        Random hex string
    """
    return secrets.token_hex(length // 2)


def validate_api_key(key: str) -> bool:
    """
    Validate an API key format.

    Args:
        key: API key to validate

    Returns:
        True if valid format
    """
    if not key:
        return False

    # Should be hex string of reasonable length
    if len(key) < 16 or len(key) > 128:
        return False

    try:
        int(key, 16)
        return True
    except ValueError:
        return False


if __name__ == "__main__":
    # Generate a new API key when run directly
    key = generate_api_key()
    print(f"Generated API key: {key}")
    print(f"\nTo use, set environment variable:")
    print(f"  export MCP_API_KEY=\"{key}\"")
