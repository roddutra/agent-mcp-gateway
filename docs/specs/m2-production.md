# Milestone 2: Production Readiness

**Status:** Not Started
**Target:** Production-grade gateway with HTTP transport, health checks, and robust error handling

---

## Overview

M2 transforms the gateway from a development tool to a production-ready service. This milestone adds:
- HTTP transport with Streamable HTTP/SSE support
- Health check endpoints for monitoring
- Comprehensive error handling with all defined error codes
- HTTP session management with session IDs
- Performance optimizations and monitoring
- Security hardening

**Key Success Metric:** Gateway can run as a production HTTP service with <100ms P95 latency, proper error handling, and monitoring capabilities.

---

## Core Components

### 1. HTTP Transport Implementation
### 2. Health Check Endpoints
### 3. Error Handling System
### 4. Session Management
### 5. Security Hardening
### 6. Performance Optimization

---

## Detailed Task Checklist

### HTTP Transport Setup

- [ ] Configure gateway for HTTP transport
  - [ ] Add HTTP transport support to gateway.run()
  - [ ] Configure host and port from environment variables
  - [ ] Support both stdio and HTTP concurrently (if needed)
  - [ ] Implement Streamable HTTP with SSE support
  - [ ] Add CORS handling for web clients

- [ ] Environment variable configuration
  - [ ] `GATEWAY_TRANSPORT` (stdio|http)
  - [ ] `GATEWAY_HTTP_HOST` (default: 127.0.0.1)
  - [ ] `GATEWAY_HTTP_PORT` (default: 8000)
  - [ ] `GATEWAY_CORS_ORIGINS` (comma-separated allowed origins)

- [ ] Test HTTP transport
  - [ ] Verify HTTP POST for sending messages
  - [ ] Verify SSE streaming for server messages
  - [ ] Test session creation and reuse
  - [ ] Test concurrent HTTP connections

**Code Reference:**
```python
# main.py updates
import os

def main():
    # ... existing setup ...

    # Configure transport
    transport = os.getenv("GATEWAY_TRANSPORT", "stdio")

    if transport == "http":
        host = os.getenv("GATEWAY_HTTP_HOST", "127.0.0.1")
        port = int(os.getenv("GATEWAY_HTTP_PORT", "8000"))

        # Run with HTTP transport
        gateway.run(
            transport="http",
            host=host,
            port=port
        )
    else:
        # Run with stdio transport (default)
        gateway.run()

if __name__ == "__main__":
    main()
```

**Documentation Reference:**
- FastMCP HTTP Transport - https://gofastmcp.com/servers/server#running-the-server
- MCP Streamable HTTP - https://modelcontextprotocol.io/specification/2025-06-18/basic/transports#streamable-http

### Health Check Endpoints

- [ ] Implement health check endpoint
  - [ ] Add `/health` endpoint using `@gateway.custom_route`
  - [ ] Return 200 OK with basic status
  - [ ] Include gateway version info
  - [ ] Check downstream server connectivity (optional)

- [ ] Implement readiness check endpoint
  - [ ] Add `/ready` endpoint
  - [ ] Verify all proxy connections are initialized
  - [ ] Return 503 if not ready
  - [ ] Return 200 when ready

- [ ] Implement metrics endpoint
  - [ ] Add `/metrics` endpoint
  - [ ] Return metrics in JSON format
  - [ ] Include operation counts, latencies, error rates
  - [ ] Support Prometheus format (optional)

**Code Reference:**
```python
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
import time

# Store startup time
STARTUP_TIME = time.time()

@gateway.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """Basic health check endpoint."""
    return JSONResponse({
        "status": "healthy",
        "service": "agent-mcp-gateway",
        "version": "1.0.0",
        "uptime_seconds": time.time() - STARTUP_TIME
    })

@gateway.custom_route("/ready", methods=["GET"])
async def readiness_check(request: Request) -> JSONResponse:
    """Readiness check - verifies gateway is ready to serve requests."""
    # Get proxy clients from state
    # In production, you'd store this in a way accessible to routes
    proxy_clients = getattr(gateway, "_proxy_clients", {})

    if not proxy_clients:
        return JSONResponse(
            {"status": "not_ready", "reason": "no_proxy_clients"},
            status_code=503
        )

    return JSONResponse({
        "status": "ready",
        "servers_configured": len(proxy_clients)
    })

@gateway.custom_route("/metrics", methods=["GET"])
async def metrics_endpoint(request: Request) -> JSONResponse:
    """Metrics endpoint for monitoring."""
    metrics_collector = getattr(gateway, "_metrics_collector", None)

    if not metrics_collector:
        return JSONResponse({"error": "metrics not available"}, status_code=503)

    summary = metrics_collector.get_summary()

    return JSONResponse({
        "timestamp": time.time(),
        "operations": summary,
        "uptime_seconds": time.time() - STARTUP_TIME
    })
```

