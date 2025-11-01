# Multi-Hop OAuth: Proxying to OAuth-Protected Downstream MCPs

**Research Date:** November 1, 2025
**Use Case:** How agent-mcp-gateway proxies to downstream MCPs that require OAuth authentication

---

## The Specific Scenario

**Four-Party Architecture:**
```
User ↔ Claude Code (MCP Client) ↔ agent-mcp-gateway (MCP Proxy) ↔ Notion MCP (OAuth-protected) ↔ Notion OAuth Provider
```

**Real-World Example:**
1. User adds agent-mcp-gateway to Claude Code as the ONLY MCP server
2. agent-mcp-gateway is configured with downstream MCPs (e.g., Notion MCP) that require OAuth
3. When user wants to use Notion tools through gateway, OAuth authentication must happen

**Key Question:** How does OAuth flow between these parties?

---

## Executive Summary

**Can the agent-mcp-gateway proxy to OAuth-protected downstream MCPs?**

**YES** - FastMCP 2.x fully supports this scenario. When using `FastMCP.as_proxy()`, you can configure the gateway to connect to OAuth-protected downstream MCPs by passing authentication parameters through `client_kwargs`. The OAuth flow, token storage, and authentication are handled by the **gateway itself**, not by Claude Code.

**Implementation Complexity:** Simple - one line of code change.

**User Experience:** Browser opens for initial authentication, then seamless thereafter.

---

## How It Works: The Three-Party Reality

**Important Realization:** This is actually a **THREE-party flow from the user's perspective**, not four.

The gateway acts as an MCP client to downstream servers, meaning:

1. **Claude Code** → Connects to gateway (no OAuth, just stdio)
2. **Gateway** → Connects to Notion MCP (with OAuth)
3. **Notion MCP** → Validates tokens with Notion OAuth Provider

**Claude Code is completely unaware of the downstream OAuth flow.**

---

## Initial OAuth Flow (First-Time Setup)

### What Happens Step-by-Step

