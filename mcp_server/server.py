"""
MCP Server for chatbot-tester.

Remote MCP server with HTTP/SSE transport for exposing chatbot-tester
functionality to Claude Desktop clients.

Usage:
    python mcp_server/server.py

Environment:
    MCP_API_KEY: API key for authentication
    CIRCLECI_TOKEN: CircleCI API token
    PORT: Server port (default: 8080)
"""

import os
import sys
import logging
import base64
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


def setup_google_credentials():
    """
    Write Google credentials from environment variables to disk.
    Credentials are stored as base64-encoded secrets in Fly.io.

    Supports two modes:
    1. Service Account (PREFERRED): GOOGLE_SERVICE_ACCOUNT_B64
       - No token needed, no expiration
       - Write to oauth_credentials.json (auto-detected by sheets_client)

    2. OAuth (LEGACY): GOOGLE_OAUTH_B64 + GOOGLE_TOKEN_B64
       - Requires periodic token refresh
       - May expire if not used
    """
    config_dir = Path(__file__).parent.parent / "config"
    config_dir.mkdir(exist_ok=True)

    # PREFERRED: Service Account credentials (no expiration)
    sa_b64 = os.environ.get("GOOGLE_SERVICE_ACCOUNT_B64")
    if sa_b64:
        # Write to oauth_credentials.json - sheets_client auto-detects type
        sa_path = config_dir / "oauth_credentials.json"
        sa_path.write_bytes(base64.b64decode(sa_b64))
        logging.info(f"Google Service Account credentials written to {sa_path}")
        return  # Service Account doesn't need token.json

    # LEGACY: OAuth credentials + token
    # Decode and write token.json
    token_b64 = os.environ.get("GOOGLE_TOKEN_B64")
    if token_b64:
        token_path = config_dir / "token.json"
        token_path.write_bytes(base64.b64decode(token_b64))
        logging.info(f"Google token written to {token_path}")

    # Decode and write oauth_credentials.json
    oauth_b64 = os.environ.get("GOOGLE_OAUTH_B64")
    if oauth_b64:
        oauth_path = config_dir / "oauth_credentials.json"
        oauth_path.write_bytes(base64.b64decode(oauth_b64))
        logging.info(f"Google OAuth credentials written to {oauth_path}")


# Setup credentials before importing tools (which may need them)
setup_google_credentials()

from mcp.server import Server
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.responses import JSONResponse
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
import uvicorn

from mcp_server import __version__
from mcp_server.tools import register_tools
from mcp_server.auth import APIKeyMiddleware

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create MCP server
mcp_server = Server("chatbot-tester")

# Register tools
register_tools(mcp_server)

# Create SSE transport - must be created once and reused
sse_transport = SseServerTransport("/messages/")


async def health_check(request):
    """Health check endpoint."""
    return JSONResponse({
        "status": "healthy",
        "service": "chatbot-tester-mcp",
        "version": __version__
    })


async def oauth_discovery(request):
    """OAuth discovery endpoint - returns 404 as we don't support OAuth."""
    return JSONResponse(
        status_code=404,
        content={"error": "OAuth not supported", "message": "This server uses API key authentication"}
    )


async def handle_sse(scope, receive, send):
    """Raw ASGI handler for SSE endpoint."""
    logger.info("SSE connection initiated")

    async with sse_transport.connect_sse(scope, receive, send) as streams:
        await mcp_server.run(
            streams[0],  # read stream
            streams[1],  # write stream
            mcp_server.create_initialization_options()
        )


class MCPApp:
    """Custom ASGI app that routes to Starlette or SSE handler."""

    def __init__(self, starlette_app):
        self.starlette_app = starlette_app

    async def __call__(self, scope, receive, send):
        """Route requests to appropriate handler."""
        if scope["type"] == "http":
            path = scope.get("path", "")
            method = scope.get("method", "")

            # Route GET /sse to raw ASGI handler for SSE connection
            # POST requests should go to /messages/ (handled by Starlette)
            if path == "/sse" and method == "GET":
                # Check API key authentication
                api_key = os.environ.get("MCP_API_KEY")
                if api_key:
                    headers = dict(scope.get("headers", []))
                    auth_header = headers.get(b"authorization", b"").decode()
                    if not auth_header.startswith("Bearer ") or auth_header[7:] != api_key:
                        # Send 401 Unauthorized
                        await send({
                            "type": "http.response.start",
                            "status": 401,
                            "headers": [[b"content-type", b"application/json"]],
                        })
                        await send({
                            "type": "http.response.body",
                            "body": b'{"error":"Unauthorized"}',
                        })
                        return
                await handle_sse(scope, receive, send)
                return
        # Everything else goes to Starlette
        await self.starlette_app(scope, receive, send)


# Build the Starlette app for other routes
routes = [
    Route("/health", health_check, methods=["GET"]),
    Route("/.well-known/oauth-authorization-server", oauth_discovery, methods=["GET"]),
    # Mount the SSE transport's message handler
    Mount("/messages", app=sse_transport.handle_post_message),
]

middleware = [
    Middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    ),
    Middleware(APIKeyMiddleware),
]

starlette_app = Starlette(
    routes=routes,
    middleware=middleware,
    debug=os.environ.get("DEBUG", "false").lower() == "true"
)

# Wrap with MCPApp for SSE routing
app = MCPApp(starlette_app)


def main():
    """Run the MCP server."""
    port = int(os.environ.get("PORT", 8080))
    host = os.environ.get("HOST", "0.0.0.0")

    logger.info(f"Starting chatbot-tester MCP server on {host}:{port}")
    logger.info(f"SSE endpoint: http://{host}:{port}/sse")

    # Check required environment variables
    if not os.environ.get("CIRCLECI_TOKEN"):
        logger.warning("CIRCLECI_TOKEN not set - CircleCI tools will not work")

    if not os.environ.get("MCP_API_KEY"):
        logger.warning("MCP_API_KEY not set - API will be open (not recommended for production)")

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info"
    )


if __name__ == "__main__":
    main()
