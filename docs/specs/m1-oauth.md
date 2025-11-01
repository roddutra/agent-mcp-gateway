# Milestone: OAuth Support for Downstream MCPs

**Status:** 📋 Planned
**Priority:** High
**Complexity:** Medium
**Estimated Effort:** 4-8 hours

## Overview

Enable agent-mcp-gateway to transparently proxy to OAuth-protected downstream MCP servers (e.g., Notion MCP, GitHub MCP) by leveraging FastMCP's built-in OAuth support and the MCP protocol's automatic OAuth discovery mechanism.

**Key Insight:** The MCP protocol uses auto-detection for OAuth via HTTP 401 responses. We don't need to know ahead of time which servers require OAuth - the server signals this to the client automatically.

---

## Implementation Checklist

### Phase 1: Core OAuth Support

- [ ] **Update ProxyManager Client Creation** (`src/proxy.py`)
  - [ ] Modify `_create_client()` method to enable OAuth for HTTP clients
  - [ ] Add logic: if `"url"` in server_config, pass `auth="oauth"` to Client
  - [ ] Keep stdio clients unchanged (no OAuth for local processes)
  - [ ] Test with mixed config (HTTP + stdio servers)

- [ ] **Test OAuth Auto-Detection**
  - [ ] Create test `.mcp.json` with OAuth-protected server
  - [ ] Verify 401 response triggers OAuth flow
  - [ ] Verify browser opens for authentication
  - [ ] Verify tokens cached in `~/.fastmcp/oauth-mcp-client-cache/`
  - [ ] Verify subsequent runs use cached tokens (no browser)

- [ ] **Test Mixed Authentication Scenarios**
  - [ ] Configure both stdio (brave-search) and HTTP (Notion) servers
  - [ ] Verify stdio server works without OAuth (API key via env)
  - [ ] Verify HTTP OAuth server triggers OAuth flow
  - [ ] Verify both servers work simultaneously

### Phase 2: Documentation

- [ ] **Update README.md**
  - [ ] Add "OAuth Support" section
  - [ ] Explain auto-detection mechanism
  - [ ] Provide example of OAuth-protected server config
  - [ ] Document first-time setup flow (browser opens)
  - [ ] Document token storage location

- [ ] **Update CLAUDE.md**
  - [ ] Add OAuth implementation details to Architecture section
  - [ ] Document OAuth auto-detection behavior
  - [ ] Add environment variable notes (if any)

- [ ] **Create User Guide** (`docs/oauth-user-guide.md`)
  - [ ] Quick start: Adding OAuth-protected MCPs
  - [ ] First-time authentication flow walkthrough
  - [ ] Troubleshooting common issues
  - [ ] Token management (location, expiration, refresh)
  - [ ] Headless environment workarounds

### Phase 3: Error Handling & UX

- [ ] **Improve OAuth Flow Visibility**
  - [ ] Add logging when OAuth flow is triggered
  - [ ] Log: "Opening browser for [server-name] authentication..."
  - [ ] Log: "✓ [server-name] authentication successful"
  - [ ] Log: "Using cached tokens for [server-name]"

- [ ] **Error Handling**
  - [ ] Handle OAuth callback failures gracefully
  - [ ] Detect when browser doesn't open (headless env)
  - [ ] Provide clear error messages for common OAuth failures
  - [ ] Add retry mechanism for failed OAuth flows

- [ ] **Token Management**
  - [ ] Verify automatic token refresh works
  - [ ] Handle refresh token expiration (trigger new OAuth flow)
  - [ ] Log token refresh events for debugging

### Phase 4: Testing

- [ ] **Unit Tests**
  - [ ] Test `_create_client()` creates OAuth-enabled clients for HTTP servers
  - [ ] Test stdio clients created without OAuth
  - [ ] Mock 401 response and verify OAuth triggered

- [ ] **Integration Tests**
  - [ ] Test with real OAuth-protected MCP (if available in test env)
  - [ ] Test token caching and reuse
  - [ ] Test token refresh flow

