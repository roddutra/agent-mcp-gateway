# Milestone M1: Policy Engine - Implicit Tool Grant

**Status:** Planning
**Version:** 0.2.0 (target)
**Reference:** [Policy Rules Specification](../policy-rules-specification.md)

## Problem Statement

Current policy engine requires explicit tool permissions for every server, even when the intent is "grant all tools." This creates verbose configurations and poor UX.

**Example of current problem:**
```json
{
  "admin": {
    "allow": {
      "servers": ["*"],
      "tools": {
        "playwright": ["*"],
        "brave-search": ["*"],
        "context7": ["*"],
        "github": ["*"],
        "notion": ["*"]
        // Must explicitly add ["*"] for EVERY server
      }
    }
  }
}
```

**Desired behavior:**
```json
{
  "admin": {
    "allow": {
      "servers": ["*"]
      // Implicitly grants all tools from all servers
    }
  }
}
```

## Objectives

1. Implement implicit tool grant: server access grants all tools by default
2. Maintain backward compatibility: existing explicit tool configs continue to work
3. Preserve security: deny-before-allow precedence and fine-grained control remain
4. Update tests to validate new behavior
5. Update documentation and examples

## Success Criteria

- [ ] `admin` agent with `"servers": ["*"]` can access all tools from all servers
- [ ] `default` agent with `"servers": ["context7"]` can access all tools from context7
- [ ] Explicit `allow.tools` entries narrow access from implicit all
- [ ] `deny.tools` entries filter tools from granted set
- [ ] All existing precedence tests pass
- [ ] New implicit grant tests pass
- [ ] Documentation reflects new behavior
- [ ] Config examples simplified where appropriate

## Implementation Tasks

### 1. Core Logic Changes

#### File: `src/policy.py`

**Method: `can_access_tool()` (lines 100-173)**

**CRITICAL: Current precedence order is WRONG and must be fixed!**

**Current precedence (INCORRECT):**
```python
# 1. Explicit deny rules (line ~134)
if tool in explicit_deny:
    return False

# 2. Explicit allow rules (line ~139) ← WRONG POSITION
if tool in explicit_allow:
    return True

# 3. Wildcard deny rules (line ~145) ← WRONG POSITION
for pattern in wildcard_deny:
    if self._matches_pattern(tool, pattern):
        return False

# 4. Wildcard allow rules (line ~167)
for pattern in wildcard_allow:
    if self._matches_pattern(tool, pattern):
        return True

# 5. Default policy (line 173)
return False
```

**Required changes:**

1. **Reorder precedence (lines 129-170):**
```python
# 1. Explicit deny rules (CORRECT - keep as is)
if tool in explicit_deny:
    return False

# 2. Wildcard deny rules (MOVE UP - check before any allows)
for pattern in wildcard_deny:
    if self._matches_pattern(tool, pattern):
        return False

# 3. Explicit allow rules (MOVE DOWN - check after all denies)
if tool in explicit_allow:
    return True

# 4. Wildcard allow rules (CORRECT - keep as is)
for pattern in wildcard_allow:
    if self._matches_pattern(tool, pattern):
        return True
```

2. **Add implicit grant check (before line 173):**
```python
# 5. Implicit grant - if server allowed but no allow rules, grant all tools
if not allow_tools:
    # No allow tool rules for this server
    # Server access implicitly grants all tools
    # (Deny rules already filtered in steps 1-2)
    return True

# 6. Default policy - if no rules match, deny
return False
```

**Why this order is critical:**
- **All deny rules MUST be checked before any allow rules**
- Current implementation allows explicit allow to override wildcard deny (SECURITY BUG)
- Example: With `allow: ["delete_user"]` and `deny: ["delete_*"]`, current code ALLOWS delete_user (wrong)
- Correct behavior: deny `delete_*` should block delete_user despite explicit allow

**Implicit grant logic - CRITICAL:**
- Condition: `if not allow_tools` (NOT checking deny_tools)
- `allow_tools = agent_rules.get("allow", {}).get("tools", {}).get(server, [])`
- If server not in `allow.tools` → `allow_tools` is `[]` (empty)
- Empty allow_tools means no restrictions → grant all tools from that server
- **Why not check deny_tools:** Deny rules already evaluated in steps 1-2. If we reach step 5, this specific tool wasn't denied. The presence of deny rules for OTHER tools shouldn't block implicit grant for THIS tool.

**Example proving why deny_tools check would be wrong:**
```json
{
  "allow": {"servers": ["playwright"]},  // No allow.tools entry
  "deny": {"tools": {"playwright": ["browser_type"]}}
}
```