**Documentation Reference:**
- FastMCP Custom Routes - https://gofastmcp.com/servers/server#custom-routes

### Comprehensive Error Handling

- [ ] Define error code constants
  - [ ] `DENIED_BY_POLICY` (-32000)
  - [ ] `SERVER_UNAVAILABLE` (-32001)
  - [ ] `TOOL_NOT_FOUND` (-32002)
  - [ ] `INVALID_AGENT_ID` (-32003)
  - [ ] `TIMEOUT` (-32004)

- [ ] Implement custom exception classes
  - [ ] `DeniedByPolicyError` with rule reference
  - [ ] `ServerUnavailableError` with server name
  - [ ] `ToolNotFoundError` with tool and server
  - [ ] `InvalidAgentIdError` with validation details
  - [ ] `TimeoutError` with duration info

- [ ] Update all tools to use error codes
  - [ ] Standardize error responses
  - [ ] Include helpful error messages
  - [ ] Add rule references for policy denials
  - [ ] Log all errors appropriately

- [ ] Add error response formatting
  - [ ] Consistent JSON structure
  - [ ] Include error code, message, data
  - [ ] Support MCP error format

**Code Reference:**
```python
# src/errors.py
from fastmcp.exceptions import ToolError

class GatewayError(ToolError):
    """Base class for gateway errors."""
    code: int = -32000

class DeniedByPolicyError(GatewayError):
    """Raised when operation is denied by policy."""
    code = -32000

    def __init__(self, agent_id: str, operation: str, rule: str):
        self.agent_id = agent_id
        self.operation = operation
        self.rule = rule
        super().__init__(
            f"Agent '{agent_id}' denied {operation}",
            data={
                "code": "DENIED_BY_POLICY",
                "agent_id": agent_id,
                "operation": operation,
                "rule": rule
            }
        )

class ServerUnavailableError(GatewayError):
    """Raised when downstream server is unavailable."""
    code = -32001

    def __init__(self, server: str, reason: str = ""):
        self.server = server
        self.reason = reason
        super().__init__(
            f"Server '{server}' is unavailable" + (f": {reason}" if reason else ""),
            data={
                "code": "SERVER_UNAVAILABLE",
                "server": server,
                "reason": reason
            }
        )

class ToolNotFoundError(GatewayError):
    """Raised when requested tool doesn't exist."""
    code = -32002

    def __init__(self, tool: str, server: str):
        self.tool = tool
        self.server = server
        super().__init__(
            f"Tool '{tool}' not found on server '{server}'",
            data={
                "code": "TOOL_NOT_FOUND",
                "tool": tool,
                "server": server
            }
        )

class InvalidAgentIdError(GatewayError):
    """Raised when agent_id is invalid or missing."""
    code = -32003

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(
            f"Invalid agent_id: {reason}",
            data={
                "code": "INVALID_AGENT_ID",
                "reason": reason
            }
        )

class GatewayTimeoutError(GatewayError):
    """Raised when operation times out."""
    code = -32004

    def __init__(self, operation: str, timeout_ms: int):
        self.operation = operation
        self.timeout_ms = timeout_ms
        super().__init__(
            f"Operation '{operation}' timed out after {timeout_ms}ms",
            data={
                "code": "TIMEOUT",
                "operation": operation,
                "timeout_ms": timeout_ms
            }
        )
```

- [ ] Update tools to use new error classes
  - [ ] Replace generic exceptions with specific errors
  - [ ] Include all required context in errors
  - [ ] Test error responses

### Session Management

- [ ] Implement HTTP session tracking
  - [ ] Generate secure session IDs (UUID4)
  - [ ] Store session state (agent_id, created_at, last_used)
  - [ ] Return `Mcp-Session-Id` header on initialization
  - [ ] Validate `Mcp-Session-Id` on subsequent requests
  - [ ] Support session termination via DELETE

- [ ] Add session timeout
  - [ ] Configure session TTL (default: 1 hour)
  - [ ] Clean up expired sessions
  - [ ] Return 404 for expired sessions

- [ ] Implement session storage
  - [ ] In-memory session store
  - [ ] Thread-safe access
  - [ ] Support session persistence (optional)