1. **User starts Claude Code** → gateway process starts via stdio
2. **Gateway tries to connect** to Notion MCP (configured in `.mcp.json`)
3. **Notion MCP responds** with 401 Unauthorized + Protected Resource Metadata (PRM)
4. **Gateway's OAuth client discovers** authorization server endpoints via `/.well-known/oauth-protected-resource`
5. **Gateway opens browser window** on user's machine (NOT in Claude Code)
6. **User authenticates** with Notion OAuth Provider in browser
7. **Browser redirects to** `localhost:<random-port>/callback` (gateway's temporary HTTP server)
8. **Gateway receives authorization code** and exchanges it for access token
9. **Gateway stores tokens** in `~/.fastmcp/oauth-mcp-client-cache/`
10. **Gateway uses access token** for all subsequent requests to Notion MCP

### Code Implementation

```python
# In agent-mcp-gateway main.py
from fastmcp import FastMCP

# Configuration for OAuth-protected downstream server
mcp_config = {
    "mcpServers": {
        "notion": {
            "url": "https://notion-mcp-server.example.com/mcp",
            "transport": "http"
        }
    }
}

# Create proxy with OAuth authentication for downstream
gateway = FastMCP.as_proxy(
    mcp_config,
    name="agent-mcp-gateway",
    client_kwargs={"auth": "oauth"}  # Enable OAuth for downstream connections
)
```

**That's it!** FastMCP handles everything else automatically.

---

## Token Storage and Management

### Where Are Tokens Stored?

**Location:** `~/.fastmcp/oauth-mcp-client-cache/` on the machine running the gateway

**Structure:**
```
~/.fastmcp/oauth-mcp-client-cache/
├── <hash-of-notion-server-url>/
│   └── tokens.json
├── <hash-of-google-drive-server-url>/
│   └── tokens.json
└── ...
```

**Token file format:**
```json
{
  "access_token": "ya29.a0AfH6SMB...",
  "refresh_token": "1//0gKJK...",
  "expires_at": 1730462400,
  "token_type": "Bearer"
}
```

### Token Lifecycle

**Initial Authentication:**
- User authenticates via browser
- Gateway receives and caches tokens

**Subsequent Sessions:**
- Gateway loads cached tokens on startup
- No user interaction needed

**Token Refresh (Automatic):**
- When access token expires, gateway uses refresh token
- Gets new access token from OAuth provider
- Updates cache automatically
- User never notices

**Refresh Token Expiration:**
- If refresh token expires (typically 30-90 days of inactivity)
- Gateway detects 401 even after refresh attempt
- **New OAuth flow initiated** - browser opens again
- User re-authenticates, new tokens cached

---

## Claude Code Configuration

### What Claude Code Knows

**Claude Code's MCP configuration** (`~/.claude/mcp.json`):
```json
{
  "mcpServers": {
    "agent-mcp-gateway": {
      "command": "uv",
      "args": ["run", "python", "/path/to/agent-mcp-gateway/main.py"]
    }
  }
}
```

**That's all.** Claude Code only knows about the gateway via stdio connection.

### What Claude Code Doesn't Know

- That gateway connects to downstream MCPs
- That any of those MCPs require OAuth
- What tokens are being used
- When OAuth flows happen

**Claude Code simply calls gateway tools** - the gateway handles all complexity.

---

## User Experience

### First-Time Setup

**Step 1: User configures gateway's `.mcp.json`**
```json
{
  "mcpServers": {
    "notion": {
      "url": "https://notion-mcp.example.com/mcp",
      "transport": "http"
    },
    "google-drive": {
      "url": "https://drive-mcp.example.com/mcp",
      "transport": "http"
    }
  }
}
```

**Step 2: User adds gateway to Claude Code**
```json
{
  "mcpServers": {
    "agent-mcp-gateway": {
      "command": "uv",
      "args": ["run", "python", "/path/to/agent-mcp-gateway/main.py"]
    }
  }
}
```

**Step 3: User starts Claude Code**

**What happens:**
1. Gateway starts
2. **Browser window opens** for Notion authentication
3. User logs into Notion, grants permission
4. Browser shows "Authentication successful" and closes
5. **Another browser window opens** for Google Drive authentication
6. User logs into Google, grants permission
7. Browser shows "Authentication successful" and closes
8. **Gateway is ready** - Claude Code can now use all Notion and Google Drive tools

### Subsequent Sessions

**User starts Claude Code:**
1. Gateway starts
2. Gateway loads cached tokens from `~/.fastmcp/oauth-mcp-client-cache/`
3. Gateway refreshes access tokens if needed (automatic, using refresh tokens)
4. **Everything works seamlessly** - no user interaction required
5. User can immediately use Notion and Google Drive tools through Claude Code

**No browser windows, no authentication prompts, no delays.**

---

## Implementation Details

### MCP Client Creation with OAuth

**How gateway creates OAuth-enabled clients for downstream servers:**

**Option 1: Automatic OAuth (Recommended)**
```python
from fastmcp import Client

# FastMCP handles everything automatically
client = Client("https://notion-mcp.example.com/mcp", auth="oauth")
```

**Option 2: Explicit OAuth Configuration**
```python
from fastmcp.client.auth import OAuth

oauth = OAuth(
    mcp_url="https://notion-mcp.example.com/mcp",
    client_name="agent-mcp-gateway",
    callback_port=61382  # Random port for OAuth callback server
)
client = Client("https://notion-mcp.example.com/mcp", auth=oauth)
```

**Option 3: Via as_proxy with Config (Used by agent-mcp-gateway)**
```python
gateway = FastMCP.as_proxy(
    {
        "mcpServers": {
            "notion": {
                "url": "https://notion-mcp.example.com/mcp",
                "transport": "http"
            }
        }
    },
    client_kwargs={"auth": "oauth"}  # Applied to all downstream servers
)
```

### Token Flow During Client Creation

1. **Client checks cache:** `~/.fastmcp/oauth-mcp-client-cache/<server-hash>/tokens.json`
2. **If valid tokens found:** Use cached access token
3. **If not found or expired:**
   - Start OAuth flow
   - Open browser for user authentication
   - Receive authorization code via localhost callback
   - Exchange code for tokens
   - Save tokens to cache
4. **Client adds header:** `Authorization: Bearer <access_token>` to all MCP requests

### Automatic Token Refresh

**FastMCP handles token refresh automatically:**

```python
# No manual refresh needed - this happens automatically:
#
# 1. Gateway makes request to Notion MCP
# 2. Notion MCP returns 401 (token expired)
# 3. Gateway detects 401
# 4. Gateway uses refresh token to get new access token
# 5. Gateway updates cache with new tokens
# 6. Gateway retries original request with new access token
# 7. Request succeeds
```

**User never experiences any interruption.**

---

## Real-World Examples

### Example from FastMCP GitHub Issues

**Issue #1551 - Multi-User Token Storage:**

A developer successfully created a proxy to an OAuth-protected MCP:

```python
from fastmcp import FastMCP
from fastmcp.client.auth import OAuth
from fastmcp.transport import StreamableHttpTransport

# Create OAuth configuration
oauth = OAuth(
    mcp_url="http://127.0.0.1:8000/mcp",
    client_name="mcp-inspector",
    callback_port=61382
)

# Create MCP client with OAuth
mcp_client = Client(
    transport=StreamableHttpTransport(
        url="http://127.0.0.1:8000/mcp",
        auth=oauth
    )
)

# Create proxy server
proxy = FastMCP.as_proxy(mcp_client, name="proxy01")
proxy.run(transport="stdio")
```

**Result:** Successfully proxied stdio requests to OAuth-protected HTTP MCP server.

### Example: Notion MCP Behind Gateway

**Gateway configuration (`.mcp.json`):**
```json
{
  "mcpServers": {
    "notion": {
      "url": "https://api.notion.com/mcp",
      "transport": "http"
    }
  }
}
```

**Gateway code:**
```python
from fastmcp import FastMCP
from pathlib import Path

# Load downstream server config
mcp_config = load_config(Path(".mcp.json"))

# Create gateway with OAuth support
gateway = FastMCP.as_proxy(
    mcp_config,
    name="Agent MCP Gateway",
    client_kwargs={"auth": "oauth"}
)

# Add access control middleware
gateway.add_middleware(AgentAccessControl())

# Run on stdio (for Claude Code)
gateway.run(transport="stdio")
```

**User interaction:**
1. First run: Browser opens for Notion OAuth
2. User authorizes access to their Notion workspace
3. Tokens cached
4. All subsequent runs: Automatic, seamless

---

## Advanced: Selective OAuth Configuration

### Challenge

Some downstream MCPs require OAuth, others don't. How to handle mixed authentication requirements?

### Solution: Per-Server Auth Configuration

**Extend `.mcp.json` schema:**
```json
{
  "mcpServers": {
    "notion": {
      "url": "https://notion-mcp.example.com/mcp",
      "transport": "http",
      "auth": "oauth"  // Explicitly requires OAuth
    },
    "public-api": {
      "url": "https://public-mcp.example.com/mcp",
      "transport": "http"
      // No auth field = no authentication
    },
    "brave-search": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-brave-search"],
      "env": {"BRAVE_API_KEY": "${BRAVE_API_KEY}"}
      // stdio transport - no OAuth possible
    }
  }
}
```

**Gateway implementation:**
```python
from fastmcp import FastMCP, Client
from fastmcp.transport import StreamableHttpTransport

# Load config
mcp_config = load_config(".mcp.json")

# Create clients with appropriate auth
clients = {}
for name, config in mcp_config["mcpServers"].items():
    if config.get("auth") == "oauth":
        # OAuth-protected HTTP server
        clients[name] = Client(
            config["url"],
            auth="oauth"
        )
    elif config.get("transport") == "http":
        # HTTP server without auth
        clients[name] = Client(config["url"])
    else:
        # stdio server - will be handled by FastMCP.as_proxy() normally
        pass

# Create composite proxy
# (This is simplified - actual implementation would use FastMCP.as_proxy() differently)
gateway = FastMCP.as_proxy(mcp_config, client_kwargs={"auth": "oauth"})
```

**Benefit:** Mix OAuth-protected and public MCPs in same gateway.

---

## Blockers and Limitations

### Non-Blocker: stdio Transport for Gateway

**Initial Concern:** OAuth requires HTTP callbacks, but gateway uses stdio to talk to Claude Code.

**Why it's not a blocker:**

The gateway is a Python process running on the user's machine. It can:
1. Communicate with Claude Code via stdio
2. **Simultaneously** run a temporary HTTP server on `localhost:<random-port>` for OAuth callbacks
3. These are independent - stdio for MCP protocol, HTTP for OAuth callbacks

**FastMCP implementation:**
```python
# FastMCP creates temporary OAuth callback server automatically
from fastmcp.client.oauth_callback import create_oauth_callback_server

server = create_oauth_callback_server(
    port=61382,  # or random available port
    callback_path="/callback"
)
# Server runs in background thread
# Gateway continues handling stdio communication
```

### Limitation 1: No OAuth for stdio Downstream MCPs

**Scope:** OAuth only works with HTTP/SSE transports, not stdio.

**Impact:** If a downstream MCP uses stdio transport (e.g., `npx @modelcontextprotocol/server-notion`), it **cannot** use OAuth.

**Why:** stdio has no HTTP endpoint for OAuth callbacks.

**Workaround:** OAuth-protected MCPs must expose HTTP/SSE endpoints. Many do (or can):
- Notion MCP: Can run as HTTP server
- Google Drive MCP: HTTP endpoint available
- GitHub MCP: HTTP endpoint available

**Example:**
```json
// This WILL NOT work with OAuth:
{
  "notion": {
    "command": "npx",
    "args": ["@modelcontextprotocol/server-notion"],
    "env": {"NOTION_API_KEY": "${NOTION_API_KEY}"}
  }
}

// This WILL work with OAuth:
{
  "notion": {
    "url": "https://notion-mcp.example.com/mcp",
    "transport": "http"
  }
}
```

### Limitation 2: Browser Required for Initial Authentication

**Impact:** Headless environments (Docker containers, CI/CD pipelines) cannot complete OAuth flows.

**Scenarios where this is a problem:**
- Gateway running in Docker without X11 forwarding
- Automated testing environments
- CI/CD pipelines

**Workaround: Pre-authenticate and copy tokens**

```bash
# On machine WITH browser (e.g., developer's laptop)
cd agent-mcp-gateway
uv run python -c "
from fastmcp import Client
client = Client('https://notion-mcp.example.com/mcp', auth='oauth')
# This triggers OAuth flow in browser and caches tokens
"

# Copy cached tokens to headless environment
scp -r ~/.fastmcp/oauth-mcp-client-cache/ user@docker-host:~/.fastmcp/

# Now Docker container can use pre-authenticated tokens
```

**Alternative: Use service account tokens** (if downstream MCP supports it)
```python
# Instead of OAuth, use long-lived service account token
from fastmcp.client.auth import BearerAuth

client = Client(
    "https://notion-mcp.example.com/mcp",
    auth=BearerAuth(token=os.getenv("NOTION_SERVICE_ACCOUNT_TOKEN"))
)
```

### Limitation 3: Multi-User Scenarios (Future Consideration)

**Current Status:** Not a blocker for Claude Code use case (single user per gateway instance).

**Future Scenario:** If gateway transitions to HTTP transport for multi-user access:

**Problem:** Tokens stored in `~/.fastmcp/oauth-mcp-client-cache/` are global
- User A authenticates with their Notion account
- User B connects to same gateway instance
- User B would use User A's Notion tokens
- **Security issue:** Users could access each other's data

**Solution for future multi-user scenarios:**

**Per-user token storage:**
```python
from fastmcp.client.auth.oauth import FileTokenStorage
from pathlib import Path

class UserTokenStorage(FileTokenStorage):
    def __init__(self, server_url: str, user_id: str):
        # Store tokens per user
        storage_path = Path(f"~/.fastmcp/tokens/{user_id}")
        super().__init__(server_url, storage_path)

# Create OAuth client with user-specific storage
@gateway.middleware
async def create_user_specific_client(ctx, call_next):
    user_id = ctx.get("agent_id")  # From gateway's access control

    oauth = OAuth(
        mcp_url="https://notion-mcp.example.com/mcp",
        token_storage=UserTokenStorage("https://notion-mcp.example.com/mcp", user_id)
    )

    client = Client("https://notion-mcp.example.com/mcp", auth=oauth)
    ctx.set("notion_client", client)

    return await call_next(ctx)
```

**When to implement:** Only if/when gateway supports multiple concurrent users.

---

## Implementation Plan

### Phase 1: Basic OAuth Proxy Support (MVP)

**Goal:** Enable gateway to proxy to OAuth-protected downstream MCPs

**Effort:** 1-2 hours

**Changes Required:**

1. **Update main.py:**
```python
# Before
gateway = FastMCP.as_proxy(
    mcp_config,
    name="Agent MCP Gateway"
)

# After
gateway = FastMCP.as_proxy(
    mcp_config,
    name="Agent MCP Gateway",
    client_kwargs={"auth": "oauth"}  # NEW: Enable OAuth for downstream
)
```

2. **Update documentation** - Add OAuth setup guide
3. **Test with real OAuth MCP** - Verify with GitHub MCP or similar

**Testing:**
```bash
# Add GitHub MCP to .mcp.json
{
  "mcpServers": {
    "github": {
      "url": "https://github-mcp.example.com/mcp",
      "transport": "http"
    }
  }
}

# Start gateway
uv run python main.py

# Expected: Browser opens for GitHub OAuth
# After auth: Tokens cached in ~/.fastmcp/oauth-mcp-client-cache/
# Subsequent runs: No browser, uses cached tokens
```

### Phase 2: Selective OAuth Configuration

**Goal:** Support mixed authentication requirements (some MCPs with OAuth, some without)

**Effort:** 4-8 hours

**Implementation:**

Extend `.mcp.json` schema to include auth field:
```json
{
  "mcpServers": {
    "notion": {
      "url": "https://notion-mcp.example.com/mcp",
      "transport": "http",
      "auth": "oauth"
    },
    "public-api": {
      "url": "https://public-mcp.example.com/mcp",
      "transport": "http"
      // No auth
    }
  }
}
```

Modify gateway to respect per-server auth configuration.

### Phase 3: Enhanced User Experience

**Goal:** Better OAuth flow visibility and error handling

**Features:**
- Pre-flight OAuth check during gateway startup
- Clear terminal messages: "Opening browser for Notion authentication..."
- OAuth status command/tool for debugging
- Token expiration warnings
- Manual re-authentication command

**Example terminal output:**
```
Agent MCP Gateway starting...
✓ Loading configuration from .mcp.json
✓ Configured downstream servers: notion, github, brave-search

Authenticating with downstream servers:
→ brave-search: No authentication required
→ notion: OAuth required
  Opening browser for Notion authentication...
  ✓ Notion authentication successful (tokens cached)
→ github: OAuth required
  Opening browser for GitHub authentication...
  ✓ GitHub authentication successful (tokens cached)

✓ Gateway ready on stdio transport
✓ All 3 downstream servers connected
```

### Phase 4: Multi-User Support (Future)

**Goal:** Support multiple users when gateway runs as HTTP server

**Required when:** Gateway transitions from stdio to HTTP transport

**Implementation:** Per-user token storage (see Limitation 3 above)

---

## User Documentation

### Quick Start: Using OAuth-Protected Downstream MCPs

**Step 1: Configure your gateway's `.mcp.json`**

Add OAuth-protected MCPs to your gateway configuration:

```json
{
  "mcpServers": {
    "notion": {
      "url": "https://notion-mcp.example.com/mcp",
      "transport": "http"
    },
    "github": {
      "url": "https://github-mcp.example.com/mcp",
      "transport": "http"
    }
  }
}
```

**Step 2: Add gateway to Claude Code**

In your Claude Code MCP configuration (`~/.claude/mcp.json`):

```json
{
  "mcpServers": {
    "agent-mcp-gateway": {
      "command": "uv",
      "args": ["run", "python", "/path/to/agent-mcp-gateway/main.py"]
    }
  }
}
```

**Step 3: Start Claude Code**

When you start Claude Code:
1. Gateway will detect OAuth requirement for Notion
2. **Browser window opens automatically** on your machine
3. Log into Notion and grant permission
4. Browser shows "Authentication successful"
5. Repeat for GitHub (or any other OAuth-protected MCPs)
6. Return to Claude Code - you can now use all tools!

**Step 4: Use tools normally**

In Claude Code, you can now use Notion and GitHub tools:
- "Show me my Notion pages"
- "Create a new GitHub issue"
- Etc.

**Claude Code has no idea these MCPs require OAuth** - the gateway handles everything transparently.

### Subsequent Sessions

After initial authentication:
- Tokens are cached in `~/.fastmcp/oauth-mcp-client-cache/`
- No browser windows open
- No authentication prompts
- Everything works seamlessly

Tokens refresh automatically when they expire.

### Troubleshooting

**Browser doesn't open:**
- Check that your system can open browser windows
- Test: `python -m webbrowser https://example.com`
- Check that gateway has permissions to spawn browser

**"Authentication failed" error:**
- Verify the downstream MCP URL in `.mcp.json`
- Check that the MCP server is running and accessible
- Try accessing the MCP URL directly in browser

**Need to re-authenticate:**
- Clear cached tokens: `rm -rf ~/.fastmcp/oauth-mcp-client-cache/`
- Restart Claude Code
- Browser will open again for authentication

**Tokens expiring too quickly:**
- Check that your system clock is correct
- Verify MCP server's token expiration settings
- Ensure refresh tokens are being saved (check cache directory)

---

## Alternative Approaches (If Direct Proxying Doesn't Fit)

### Alternative 1: Manual Token Injection

**Scenario:** User obtains OAuth tokens through other means and provides them to gateway.

**Implementation:**
```python
from fastmcp.client.auth import BearerAuth
import os

# User provides token via environment variable
notion_token = os.getenv("NOTION_ACCESS_TOKEN")

client = Client(
    "https://notion-mcp.example.com/mcp",
    auth=BearerAuth(notion_token)
)
```

**Pros:**
- Simple implementation
- No browser required
- Works in headless environments

**Cons:**
- User must manually obtain and refresh tokens
- Poor user experience
- Tokens expire, requiring manual updates

### Alternative 2: OAuth Setup Wizard

**Scenario:** Separate one-time setup step for authenticating downstream MCPs.

**Implementation:**
```python
# setup_oauth.py
from fastmcp import Client

async def setup_downstream_oauth():
    print("Setting up Notion MCP authentication...")
    client = Client("https://notion-mcp.example.com/mcp", auth="oauth")
    await client.ping()  # Triggers OAuth flow
    print("✓ Notion authentication successful! Tokens cached.")

    print("Setting up GitHub MCP authentication...")
    client = Client("https://github-mcp.example.com/mcp", auth="oauth")
    await client.ping()
    print("✓ GitHub authentication successful! Tokens cached.")

    print("\nSetup complete! You can now start Claude Code.")
```

**Usage:**
```bash
# Run once during setup
uv run python setup_oauth.py

# Then use gateway normally in Claude Code
```

**Pros:**
- Clear separation of setup vs runtime
- User knows when authentication is happening
- Can provide better error messages and guidance

**Cons:**
- Extra setup step
- Less seamless than automatic flow

### Alternative 3: Gateway OAuth Tools

**Scenario:** Gateway exposes tools that users can call from Claude Code to trigger OAuth flows.

**Implementation:**
```python
@gateway.tool
async def authenticate_notion(ctx: Context) -> str:
    """Initiate OAuth flow for Notion MCP"""
    # Trigger OAuth flow
    client = Client("https://notion-mcp.example.com/mcp", auth="oauth")
    # This opens browser
    return "Please complete authentication in the browser window that opened."

@gateway.tool
async def list_authenticated_servers(ctx: Context) -> list[str]:
    """List which downstream MCPs are authenticated"""
    # Check token cache
    authenticated = []
    cache_dir = Path.home() / ".fastmcp" / "oauth-mcp-client-cache"
    for server_dir in cache_dir.iterdir():
        if (server_dir / "tokens.json").exists():
            authenticated.append(server_dir.name)
    return authenticated
```

**Usage in Claude Code:**
```
User: "Authenticate with Notion"
Claude: [Calls authenticate_notion tool]
Gateway: [Opens browser for OAuth]
User: [Completes auth in browser]
Claude: "Authentication successful!"
```

**Pros:**
- User can trigger auth from within Claude Code
- More control over when authentication happens
- Can check auth status, re-authenticate, etc.

**Cons:**
- More complex implementation
- User must know to authenticate before using tools
- Breaks stdio transport model (browser opens outside Claude Code)

---

## Sources

1. **FastMCP Proxy Documentation:** https://github.com/jlowin/fastmcp/blob/main/docs/servers/proxy.mdx
2. **FastMCP OAuth Client Documentation:** https://github.com/jlowin/fastmcp/blob/main/docs/clients/auth/oauth.mdx
3. **FastMCP Issue #1551 - Multi-User Token Storage:** https://github.com/jlowin/fastmcp/issues/1551
4. **MCP Authorization Specification:** https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization
5. **AWS Blog - MCP Authentication:** https://aws.amazon.com/blogs/opensource/open-protocols-for-agent-interoperability-part-2-authentication-on-mcp/
6. **Real-world implementations:** Reddit r/mcp discussions, Medium articles on MCP gateway OAuth patterns

---

## Conclusion

**The agent-mcp-gateway CAN transparently proxy to OAuth-protected downstream MCPs.**

**Key Takeaways:**

1. ✅ **Implementation is simple:** One line of code (`client_kwargs={"auth": "oauth"}`)
2. ✅ **User experience is seamless:** Browser opens once for initial auth, then automatic
3. ✅ **Claude Code is unaware:** Talks to gateway via stdio, knows nothing about OAuth
4. ✅ **Token management is automatic:** FastMCP handles refresh, caching, expiration
5. ✅ **Works with existing architecture:** No changes to stdio transport or policy engine

**Recommendation:** Implement Phase 1 (Basic OAuth Proxy Support) immediately. It's a minimal change with significant benefit for users who want to connect to OAuth-protected MCPs like Notion, GitHub, Google Drive, etc.

**Next Step:** Update `main.py` to enable OAuth support and test with a real OAuth-protected MCP server.