With `if not allow_tools and not deny_tools`:
- For "browser_navigate": allow_tools=[], deny_tools=["browser_type"]
- Condition: `if True and False` → False → Falls to default deny → **DENIED** ❌ (WRONG!)

With `if not allow_tools`:
- For "browser_navigate": Steps 1-2 check deny, no match → Step 5: `if True` → **ALLOWED** ✓ (CORRECT!)
- For "browser_type": Step 1 explicit deny → **DENIED** ✓ (CORRECT!)

### 2. Test Updates

#### File: `tests/test_policy.py`

**Remove/Update Test (line 482):**
```python
def test_no_tool_rules_defaults_to_deny(self):
    """Test that no tool rules means deny access."""
```
**Action:** DELETE this test (behavior changing to implicit grant)

**Add New Tests:**

```python
def test_no_tool_rules_defaults_to_implicit_grant(self):
    """Test that no tool rules means implicit grant of all tools."""
    rules = {
        "agents": {
            "test": {
                "allow": {
                    "servers": ["db"]
                    # No tools section - should grant all tools implicitly
                }
            }
        }
    }

    engine = PolicyEngine(rules)

    assert engine.can_access_server("test", "db") is True
    assert engine.can_access_tool("test", "db", "any_tool") is True
    assert engine.can_access_tool("test", "db", "another_tool") is True
    assert engine.can_access_tool("test", "db", "query") is True


def test_explicit_tool_rules_override_implicit_grant(self):
    """Test that explicit tool rules narrow access from implicit grant."""
    rules = {
        "agents": {
            "test": {
                "allow": {
                    "servers": ["db"],
                    "tools": {
                        "db": ["query", "list_tables"]
                    }
                }
            }
        }
    }

    engine = PolicyEngine(rules)

    assert engine.can_access_server("test", "db") is True
    assert engine.can_access_tool("test", "db", "query") is True
    assert engine.can_access_tool("test", "db", "list_tables") is True
    assert engine.can_access_tool("test", "db", "drop_table") is False  # Not in explicit list


def test_wildcard_tools_grant_all_explicitly(self):
    """Test that explicit wildcard ["*"] grants all tools."""
    rules = {
        "agents": {
            "test": {
                "allow": {
                    "servers": ["db"],
                    "tools": {
                        "db": ["*"]
                    }
                }
            }
        }
    }

    engine = PolicyEngine(rules)

    assert engine.can_access_tool("test", "db", "any_tool") is True
    assert engine.can_access_tool("test", "db", "another_tool") is True


def test_deny_tools_filters_implicit_grant(self):
    """Test that deny.tools filters tools from implicit grant."""
    rules = {
        "agents": {
            "test": {
                "allow": {
                    "servers": ["db"]
                    # No tools - implicit grant all
                },
                "deny": {
                    "tools": {
                        "db": ["drop_*", "delete_*"]
                    }
                }
            }
        }
    }

    engine = PolicyEngine(rules)

    # Should allow most tools (implicit grant)
    assert engine.can_access_tool("test", "db", "query") is True
    assert engine.can_access_tool("test", "db", "insert") is True
    assert engine.can_access_tool("test", "db", "list_tables") is True

    # Should deny dangerous tools
    assert engine.can_access_tool("test", "db", "drop_table") is False
    assert engine.can_access_tool("test", "db", "drop_database") is False
    assert engine.can_access_tool("test", "db", "delete_user") is False


def test_admin_wildcard_servers_grants_all_tools(self):
    """Test that admin with servers:['*'] gets all tools from all servers."""
    rules = {
        "agents": {
            "admin": {
                "allow": {
                    "servers": ["*"]
                    # No tools section - should grant all tools from all servers
                }
            }
        }
    }

    engine = PolicyEngine(rules)

    # All servers accessible
    assert engine.can_access_server("admin", "playwright") is True
    assert engine.can_access_server("admin", "brave-search") is True
    assert engine.can_access_server("admin", "github") is True

    # All tools accessible (implicit grant)
    assert engine.can_access_tool("admin", "playwright", "browser_navigate") is True
    assert engine.can_access_tool("admin", "brave-search", "brave_web_search") is True
    assert engine.can_access_tool("admin", "github", "create_issue") is True


def test_mixed_explicit_and_implicit_tool_grants(self):
    """Test combination of servers with explicit tool rules and implicit grants."""
    rules = {
        "agents": {
            "test": {
                "allow": {
                    "servers": ["db", "api", "filesystem"],
                    "tools": {
                        "db": ["query"],  # Explicit restriction
                        # "api" has no tools entry - implicit grant all
                        "filesystem": ["read_*"]  # Explicit restriction
                    }
                }
            }
        }
    }

    engine = PolicyEngine(rules)

    # db: only query allowed
    assert engine.can_access_tool("test", "db", "query") is True
    assert engine.can_access_tool("test", "db", "insert") is False

    # api: all tools allowed (implicit)
    assert engine.can_access_tool("test", "api", "get_data") is True
    assert engine.can_access_tool("test", "api", "post_data") is True
    assert engine.can_access_tool("test", "api", "delete_data") is True

    # filesystem: only read_* pattern allowed
    assert engine.can_access_tool("test", "filesystem", "read_file") is True
    assert engine.can_access_tool("test", "filesystem", "read_directory") is True
    assert engine.can_access_tool("test", "filesystem", "write_file") is False
```