**Code Reference:**
```python
# src/session.py
import uuid
from datetime import datetime, timedelta
from typing import Dict, Optional
import threading

class Session:
    def __init__(self, session_id: str, agent_id: str = ""):
        self.session_id = session_id
        self.agent_id = agent_id
        self.created_at = datetime.utcnow()
        self.last_used = datetime.utcnow()
        self.data = {}

    def touch(self):
        """Update last used timestamp."""
        self.last_used = datetime.utcnow()

    def is_expired(self, ttl_seconds: int) -> bool:
        """Check if session has expired."""
        return (datetime.utcnow() - self.last_used).total_seconds() > ttl_seconds

class SessionManager:
    """Manage HTTP sessions for the gateway."""

    def __init__(self, ttl_seconds: int = 3600):
        self.sessions: Dict[str, Session] = {}
        self.ttl_seconds = ttl_seconds
        self._lock = threading.Lock()

    def create_session(self, agent_id: str = "") -> Session:
        """Create a new session."""
        session_id = str(uuid.uuid4())
        session = Session(session_id, agent_id)

        with self._lock:
            self.sessions[session_id] = session

        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """Get session by ID."""
        with self._lock:
            session = self.sessions.get(session_id)

            if session:
                if session.is_expired(self.ttl_seconds):
                    del self.sessions[session_id]
                    return None

                session.touch()

            return session

    def delete_session(self, session_id: str):
        """Delete a session."""
        with self._lock:
            self.sessions.pop(session_id, None)

    def cleanup_expired(self):
        """Remove all expired sessions."""
        with self._lock:
            expired = [
                sid for sid, session in self.sessions.items()
                if session.is_expired(self.ttl_seconds)
            ]
            for sid in expired:
                del self.sessions[sid]
```

**Documentation Reference:**
- MCP Session Management - https://modelcontextprotocol.io/specification/2025-06-18/basic/transports#session-management

### Security Hardening

- [ ] Implement Origin validation for HTTP
  - [ ] Validate `Origin` header on all HTTP requests
  - [ ] Prevent DNS rebinding attacks
  - [ ] Configure allowed origins via environment

- [ ] Add rate limiting (optional)
  - [ ] Limit requests per agent per minute
  - [ ] Return 429 Too Many Requests when exceeded
  - [ ] Configurable rate limits

- [ ] Secure session IDs
  - [ ] Use cryptographically secure random generation
  - [ ] Validate session ID format
  - [ ] Prevent session fixation attacks

- [ ] Add request validation
  - [ ] Validate all input parameters
  - [ ] Sanitize error messages
  - [ ] Prevent information leakage

**Code Reference:**
```python
# src/security.py
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

class OriginValidationMiddleware(BaseHTTPMiddleware):
    """Validate Origin header to prevent DNS rebinding attacks."""

    def __init__(self, app, allowed_origins: list[str]):
        super().__init__(app)
        self.allowed_origins = set(allowed_origins)

    async def dispatch(self, request, call_next):
        origin = request.headers.get("origin")

        # If running locally, only allow localhost
        if request.url.hostname in ["127.0.0.1", "localhost"]:
            if origin and not origin.startswith("http://localhost") \
                    and not origin.startswith("http://127.0.0.1"):
                return JSONResponse(
                    {"error": "Invalid origin for local server"},
                    status_code=403
                )

        # For remote servers, validate against allowed origins
        elif origin and origin not in self.allowed_origins:
            return JSONResponse(
                {"error": "Origin not allowed"},
                status_code=403
            )

        response = await call_next(request)
        return response
```

### Performance Optimization

- [ ] Implement connection pooling
  - [ ] Reuse ProxyClient connections when safe
  - [ ] Configure pool size limits
  - [ ] Monitor pool utilization

- [ ] Add caching layer
  - [ ] Cache get_server_tools results (short TTL)
  - [ ] Cache policy evaluations
  - [ ] Invalidate on configuration changes

- [ ] Optimize policy evaluation
  - [ ] Pre-compile wildcard patterns
  - [ ] Cache policy decisions
  - [ ] Index rules for faster lookup

- [ ] Add performance monitoring
  - [ ] Track operation durations
  - [ ] Identify slow operations
  - [ ] Alert on performance degradation

