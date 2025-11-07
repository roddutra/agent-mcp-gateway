# Policy Rules Specification

**Version:** 1.0
**Status:** Desired End State
**Purpose:** Define expected policy evaluation logic for agent-mcp-gateway

## Overview

Gateway policies control which agents can access which MCP servers and tools. Rules follow a hierarchical model: server access is granted first, then tool access is evaluated. The key principle: **granting server access implicitly grants all tools unless explicitly restricted**.

## Configuration Structure

```json
{
  "agents": {
    "agent-name": {
      "allow": {
        "servers": ["server1", "server2", "*"],
        "tools": {
          "server1": ["tool1", "tool2", "*"],
          "server2": ["pattern_*", "exact_name"]
        }
      },
      "deny": {
        "servers": ["excluded-server"],
        "tools": {
          "server1": ["dangerous_tool", "drop_*"]
        }
      }
    }
  },
  "defaults": {
    "deny_on_missing_agent": false
  }
}
```

## Hierarchy of Access Control

### Level 1: Server Access

**Rule:** Agent must have server access before any tool access is evaluated.

**Evaluation:**
1. If server in `deny.servers` → **deny** (explicit or wildcard)
2. If server in `allow.servers` → **allow** (explicit or wildcard)
3. Otherwise → **deny**

**Implicit Behavior:**
- `"servers": ["*"]` grants access to ALL configured servers
- `"servers": ["playwright"]` grants access to playwright server only

### Level 2: Tool Access (Conditional on Server Access)

**Rule:** If agent has server access, evaluate tool permissions.

**Key Principle - Implicit Tool Grant:**
- If server in `allow.servers` AND no `allow.tools` entry for that server → **implicitly grant all tools** (equivalent to `["*"]`)
- If `allow.tools` specifies rules for the server → **only grant specified tools** (narrow from implicit all)
- If `deny.tools` specifies rules for the server → **remove specified tools** (filter from granted set)

**CRITICAL: Implicit grant is triggered ONLY by absence of `allow.tools` entry, NOT by absence of both allow and deny rules.**

Example:
```json
{
  "allow": {"servers": ["playwright"]},  // No allow.tools entry
  "deny": {"tools": {"playwright": ["browser_type"]}}  // Deny rules present
}
```
Result: Implicit grant applies. All 21 playwright tools granted, then "browser_type" is filtered out by deny rule → 20 tools accessible.

## Evaluation Precedence Order

Tool access follows strict precedence with **short-circuit evaluation** (DO NOT CHANGE):

**Critical Principle:** Deny rules ALWAYS override allow rules. All denies checked before any allows.

1. **Explicit deny rules** - specific tool names in `deny.tools.{server}` → if match, DENY and STOP
2. **Wildcard deny rules** - patterns like `drop_*` in `deny.tools.{server}` → if match, DENY and STOP
3. **Explicit allow rules** - specific tool names in `allow.tools.{server}` → if match, ALLOW and STOP
4. **Wildcard allow rules** - patterns like `get_*` or `*` in `allow.tools.{server}` → if match, ALLOW and STOP
5. **Implicit grant** - if server allowed but no `allow.tools.{server}` entry → ALLOW and STOP
6. **Default deny** - if no rules matched → DENY

Each rule is checked in order. As soon as a match is found, that decision is returned and evaluation stops.

## Wildcard Support

### Server-Level Wildcards

**Supported in both `allow.servers` and `deny.servers`:**
- `"*"` - matches all servers
- `"browser_*"` - matches servers starting with "browser_"
- Patterns use glob-style matching (fnmatch)

### Tool-Level Wildcards

**Supported in both `allow.tools.{server}` and `deny.tools.{server}`:**
- `"*"` - matches all tools
- `"get_*"` - matches tools starting with "get_"
- `"*_query"` - matches tools ending with "_query"
- `"drop_*"` - matches tools starting with "drop_"
- Patterns use glob-style matching (fnmatch)

## Behavioral Examples

### Example 1: Admin with Full Access

```json
{
  "admin": {
    "allow": {
      "servers": ["*"]
    }
  }
}
```

**Behavior:**
- Server access: ALL servers ✓
- Tool access: ALL tools from ALL servers ✓ (implicit grant)
- No need to specify tools for each server

### Example 2: Admin with One Server Restricted

```json
{
  "admin": {
    "allow": {
      "servers": ["*"],
      "tools": {
        "brave-search": ["brave_web_search"]
      }
    }
  }
}
```

**Behavior:**
- Server access: ALL servers ✓
- Tool access for `brave-search`: ONLY `brave_web_search` ✓ (explicit restriction)
- Tool access for other servers: ALL tools ✓ (implicit grant)

### Example 3: Admin with Mixed Access Patterns

```json
{
  "admin": {
    "allow": {
      "servers": ["*"],
      "tools": {
        "brave-search": ["brave_web_search"]
      }
    },
    "deny": {
      "servers": ["notion"],
      "tools": {
        "playwright": ["browser_type"]
      }
    }
  }
}
```

**Evaluation walkthrough:**

**notion server:**
- Server level: "notion" in `deny.servers` → **SERVER DENIED** ✗
- Tools never evaluated (server blocked)

**playwright server (21 tools):**
- Server level: "*" in `allow.servers`, "notion" ≠ "playwright" → **SERVER ALLOWED** ✓
- Tool "browser_type": Step 1 explicit deny → **DENIED** ✗
- Tool "browser_navigate": Steps 1-2 no deny match → Step 5 implicit grant (`allow.tools` has no playwright entry) → **ALLOWED** ✓
- Other 19 tools: Same as browser_navigate → **ALLOWED** ✓
- **Result: 20/21 tools accessible**

