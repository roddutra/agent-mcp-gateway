# OAuth User Guide for Agent MCP Gateway

**Last Updated:** 2025-11-01
**Status:** ✅ Complete

---

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [How OAuth Auto-Detection Works](#how-oauth-auto-detection-works)
- [First-Time Authentication](#first-time-authentication)
- [Token Management](#token-management)
- [Mixed Authentication Scenarios](#mixed-authentication-scenarios)
- [Troubleshooting](#troubleshooting)
- [Headless Environments](#headless-environments)
- [Security Considerations](#security-considerations)
- [FAQ](#faq)

---

## Overview

The Agent MCP Gateway supports OAuth-protected downstream MCP servers (like Notion MCP, GitHub MCP) through **automatic OAuth detection**. You don't need to configure which servers require OAuth - the MCP protocol handles this automatically.

### Key Benefits

- ✅ **Zero Configuration**: Just add the server URL to `.mcp.json`
- ✅ **Auto-Detection**: Gateway detects OAuth requirement automatically
- ✅ **Seamless UX**: Browser opens once, then tokens cached for future use
- ✅ **Transparent**: stdio servers continue working with API keys as before
- ✅ **Mixed Auth**: Supports both OAuth and non-OAuth servers simultaneously

---

## Quick Start

### Step 1: Add OAuth-Protected Server to Configuration

Edit your `.mcp.json` file and add the OAuth-protected server's URL:

```json
{
  "mcpServers": {
    "notion": {
      "url": "https://mcp.notion.com/mcp",
      "transport": "http"
    }
  }
}
```

**That's it!** No explicit OAuth configuration needed.

### Step 2: Start the Gateway

```bash
uv run python main.py
```

### Step 3: Complete Authentication

When the gateway first connects to Notion:

1. **Browser opens automatically** with Notion login page
2. **Log in to Notion** and grant permissions
3. **Browser shows** "Authentication successful" message
4. **Browser closes automatically**
5. **Gateway connects** and Notion tools become available

### Step 4: Use Notion Tools

Notion tools are now available through the gateway:

```python
# List Notion tools
tools = await client.call_tool("get_server_tools", {
    "agent_id": "your-agent",
    "server": "notion"
})

# Execute Notion tool
result = await client.call_tool("execute_tool", {
    "agent_id": "your-agent",
    "server": "notion",
    "tool": "search_pages",
    "args": {"query": "project notes"}
})
```

---

## How OAuth Auto-Detection Works

The MCP protocol uses **HTTP status codes** to signal OAuth requirements:

### Non-OAuth Servers

```
Gateway → HTTP GET /mcp → Server
         ← HTTP 200 OK
✅ Connection established
```

### OAuth-Protected Servers

```
Gateway → HTTP GET /mcp → Server
         ← HTTP 401 Unauthorized
         ← WWW-Authenticate: Bearer ...
         ← OAuth metadata in response body

Gateway → Fetches /.well-known/oauth-protected-resource
         ← OAuth configuration (RFC 9728)

Gateway → Opens browser for user authentication
User    → Logs in and grants permissions
         ← Authorization code

Gateway → Exchanges code for tokens
         ← Access token + refresh token

Gateway → Caches tokens in ~/.fastmcp/oauth-mcp-client-cache/
Gateway → Retries original request with Bearer token
         ← HTTP 200 OK
✅ Connection established with OAuth
```

### What This Means

- **You don't configure OAuth** - the server tells the gateway it needs OAuth
- **Gateway enables OAuth for all HTTP servers** - it only activates on 401
- **stdio servers never trigger OAuth** - they use local process communication
- **Mixed configs work automatically** - each server handled according to its needs

---

## First-Time Authentication

### What to Expect

When connecting to an OAuth-protected server for the first time:

#### Terminal Output

```
Loading MCP server configuration from: .mcp.json
Loading gateway rules from: .mcp-gateway-rules.json

Initializing proxy connections to downstream servers...
  - 2 proxy client(s) initialized
    * brave-search: ready (stdio, no OAuth)
    * notion: ready (HTTP, OAuth enabled)
```

#### Browser Interaction

1. **Browser window opens** automatically
2. **You see the OAuth provider's login page** (e.g., Notion login)
3. **You log in** with your credentials
4. **You grant permissions** for the gateway to access your data
5. **Browser shows** "Authentication successful - you can close this window"
6. **Browser may close automatically** (depending on OAuth provider)

#### Gateway Logs

```
[INFO] Creating HTTP Client with OAuth support for notion: url=https://mcp.notion.com/mcp
[INFO] OAuth flow initiated for notion
[INFO] Opening browser for authentication...
[INFO] OAuth callback received
[INFO] Tokens cached for notion
[INFO] Successfully connected to server: notion
```

### Authentication Flow Timeline

| Time | Event |
|------|-------|
| T+0s | Gateway starts, detects OAuth requirement |
| T+1s | Browser window opens |
| T+5s | You log in (variable timing) |
| T+10s | You grant permissions |
| T+11s | Browser shows success message |
| T+12s | Gateway caches tokens |
| T+13s | Gateway ready - Notion tools available |

---

## Token Management

### Token Storage

OAuth tokens are stored in: `~/.fastmcp/oauth-mcp-client-cache/`

```
~/.fastmcp/oauth-mcp-client-cache/
├── <hash-of-notion-url>/
│   └── tokens.json
├── <hash-of-github-url>/
│   └── tokens.json
└── ...
```

### Token Structure

```json
{
  "access_token": "ya29.a0AfH6SMB...",
  "refresh_token": "1//0gKJK...",
  "expires_at": 1730462400,
  "token_type": "Bearer"
}
```

### Automatic Token Refresh

The gateway automatically refreshes access tokens when they expire:

1. **Gateway makes request** with cached access token
2. **Server responds** with 401 (token expired)
3. **Gateway detects expiration** and uses refresh token
4. **Gateway gets new access token** from OAuth provider
5. **Gateway updates cache** with new token
6. **Gateway retries request** with fresh token
7. **Request succeeds** - you never notice

**No user interaction required** for token refresh.

### Token Expiration

**Access Token:** Typically expires in 1 hour
- ✅ Automatically refreshed by gateway

**Refresh Token:** Typically expires in 30-90 days of inactivity
- ⚠️ Requires new authentication flow if expired
- Browser will open automatically for re-authentication

### Manual Token Management

**View cached tokens:**
```bash
ls -la ~/.fastmcp/oauth-mcp-client-cache/
```

**Clear all tokens (force re-authentication):**
```bash
rm -rf ~/.fastmcp/oauth-mcp-client-cache/
```

**Clear tokens for specific server:**
```bash
# Find the hash directory for your server
ls ~/.fastmcp/oauth-mcp-client-cache/

# Remove that specific directory
rm -rf ~/.fastmcp/oauth-mcp-client-cache/<hash>/
```

---

## Mixed Authentication Scenarios

The gateway supports multiple authentication methods simultaneously:

### Example Configuration

```json
{
  "mcpServers": {
    "brave-search": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-brave-search"],
      "env": {"BRAVE_API_KEY": "${BRAVE_API_KEY}"}
    },
    "notion": {
      "url": "https://mcp.notion.com/mcp",
      "transport": "http"
    },
    "github": {
      "url": "https://github-mcp.example.com/mcp",
      "transport": "http"
    },
    "public-api": {
      "url": "https://public-mcp.example.com/mcp",
      "transport": "http"
    }
  }
}
```

### Authentication Methods

| Server | Transport | Authentication Method |
|--------|-----------|----------------------|
| brave-search | stdio | Environment variable (API key) |
| notion | HTTP | OAuth (auto-detected) |
| github | HTTP | OAuth (auto-detected) |
| public-api | HTTP | None (public API) |

### Startup Sequence

1. **brave-search** starts → Uses API key from `$BRAVE_API_KEY` → ✅ Ready
2. **notion** connects → Returns 401 → Browser opens for OAuth → ✅ Ready
3. **github** connects → Returns 401 → Browser opens for OAuth → ✅ Ready
4. **public-api** connects → Returns 200 → ✅ Ready (no auth needed)

**Two browser windows** open during startup (one for Notion, one for GitHub).

### Subsequent Startups

1. **brave-search** starts → Uses API key → ✅ Ready
2. **notion** connects → Uses cached tokens → ✅ Ready (no browser)
3. **github** connects → Uses cached tokens → ✅ Ready (no browser)
4. **public-api** connects → Returns 200 → ✅ Ready

**No browser windows** on subsequent runs.

---

## Troubleshooting

### Browser Doesn't Open

**Symptom:** Gateway logs show OAuth required, but browser doesn't open

**Possible Causes:**
1. System can't spawn browser process
2. Browser environment variables not set correctly
3. Running in headless environment
4. Desktop environment not available

**Solutions:**

**Test browser spawning:**
```bash
python -m webbrowser https://example.com
```

If this doesn't open a browser, check:
- Is a desktop environment running?
- Are browser environment variables set? (`$BROWSER`)
- Is the browser installed?

**For headless environments:** See [Headless Environments](#headless-environments)

---

### "Authentication Failed" Error

**Symptom:** Browser opens, but authentication fails

**Possible Causes:**
1. Incorrect server URL in `.mcp.json`
2. OAuth server unavailable
3. Permissions denied during auth flow
4. Network connectivity issues

**Solutions:**

**Verify server URL:**
```bash
curl -I https://mcp.notion.com/mcp
# Should return HTTP 401 with OAuth headers
```

**Check OAuth metadata:**
```bash
curl https://mcp.notion.com/.well-known/oauth-protected-resource
# Should return OAuth configuration JSON
```

**Review gateway logs:**
```bash
tail -f gateway-debug.log
# Look for detailed OAuth error messages
```

**Try manual authentication:**
1. Clear cached tokens: `rm -rf ~/.fastmcp/oauth-mcp-client-cache/`
2. Restart gateway with debug logging
3. Watch for specific error messages

---

### Tokens Not Working After Restart

**Symptom:** Browser opens every time gateway starts, tokens not cached

**Possible Causes:**
1. Token cache directory permissions issue
2. Tokens being deleted between runs
3. Different user account running gateway

**Solutions:**

**Check token cache permissions:**
```bash
ls -la ~/.fastmcp/oauth-mcp-client-cache/
# Should be readable/writable by current user
```

**Fix permissions if needed:**
```bash
chmod 700 ~/.fastmcp/oauth-mcp-client-cache/
chmod 600 ~/.fastmcp/oauth-mcp-client-cache/*/tokens.json
```

**Verify tokens persist:**
```bash
# After successful auth, check token file exists
cat ~/.fastmcp/oauth-mcp-client-cache/*/tokens.json
```

---

### "Token Expired" Errors

**Symptom:** OAuth was working, now getting 401 errors

**Possible Causes:**
1. Access token expired (normal, should auto-refresh)
2. Refresh token expired (requires re-authentication)
3. OAuth credentials revoked

**Solutions:**

**Check token expiration:**
```bash
cat ~/.fastmcp/oauth-mcp-client-cache/*/tokens.json
# Look at "expires_at" timestamp
```

**If refresh token expired:**
```bash
# Clear tokens and re-authenticate
rm -rf ~/.fastmcp/oauth-mcp-client-cache/
# Restart gateway - browser will open for new auth
```

**If credentials revoked:**
1. Check OAuth provider's app permissions page
2. Re-authorize the gateway
3. Clear cached tokens and restart

---

### Multiple Servers, Wrong Credentials

**Symptom:** Authenticated with wrong account for a server

**Example:** Accidentally used personal Notion account instead of work account

**Solution:**

**Clear tokens for specific server:**
```bash
# List all token directories
ls ~/.fastmcp/oauth-mcp-client-cache/

# Each directory is a hash of the server URL
# Remove the one for the server you want to re-authenticate
rm -rf ~/.fastmcp/oauth-mcp-client-cache/<hash-of-notion-url>/
```

**Restart gateway** - browser will open for that server only

---

## Headless Environments

OAuth requires browser interaction for initial authentication. For headless environments (Docker, CI/CD, remote servers):

### Option 1: Pre-Authenticate and Copy Tokens

**On your local machine (with browser):**

```bash
# 1. Run gateway locally with OAuth server configured
uv run python main.py

# 2. Complete OAuth flow in browser

# 3. Verify tokens cached
ls -la ~/.fastmcp/oauth-mcp-client-cache/

# 4. Copy tokens to remote server
scp -r ~/.fastmcp/oauth-mcp-client-cache/ user@remote-server:~/.fastmcp/
```

**On headless server:**

```bash
# Tokens already present, gateway will use them
uv run python main.py
# No browser needed - uses cached tokens
```

### Option 2: Mount Token Directory (Docker)

```bash
# Pre-authenticate on host machine
uv run python main.py
# Complete OAuth flow

# Run Docker with token volume mounted
docker run -v ~/.fastmcp/oauth-mcp-client-cache:/root/.fastmcp/oauth-mcp-client-cache \
  agent-mcp-gateway
```

### Option 3: Service Account Tokens (Advanced)

Some OAuth providers support long-lived service account tokens:

```bash
# Instead of OAuth, use service account token
export NOTION_API_TOKEN=secret_abc123...
```

**Note:** This requires the downstream MCP server to support token-based auth instead of OAuth. Not all servers support this.

### Token Expiration in Headless Environments

**Access tokens** refresh automatically (no problem)

**Refresh tokens** expire after 30-90 days of inactivity:
- You'll need to re-authenticate with browser
- Copy new tokens to headless environment again
- Consider setting up periodic token refresh on a machine with browser access

---

## Security Considerations

### Token Storage Security

**Tokens are stored in plaintext** in `~/.fastmcp/oauth-mcp-client-cache/`

**Recommendations:**
1. **Set strict permissions:**
   ```bash
   chmod 700 ~/.fastmcp/oauth-mcp-client-cache/
   chmod 600 ~/.fastmcp/oauth-mcp-client-cache/*/tokens.json
   ```

2. **Don't commit tokens to git:**
   - Add `~/.fastmcp/` to `.gitignore`
   - Never share token files

3. **For production environments:**
   - Consider encrypted storage
   - Use secrets management (Vault, AWS Secrets Manager, etc.)
   - Rotate tokens regularly

### OAuth Scope Permissions

**Review permissions** before granting access:
- What data can the gateway access?
- Can the gateway modify data or just read?
- What actions can the gateway perform?

**Principle of least privilege:**
- Only grant minimum permissions needed
- Review and revoke unused permissions periodically
- Use different accounts for different environments (dev vs prod)

### Shared Machines

If multiple users share a machine:
- Each user should have their own token cache (`~/.fastmcp/`)
- Tokens are user-specific (tied to who authenticated)
- Don't share token directories between users

---

## FAQ

### Do I need to configure OAuth in .mcp.json?

**No.** OAuth is auto-detected. Just add the server URL with `"transport": "http"`.

### Will OAuth work for stdio servers?

**No.** OAuth only works with HTTP/HTTPS transports. stdio servers use local process communication and typically authenticate via environment variables (API keys).

### Can I disable OAuth for a specific HTTP server?

**Not currently.** All HTTP servers have OAuth enabled, but it only activates if the server returns 401. If a server doesn't require OAuth, it will work normally without authentication.

### What happens if OAuth authentication fails?

The gateway logs an error and that server becomes unavailable. Other servers continue working normally. You can retry authentication by restarting the gateway.

### Can I use custom headers with OAuth?

**Partially.** Custom headers can be specified but may conflict with OAuth's `Authorization` header. The gateway will log a warning if custom headers are detected on an OAuth-enabled server. This is a known limitation.

### Do tokens work across different machines?

**Yes**, if you copy the entire `~/.fastmcp/oauth-mcp-client-cache/` directory. However, tokens are tied to the OAuth client registration, so ensure the gateway configuration is identical.

### How long do tokens last?

- **Access tokens:** 1 hour (typical)
- **Refresh tokens:** 30-90 days of inactivity (typical)

These durations vary by OAuth provider.

### What OAuth providers are supported?

The gateway supports **any OAuth 2.1 provider** that follows the MCP specification and RFC 9728 (OAuth Protected Resource Metadata). Known supported providers:
- Notion
- GitHub
- Google (if MCP server available)
- Any custom OAuth provider implementing MCP auth spec

### Can I use the gateway with multiple Notion workspaces?

**Yes**, but you'll need separate MCP server configurations for each workspace (different URLs). Each will have its own OAuth flow and cached tokens.

### What if I delete the token cache by accident?

No problem - just restart the gateway and browser will open for re-authentication. No data loss, just the inconvenience of logging in again.

### Does token refresh require browser interaction?

**No.** Token refresh happens automatically in the background using the refresh token. You only need browser interaction for initial authentication or if the refresh token expires.

---

## Related Documentation

- [README.md - OAuth Support Section](../README.md#oauth-support-for-downstream-servers)
- [OAuth Milestone Specification](specs/m1-oauth.md)
- [OAuth Proxying Research](downstream-mcp-oauth-proxying.md)
- [FastMCP OAuth Documentation](https://github.com/jlowin/fastmcp/blob/main/docs/clients/auth/oauth.mdx)
- [MCP Authorization Specification](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization)

---

## Support

For OAuth-related issues:

1. **Check this troubleshooting guide** first
2. **Review gateway logs** in `gateway-debug.log`
3. **Test OAuth flow manually** with the MCP server directly
4. **Check FastMCP OAuth docs** for client-side issues
5. **Check MCP server docs** for server-side OAuth configuration

**Common issue?** Open a GitHub issue with:
- Gateway version
- MCP server being accessed
- Error logs (with sensitive tokens redacted)
- Steps to reproduce