**Tests that need FIXING (currently validate WRONG behavior):**

```python
def test_explicit_allow_overrides_wildcard_deny(self):
    """Test that explicit allow (level 2) overrides wildcard deny (level 3)."""
    # Line 101-130 in test_policy.py
    # This test validates the WRONG precedence order
    # MUST BE UPDATED to expect deny to win
```

**Update this test to:**
```python
def test_wildcard_deny_overrides_explicit_allow(self):
    """Test that wildcard deny overrides explicit allow (deny-first precedence)."""
    rules = {
        "agents": {
            "test_agent": {
                "allow": {
                    "servers": ["db"],
                    "tools": {"db": ["delete_user", "delete_data", "get_user"]}
                },
                "deny": {
                    "tools": {"db": ["delete_*"]}
                }
            }
        }
    }

    engine = PolicyEngine(rules)

    # Should DENY delete_user (wildcard deny wins over explicit allow)
    assert engine.can_access_tool("test_agent", "db", "delete_user") is False

    # Should DENY delete_data (wildcard deny wins over explicit allow)
    assert engine.can_access_tool("test_agent", "db", "delete_data") is False

    # Should DENY delete_something_else (wildcard deny, not in explicit allow)
    assert engine.can_access_tool("test_agent", "db", "delete_something_else") is False

    # Should ALLOW get_user (no deny rule matches)
    assert engine.can_access_tool("test_agent", "db", "get_user") is True
```

**Tests to verify still pass (after precedence fix):**
- Other precedence tests in `TestDenyBeforeAllowPrecedence` class (lines 11-192) - may need adjustment
- Wildcard pattern matching tests
- Multi-agent tests
- Unknown agent tests

### 3. Configuration Examples

#### File: `config/.mcp-gateway-rules.json.example`

**Update admin agent (lines 10-24):**

**Before:**
```json
"admin": {
  "allow": {
    "servers": ["*"],
    "tools": {
      "postgres": ["*"],
      "filesystem": ["*"],
      "brave-search": ["*"],
      "context7": ["*"]
    }
  }
}
```

**After:**
```json
"admin": {
  "allow": {
    "servers": ["*"]
  }
}
```

**Update claude-desktop agent (lines 26-68):**

**Before:**
```json
"claude-desktop": {
  "allow": {
    "servers": ["brave-search", "context7", "playwright", "crawl4ai", "github", "notion"],
    "tools": {
      "brave-search": ["*"],
      "context7": ["*"],
      "crawl4ai": ["md", "screenshot", "crawl"],
      "github": ["*"],
      "notion": ["*"],
      "playwright": [
        "browser_navigate",
        "browser_click",
        "browser_navigate_back",
        "browser_type",
        "browser_press_key",
        "browser_network_requests",
        "browser_snapshot",
        "browser_take_screenshot",
        "browser_select_option",
        "browser_wait_for",
        "browser_close",
        "browser_resize"
      ]
    }
  }
}
```

**After (option 1 - simplified):**
```json
"claude-desktop": {
  "allow": {
    "servers": ["brave-search", "context7", "playwright", "crawl4ai", "github", "notion"],
    "tools": {
      "crawl4ai": ["md", "screenshot", "crawl"]
      // All other servers get implicit grant of all tools
    }
  }
}
```

**After (option 2 - with explicit deny for documentation):**
```json
"claude-desktop": {
  "allow": {
    "servers": ["brave-search", "context7", "playwright", "crawl4ai", "github", "notion"],
    "tools": {
      "crawl4ai": ["md", "screenshot", "crawl"]
    }
  },
  "deny": {
    "tools": {
      "playwright": ["browser_execute_script"]  // Example: block dangerous tools
    }
  }
}
```

**Keep backend agent unchanged (good example of explicit restrictions):**
```json
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
```

### 4. Documentation Updates

#### File: `README.md`

**Section: Policy Evaluation (find and update)**

Update policy evaluation logic explanation to include implicit grant behavior.

**Before:**
```
Tool access requires explicit permission via allow.tools configuration.
```