**Code Reference:**
```python
# src/cache.py
from typing import Any, Optional
from datetime import datetime, timedelta
import hashlib
import json

class Cache:
    """Simple TTL-based cache."""

    def __init__(self, ttl_seconds: int = 60):
        self.ttl_seconds = ttl_seconds
        self._cache = {}

    def _make_key(self, *args, **kwargs) -> str:
        """Generate cache key from arguments."""
        data = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True)
        return hashlib.md5(data.encode()).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired."""
        if key in self._cache:
            value, expires_at = self._cache[key]
            if datetime.utcnow() < expires_at:
                return value
            else:
                del self._cache[key]
        return None

    def set(self, key: str, value: Any):
        """Store value in cache with TTL."""
        expires_at = datetime.utcnow() + timedelta(seconds=self.ttl_seconds)
        self._cache[key] = (value, expires_at)

    def clear(self):
        """Clear all cache entries."""
        self._cache.clear()
```

### Integration & Testing

- [ ] Update main.py for production
  - [ ] Add HTTP transport configuration
  - [ ] Initialize session manager
  - [ ] Add security middleware
  - [ ] Configure health check endpoints
  - [ ] Add graceful shutdown handling

- [ ] Create HTTP integration tests
  - [ ] Test HTTP POST for tool calls
  - [ ] Test SSE streaming
  - [ ] Test session management
  - [ ] Test health check endpoints
  - [ ] Test error responses

- [ ] Performance testing
  - [ ] Load test with multiple concurrent clients
  - [ ] Verify P95 latency <100ms
  - [ ] Test under sustained load
  - [ ] Monitor memory usage

- [ ] Security testing
  - [ ] Test Origin validation
  - [ ] Test session security
  - [ ] Test rate limiting (if implemented)
  - [ ] Verify no information leakage in errors

**Code Reference:**
```python
# tests/test_http.py
import httpx
import pytest

@pytest.mark.asyncio
async def test_http_transport():
    """Test gateway over HTTP transport."""

    base_url = "http://127.0.0.1:8000"

    async with httpx.AsyncClient() as client:
        # Test health check
        response = await client.get(f"{base_url}/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

        # Test initialize (MCP protocol)
        response = await client.post(
            base_url,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1.0.0"}
                }
            },
            headers={"Accept": "application/json"}
        )
        assert response.status_code == 200
        result = response.json()["result"]

        # Get session ID
        session_id = response.headers.get("Mcp-Session-Id")
        assert session_id is not None

        # Test tool call with session
        response = await client.post(
            base_url,
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "list_servers",
                    "arguments": {"agent_id": "researcher"}
                }
            },
            headers={
                "Mcp-Session-Id": session_id,
                "Accept": "application/json"
            }
        )
        assert response.status_code == 200
```

---

## Success Criteria

### Functional Requirements
- [ ] Gateway runs as HTTP service
- [ ] Health check endpoints respond correctly
- [ ] All error codes implemented and tested
- [ ] Session management works correctly
- [ ] Security validations in place

### Performance Requirements
- [ ] P95 latency <100ms for all operations
- [ ] Handle 100+ concurrent connections
- [ ] No memory leaks under sustained load
- [ ] Graceful degradation under high load

### Security Requirements
- [ ] Origin validation prevents DNS rebinding
- [ ] Session IDs are cryptographically secure
- [ ] No sensitive information in error messages
- [ ] Rate limiting prevents abuse (if implemented)

### Operational Requirements
- [ ] Health checks enable monitoring
- [ ] Metrics expose operational insights
- [ ] Logs are structured and parseable
- [ ] Graceful shutdown handling

---

## Performance Targets

| Metric | Target | Measurement |
|--------|--------|-------------|
| HTTP request latency | <100ms (P95) | End-to-end including downstream |
| Gateway overhead | <30ms (P95) | Gateway processing only |
| Concurrent connections | 100+ | Simultaneous active connections |
| Session lookup | <1ms | Session retrieval from store |

---

## Dependencies

**External:**
- FastMCP 2.13.0.1+
- httpx (for testing)
- Starlette (included with FastMCP)

**Internal:**
- M0 (Foundation) - Config, policy, audit
- M1 (Core) - All three gateway tools, middleware

---

## Documentation References

- **MCP Streamable HTTP:** https://modelcontextprotocol.io/specification/2025-06-18/basic/transports#streamable-http
- **MCP Session Management:** https://modelcontextprotocol.io/specification/2025-06-18/basic/transports#session-management
- **FastMCP Custom Routes:** https://gofastmcp.com/servers/server#custom-routes
- **FastMCP HTTP Transport:** https://gofastmcp.com/servers/server#running-the-server

---

## Notes

- HTTP transport is critical for remote access and multi-client scenarios
- Session management enables stateful interactions over HTTP
- Security is paramount - Origin validation prevents DNS rebinding attacks
- Health checks are essential for production monitoring
- Performance optimization should be data-driven based on actual usage patterns
- Consider implementing Prometheus metrics format for better monitoring integration