**brave-search server:**
- Server level: "*" in `allow.servers` → **SERVER ALLOWED** ✓
- Tool "brave_web_search": Step 3 explicit allow → **ALLOWED** ✓
- Tool "brave_local_search": No matches → Step 5 implicit grant fails (allow_tools exists) → Step 6 default deny → **DENIED** ✗
- **Result: 1 tool accessible (only brave_web_search)**

**github server (no tool rules):**
- Server level: "*" in `allow.servers` → **SERVER ALLOWED** ✓
- Any tool: Steps 1-4 no matches → Step 5 implicit grant (no `allow.tools` entry) → **ALLOWED** ✓
- **Result: ALL tools accessible**

**Summary:**
- notion: 0 servers, 0 tools (server blocked)
- playwright: 1 server, 20/21 tools (implicit grant with 1 tool denied)
- brave-search: 1 server, 1/N tools (explicit restriction)
- github (and others): 1 server each, all tools (implicit grant)

### Example 4: Dangerous Tools Denied with Wildcards

```json
{
  "admin": {
    "allow": {
      "servers": ["*"]
    },
    "deny": {
      "tools": {
        "playwright": ["browser_type"],
        "postgres": ["drop_*", "delete_*"]
      }
    }
  }
}
```

**Behavior:**
- Server access: ALL servers ✓
- Tool access for `playwright`: ALL tools EXCEPT `browser_type` ✓
- Tool access for `postgres`: ALL tools EXCEPT those matching `drop_*` or `delete_*` ✓
- Tool access for other servers: ALL tools ✓ (implicit grant)

### Example 5: Default Agent with Limited Access

```json
{
  "default": {
    "allow": {
      "servers": ["context7"]
    }
  }
}
```

**Behavior:**
- Server access: ONLY `context7` ✓
- Tool access for `context7`: ALL tools from context7 ✓ (implicit grant)
- Access to other servers: DENIED ✗

### Example 6: Backend Agent with Narrow Permissions

```json
{
  "backend": {
    "allow": {
      "servers": ["postgres", "filesystem"],
      "tools": {
        "postgres": ["query", "list_*"],
        "filesystem": ["read_*", "list_*"]
      }
    },
    "deny": {
      "tools": {
        "postgres": ["drop_*", "delete_*"],
        "filesystem": ["write_*", "delete_*"]
      }
    }
  }
}
```

**Behavior:**
- Server access: `postgres` and `filesystem` ✓
- Tool access for `postgres`: ONLY `query` and tools matching `list_*` ✓ (explicit restriction)
- Tool access for `filesystem`: ONLY tools matching `read_*` or `list_*` ✓ (explicit restriction)
- Deny rules are redundant here (already narrowed by allow rules) but serve as safety net

### Example 7: Precedence - Deny Always Overrides Allow

```json
{
  "agent": {
    "allow": {
      "servers": ["db"],
      "tools": {
        "db": ["delete_user", "delete_data", "get_user"]
      }
    },
    "deny": {
      "tools": {
        "db": ["delete_*"]
      }
    }
  }
}
```

**Behavior:**
- `delete_user`: DENIED ✗ (matches wildcard deny - deny overrides explicit allow)
- `delete_data`: DENIED ✗ (matches wildcard deny - deny overrides explicit allow)
- `delete_anything_else`: DENIED ✗ (not in explicit allow, matches wildcard deny)
- `get_user`: ALLOWED ✓ (explicit allow, no deny rules match)
- `insert_user`: DENIED ✗ (not in explicit allow list)

**Key Insight:** Even though `delete_user` and `delete_data` are explicitly allowed, the wildcard deny `delete_*` is checked first and blocks access. Deny rules always win.

## Semantic Meaning

### Allow Rules

**`allow.servers`:** "Agent CAN access these servers"
**`allow.tools`:** "Agent can ONLY access these specific tools (narrowing from implicit all)"

### Deny Rules

**`deny.servers`:** "Agent CANNOT access these servers (even if in allow.servers)"
**`deny.tools`:** "Agent CANNOT access these specific tools (filtering from granted set)"

## Key Differences from Current Implementation

**Current (v0.1.5):** Server access does NOT grant tool access. Tools must be explicitly specified.

**Desired (this spec):** Server access DOES grant all tools by default. Explicit tool rules narrow/filter access.

**Why Change:**
- Better UX: `"servers": ["*"]` should mean "all servers, all tools"
- Less verbose config: No need to add `"tools": {"server": ["*"]}` for every server
- Clearer semantics: `allow.tools` becomes opt-in restriction, not requirement
- Maintains security: Deny rules and explicit tool lists still provide fine-grained control

## Edge Cases

**Empty allow.tools for server:** Implicit grant (all tools)
**Empty deny.tools for server:** No tools denied
**Server in both allow and deny:** Deny wins (deny-before-allow)
**Tool in both allow and deny:** Deny always wins (all denies checked before any allows)
**Unknown agent_id:** Follow `deny_on_missing_agent` default
**Server allowed, but downstream unavailable:** Return appropriate error (not policy issue)

## Migration Path

Existing configs following explicit-grant model will continue to work:
- If `allow.tools` is already specified → behavior unchanged
- If `allow.tools` is omitted → now grants all tools (new behavior)

Users wanting to maintain strict deny-by-default can:
- Add explicit `allow.tools` entries for each server
- Or use `deny.tools` to block all except specific patterns