**After:**
```
Tool access is implicitly granted when server is allowed, unless explicit tool rules narrow access. Specify allow.tools only when restricting to specific tools.
```

Add example showing implicit grant:
```markdown
#### Example: Simple Admin Access

```json
{
  "admin": {
    "allow": {
      "servers": ["*"]
    }
  }
}
```

Grants admin access to all servers and all tools (implicit grant).
```

#### File: `CLAUDE.md`

**Section: Policy Evaluation Rules (lines 49-57)**

Update the precedence order to include implicit grant step:

**Before (INCORRECT):**
```
### Policy Evaluation Rules (CRITICAL - DO NOT CHANGE)

**Exact precedence order:**
1. Explicit deny rules
2. Explicit allow rules
3. Wildcard deny rules
4. Wildcard allow rules
5. Default policy
```

**After (CORRECTED):**
```
### Policy Evaluation Rules (CRITICAL - DO NOT CHANGE)

**Exact precedence order with short-circuit evaluation:**
1. Explicit deny rules → if match, DENY and STOP
2. Wildcard deny rules → if match, DENY and STOP
3. Explicit allow rules → if match, ALLOW and STOP
4. Wildcard allow rules → if match, ALLOW and STOP
5. Implicit grant - if server allowed but no tool rules specified → ALLOW and STOP
6. Default policy → DENY

**Critical principle:** All deny rules (explicit + wildcard) checked before any allow rules.
```

**Section: Gateway Tools (around line 19)**

Update description of behavior to mention implicit grant.

### 5. Changelog

#### File: `CHANGELOG.md`

Add entry for version 0.2.0:

```markdown
## [0.2.0] - YYYY-MM-DD

### Changed
- **BREAKING (behavioral):** Policy engine now implicitly grants all tools when server is allowed without explicit tool rules
  - `allow.servers` without corresponding `allow.tools` entry now grants all tools from that server
  - Explicit `allow.tools` entries narrow access from implicit grant
  - `deny.tools` entries filter tools from granted set
  - Existing configs with explicit tool grants continue to work unchanged
  - See [Policy Rules Specification](docs/policy-rules-specification.md) for details

### Migration
- Configs relying on implicit deny-by-default may now grant unintended access
- Review agents with `allow.servers` but no `allow.tools` - these now grant all tools
- Add explicit `allow.tools` entries to maintain previous restricted behavior if needed
```

## Testing Strategy

### Unit Tests
- [ ] Run full test suite: `pytest tests/test_policy.py -v`
- [ ] Verify all new implicit grant tests pass
- [ ] Verify all existing precedence tests still pass
- [ ] Verify backward compatibility tests pass

### Integration Tests
- [ ] Test with actual gateway: admin agent can access all tools
- [ ] Test with actual gateway: explicit tool rules properly narrow access
- [ ] Test with actual gateway: deny rules properly filter tools

### Manual Verification
- [ ] Update local `.mcp-gateway-rules.json` with simplified admin config
- [ ] Run `list_servers` with admin agent - verify sees all servers
- [ ] Run `get_server_tools` with admin agent for various servers - verify sees all tools
- [ ] Run `execute_tool` with admin agent - verify can execute any tool

## Rollback Plan

If issues arise:
1. Revert `src/policy.py` changes to line 173
2. Restore test `test_no_tool_rules_defaults_to_deny`
3. Remove new implicit grant tests
4. Revert config examples to explicit tool grants
5. Tag as version 0.1.6 with "Revert implicit grant" in changelog

## Security Considerations

**Risk:** Existing agents may gain unintended tool access.

**Mitigation:**
1. Mark as BREAKING change in changelog
2. Document migration path clearly
3. Recommend security audit of all agent configurations before upgrading
4. Provide config validation command to detect affected agents (future enhancement)

**Impact Assessment:**
- Low risk: Agents with explicit tool rules (behavior unchanged)
- Medium risk: Agents with server access but no tool rules (now grant all tools)
- High risk: Production agents with overly broad server access (e.g., `servers: ["*"]`)

**Recommendation:**
- Review all production agent configurations before deploying v0.2.0
- Add explicit `allow.tools` entries where needed to maintain least privilege
- Use `deny.tools` as additional safety net for critical servers

## Timeline

**Estimated effort:** 4-6 hours
- Policy engine changes: 30 minutes
- Test updates: 2 hours
- Configuration examples: 30 minutes
- Documentation updates: 1 hour
- Testing and verification: 1-2 hours

## References

- [Policy Rules Specification](../policy-rules-specification.md) - Desired end state
- `src/policy.py` - Current implementation
- `tests/test_policy.py` - Test suite
- Issue: Gateway rules require explicit tool permissions even when intent is "grant all"