- [ ] **Manual Testing**
  - [ ] Test with Notion MCP (https://mcp.notion.com/mcp)
  - [ ] Test with other OAuth MCPs (GitHub, Google Drive, etc.)
  - [ ] Test mixed stdio + HTTP OAuth config
  - [ ] Test behavior when tokens expire

### Phase 5: Optional Enhancements

- [ ] **Per-Server Auth Configuration** (optional)
  - [ ] Add support for explicit `"auth": "oauth"` in `.mcp.json`
  - [ ] Update schema validation to accept `auth` field
  - [ ] Allow override of auto-detection if needed

- [ ] **OAuth Status Tool** (optional)
  - [ ] Create gateway tool to check OAuth status
  - [ ] Show which servers are authenticated
  - [ ] Show token expiration times
  - [ ] Allow manual re-authentication trigger

- [ ] **Multi-User Token Isolation** (future)
  - [ ] Implement per-agent token storage
  - [ ] Required only when gateway transitions to HTTP transport
  - [ ] Not needed for current stdio use case

---

## Expected Outcome

After implementation:

1. **Users can configure OAuth-protected MCPs** in `.mcp.json` with just a URL:
   ```json
   {
     "mcpServers": {
       "Notion": {
         "url": "https://mcp.notion.com/mcp"
       }
     }
   }
   ```

2. **First-time setup is seamless:**
   - User starts Claude Code
   - Browser opens automatically for Notion authentication
   - User completes auth, browser closes
   - Tokens cached, Claude Code ready to use

3. **Subsequent sessions are transparent:**
   - No browser windows
   - No authentication prompts
   - Automatic token refresh
   - Works exactly like non-OAuth servers

4. **Mixed authentication works:**
   - stdio servers with API keys (brave-search)
   - HTTP servers with OAuth (Notion)
   - HTTP servers without auth (public APIs)
   - All work simultaneously in same gateway instance

---

## Success Criteria

- [ ] Gateway successfully proxies to Notion MCP using OAuth
- [ ] Browser opens for initial authentication
- [ ] Tokens cached and reused on subsequent runs
- [ ] No configuration needed beyond URL in `.mcp.json`
- [ ] stdio servers (brave-search) continue working unchanged
- [ ] Documentation complete and accurate
- [ ] Error handling provides clear guidance to users

---

## Summary: How OAuth Auto-Detection Works

### It's Auto-Detection! 🎯

**You don't need to know which servers require OAuth ahead of time.**

#### How It Works (MCP Protocol Design)

1. **OAuth is triggered by the server, not configured by the client**
2. When your gateway connects to a server:
   - **No OAuth needed?** → Server responds with 200 OK
   - **OAuth needed?** → Server responds with **401 Unauthorized** + metadata

3. **FastMCP Client with `auth="oauth"` enabled:**
   - Sees 401 response
   - Fetches `/.well-known/oauth-protected-resource` from the server
   - Discovers OAuth endpoints automatically
   - Initiates OAuth flow

#### Practical Example

```json
{
  "mcpServers": {
    "brave-search": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-brave-search"],
      "env": {"BRAVE_API_KEY": "${BRAVE_API_KEY}"}
    },
    "Notion": {
      "url": "https://mcp.notion.com/mcp"
    }
  }
}
```

**What happens when gateway starts:**

1. **brave-search (stdio):** Gateway spawns npx process, communicates via stdio, API key from env var → ✅ Works
2. **Notion (HTTP):** Gateway connects to https://mcp.notion.com/mcp
   - Notion returns: **401 Unauthorized**
   - Gateway (with OAuth enabled): "Ah! This needs OAuth"
   - Browser opens for user to authenticate with Notion
   - Tokens cached
   - Subsequent requests: ✅ Works

#### Implementation: Enable OAuth for HTTP Clients Only

**Location:** Update `ProxyManager._create_client()` in `src/proxy.py`:

```python
def _create_client(self, server_name: str, server_config: dict) -> Client:
    client_config = {
        "mcpServers": {
            server_name: server_config
        }
    }

    # Enable OAuth for HTTP clients (activated only on 401 response)
    # stdio clients don't need OAuth (local process communication)
    if "url" in server_config:
        return Client(transport=client_config, auth="oauth")
    else:
        return Client(transport=client_config)
```

**Why this works:**
- **HTTP servers without OAuth** (if any exist) → return 200, OAuth never activates
- **HTTP servers with OAuth** (like Notion) → return 401, OAuth activates automatically
- **stdio servers** (like brave-search) → no HTTP, no 401, no OAuth, just works

#### No Configuration Needed! ✨

Your `.mcp.json` stays exactly as is:
- No need to add `"auth": "oauth"` fields
- No need to maintain a list of which servers need OAuth
- The MCP protocol handles auto-detection

**The server tells the client what it needs via HTTP status codes.**

---

## Research Report: MCP OAuth Authentication and Mixed Auth Scenarios

**Research Date:** November 1, 2025
**Research Scope:** How MCP gateways distinguish between OAuth-required vs non-OAuth downstream servers

Based on research of the MCP protocol specification, FastMCP documentation, and Notion MCP documentation, here are the comprehensive findings:

---

### 1. Auto-Detection vs Explicit Configuration: ANSWER - Auto-Detection via 401 Response

**The MCP protocol uses automatic OAuth discovery, NOT explicit configuration.**

**How it works:**
- When a client connects to an MCP server without credentials, the server returns **HTTP 401 Unauthorized**
- The 401 response includes a `WWW-Authenticate` header pointing to `/.well-known/oauth-protected-resource`
- The client fetches **Protected Resource Metadata** (RFC 9728) from this well-known endpoint
- This metadata tells the client which authorization server to use and what scopes are required

**Key insight from Notion MCP:**
Notion's documentation states: "Complete the OAuth flow to connect" - they rely on the MCP client detecting the 401 and initiating OAuth automatically. Their `.mcp.json` config contains ONLY the URL:
```json
{
  "mcpServers": {
    "Notion": {
      "url": "https://mcp.notion.com/mcp"
    }
  }
}
```

**No explicit "auth": "oauth" field is needed in .mcp.json for Notion because the MCP protocol handles discovery automatically.**

---

### 2. FastMCP Client Behavior with `auth="oauth"`

Based on FastMCP documentation analysis:

**When you set `auth="oauth"` on a FastMCP Client:**
- It **enables** OAuth but only **activates** it when the server returns 401
- It does **NOT** force OAuth on servers that don't require it
- The OAuth flow is **triggered** by the server's 401 response, not pre-configured

**From FastMCP docs:**
```python
# Proxy with custom authentication
async def authenticated_proxy():
    proxy = await FastMCP.as_proxy(
        "https://protected-api.com/mcp",
        name="Authenticated Proxy",
        client_kwargs={"auth": "oauth"}
    )
```

**Critical Finding:** The `auth="oauth"` parameter is a **per-client setting**. When creating individual Client instances for downstream servers, we need to pass this parameter explicitly.

---

### 3. Notion MCP Specifics

**From Notion's Documentation (https://developers.notion.com/docs/get-started-with-mcp):**

**Authentication Method:**
- Notion MCP requires OAuth 2.1 with PKCE
- Users initiate connection through Notion's in-app directory
- OAuth flow: User → Notion Auth → Access Token → MCP client stores token

**How Notion Signals OAuth Requirement:**
- First connection attempt WITHOUT auth → **401 Unauthorized**
- Response includes `WWW-Authenticate: Bearer realm="..."` header
- MCP client fetches `https://mcp.notion.com/.well-known/oauth-protected-resource`
- This returns Protected Resource Metadata with:
  ```json
  {
    "resource": "https://mcp.notion.com/mcp",
    "authorization_servers": ["https://api.notion.com"],
    "bearer_methods_supported": ["header"],
    "jwks_uri": "https://api.notion.com/.well-known/jwks.json"
  }
  ```

**What happens when you connect without auth:**
- Connection attempt succeeds (HTTP 200 for metadata endpoints)
- First MCP request → 401 Unauthorized
- Client detects OAuth requirement and initiates flow
- User redirected to browser for Notion login
- Token cached for future requests

---

### 4. Mixed Auth Scenarios - Implementation Pattern

**Current ProxyManager._create_client() Implementation:**

Looking at the ProxyManager implementation, clients are created per downstream server. We need to enable OAuth for HTTP clients specifically.

**Mixed auth scenarios (some OAuth, some not) are AUTOMATICALLY HANDLED by the MCP protocol:**
- Servers that don't need OAuth → respond with 200, no authentication required
- Servers that need OAuth → respond with 401, trigger OAuth flow
- **FastMCP Client needs `auth="oauth"` enabled to handle 401 responses**

**Implementation Pattern:**
```python
def _create_client(self, server_name: str, server_config: dict) -> Client:
    client_config = {
        "mcpServers": {
            server_name: server_config
        }
    }

    # Determine if this is an HTTP or stdio server
    if "url" in server_config:
        # HTTP server - enable OAuth (will only activate on 401)
        return Client(transport=client_config, auth="oauth")
    else:
        # stdio server - no OAuth needed
        return Client(transport=client_config)
```

---

### 5. MCP Protocol OAuth Discovery (RFC 9728)

**How a server advertises OAuth requirement:**

1. **Initial Connection:** Client attempts to connect (GET or POST to MCP endpoint)

2. **401 Response:** Server returns:
   ```http
   HTTP/1.1 401 Unauthorized
   WWW-Authenticate: Bearer realm="mcp", scope="read:tools write:resources"
   ```

3. **Metadata Discovery:** Client fetches `/.well-known/oauth-protected-resource`:
   ```json
   {
     "resource": "https://api.example.com/mcp",
     "authorization_servers": ["https://auth.example.com"],
     "bearer_methods_supported": ["header"],
     "scopes_supported": ["read:tools", "write:resources"],
     "jwks_uri": "https://auth.example.com/.well-known/jwks.json"
   }
   ```

4. **Authorization Server Metadata:** Client fetches `https://auth.example.com/.well-known/oauth-authorization-server`:
   ```json
   {
     "issuer": "https://auth.example.com",
     "authorization_endpoint": "https://auth.example.com/oauth/authorize",
     "token_endpoint": "https://auth.example.com/oauth/token",
     "registration_endpoint": "https://auth.example.com/oauth/register",
     "code_challenge_methods_supported": ["S256"]
   }
   ```

5. **Dynamic Client Registration (RFC 7591):** Client registers itself via POST to registration_endpoint

6. **PKCE Flow (RFC 7636):** Client initiates authorization code flow with PKCE for secure token exchange

**This all happens AUTOMATICALLY when the client has OAuth support enabled**

---

### 6. Practical Implementation for agent-mcp-gateway

**Recommendation: Enable OAuth for all HTTP downstream clients**

**Why this works:**
- OAuth is **triggered only when server returns 401**
- brave-search (stdio + API key) will NOT return 401, so OAuth won't activate
- Notion MCP (HTTP + OAuth) WILL return 401, triggering OAuth flow automatically
- No per-server configuration needed in `.mcp.json`

**Implementation Approach:**

**Update ProxyManager to enable OAuth for HTTP clients:**
```python
def _create_client(self, server_name: str, server_config: dict) -> Client:
    # Determine transport type
    has_command = "command" in server_config
    has_url = "url" in server_config

    # ... validation ...

    # Create HTTP client with OAuth support
    if has_url:
        url = server_config["url"]

        # Enable OAuth for ALL HTTP clients
        # OAuth will only activate if server returns 401
        client_config = {
            "mcpServers": {
                server_name: server_config
            }
        }
        return Client(transport=client_config, auth="oauth")

    # Create stdio client (no OAuth needed for local processes)
    if has_command:
        client_config = {
            "mcpServers": {
                server_name: server_config
            }
        }
        return Client(transport=client_config)
```

---

### 7. Best Practice Recommendation

**Enable OAuth for all HTTP clients (auto-detection approach)**

**Rationale:**
1. **Protocol-compliant:** OAuth is designed to be auto-discovered via 401 responses
2. **Zero configuration:** No need to manually specify auth in `.mcp.json`
3. **Future-proof:** Any new HTTP MCP server that requires OAuth will work automatically
4. **No false positives:** Servers without OAuth won't be affected (they return 200, not 401)
5. **Follows MCP spec design:** The spec explicitly designed OAuth to work this way

**Configuration stays simple:**
```json
{
  "mcpServers": {
    "brave-search": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-brave-search"],
      "env": {"BRAVE_API_KEY": "${BRAVE_API_KEY}"}
    },
    "Notion": {
      "url": "https://mcp.notion.com/mcp"
    }
  }
}
```

No need to specify auth type - the protocol handles it!

---

### 8. Edge Cases and Gotchas

1. **First-time OAuth requires user interaction:**
   - User must complete OAuth flow in browser
   - Tokens are cached locally for subsequent requests
   - Gateway cannot autonomously complete OAuth (requires user consent)

2. **stdio servers NEVER need OAuth:**
   - They run as local child processes
   - Authentication is via environment variables (API keys)
   - OAuth only applies to HTTP transport

3. **Token expiration:**
   - FastMCP Client handles refresh tokens automatically
   - If refresh fails, user must re-authenticate via browser

4. **Multiple authorization servers:**
   - Each MCP server can use different OAuth providers (GitHub, Google, Auth0, etc.)
   - FastMCP Client supports dynamic client registration (RFC 7591)
   - No manual OAuth app registration needed

5. **Protected Resource Metadata caching:**
   - Clients should cache `/.well-known/oauth-protected-resource` metadata
   - Reduces network requests on subsequent connections

6. **Token Storage Location:**
   - Tokens cached in `~/.fastmcp/oauth-mcp-client-cache/`
   - Separate cache per downstream server URL
   - Tokens persist across gateway restarts

---

### 9. Summary Answer Table

| Question | Answer |
|----------|--------|
| **Auto-Detection vs Explicit Config?** | Auto-detection via 401 response + Protected Resource Metadata |
| **Can FastMCP auto-detect?** | Yes, when `auth="oauth"` is enabled on the Client |
| **Does setting `auth="oauth"` globally affect all servers?** | No - it enables OAuth but only activates when server returns 401 |
| **Will brave-search break?** | No - it returns 200, so OAuth never activates |
| **How does Notion signal OAuth?** | 401 Unauthorized → `/.well-known/oauth-protected-resource` |
| **Best practice for mixed auth?** | Enable OAuth for all HTTP clients; let protocol handle auto-detection |

---

### 10. Files to Modify

**Primary Changes:**
- `/Users/roddutra/Developer/--personal/agent-mcp-gateway/src/proxy.py`
  - Update `_create_client()` method to enable OAuth for HTTP clients

**Documentation Updates:**
- `/Users/roddutra/Developer/--personal/agent-mcp-gateway/README.md`
  - Add OAuth support section
  - Document first-time setup flow

- `/Users/roddutra/Developer/--personal/agent-mcp-gateway/CLAUDE.md`
  - Update architecture section with OAuth details

- `/Users/roddutra/Developer/--personal/agent-mcp-gateway/docs/oauth-user-guide.md` (new)
  - Comprehensive user guide for OAuth setup and troubleshooting

---

## References

1. **MCP Specification - Authorization:** https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization
2. **RFC 9728 - OAuth 2.0 Protected Resource Metadata:** https://www.rfc-editor.org/rfc/rfc9728.html
3. **RFC 7591 - Dynamic Client Registration:** https://www.rfc-editor.org/rfc/rfc7591.html
4. **RFC 7636 - PKCE:** https://www.rfc-editor.org/rfc/rfc7636.html
5. **Notion MCP Documentation:** https://developers.notion.com/docs/get-started-with-mcp
6. **FastMCP Documentation:** https://github.com/jlowin/fastmcp
7. **FastMCP OAuth Examples:** FastMCP repository and documentation

---

## Notes for Implementation

- Start with Phase 1 (core OAuth support) as it's the most critical
- Test with Notion MCP for real-world validation
- User documentation (Phase 2) is essential for adoption
- Error handling (Phase 3) can be added iteratively
- Multi-user support (Phase 5) is future work, not needed for current stdio use case

**Estimated Implementation Time:**
- Phase 1: 2-3 hours
- Phase 2: 1-2 hours
- Phase 3: 2-3 hours
- Phase 4: 2-4 hours (depending on test infrastructure)

**Total: 7-12 hours for complete implementation with tests and documentation**
