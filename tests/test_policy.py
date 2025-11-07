"""Unit tests for policy evaluation engine.

CRITICAL: Tests for deny-before-allow precedence are the most important tests
in this file. This precedence order must NEVER be violated.
"""

import pytest
from src.policy import PolicyEngine


class TestDenyBeforeAllowPrecedence:
    """CRITICAL: Tests for deny-before-allow precedence rules.

    These tests are the most important in the entire test suite.
    The precedence order MUST be:
    1. Explicit deny rules
    2. Explicit allow rules
    3. Wildcard deny rules
    4. Wildcard allow rules
    5. Default policy
    """

    def test_explicit_deny_overrides_wildcard_allow(self):
        """Test that explicit deny takes precedence over wildcard allow."""
        rules = {
            "agents": {
                "test_agent": {
                    "allow": {
                        "servers": ["postgres"],
                        "tools": {"postgres": ["*"]}  # Wildcard allow ALL
                    },
                    "deny": {
                        "tools": {"postgres": ["drop_table"]}  # Explicit deny
                    }
                }
            },
            "defaults": {"deny_on_missing_agent": True}
        }

        engine = PolicyEngine(rules)

        # Should allow query (matches wildcard allow, no deny)
        assert engine.can_access_tool("test_agent", "postgres", "query") is True

        # Should deny drop_table (explicit deny overrides wildcard allow)
        assert engine.can_access_tool("test_agent", "postgres", "drop_table") is False

    def test_wildcard_deny_overrides_wildcard_allow(self):
        """Test that wildcard deny patterns take precedence over wildcard allow."""
        rules = {
            "agents": {
                "test_agent": {
                    "allow": {
                        "servers": ["postgres"],
                        "tools": {"postgres": ["*"]}  # Wildcard allow
                    },
                    "deny": {
                        "tools": {"postgres": ["drop_*"]}  # Pattern deny
                    }
                }
            },
            "defaults": {"deny_on_missing_agent": True}
        }

        engine = PolicyEngine(rules)

        # Should allow query (matches wildcard allow, no deny)
        assert engine.can_access_tool("test_agent", "postgres", "query") is True

        # Should deny drop_table (matches deny pattern, even though wildcard allows)
        assert engine.can_access_tool("test_agent", "postgres", "drop_table") is False

        # Should deny drop_database (matches deny pattern)
        assert engine.can_access_tool("test_agent", "postgres", "drop_database") is False

    def test_explicit_deny_overrides_explicit_allow(self):
        """Test that explicit deny overrides explicit allow for same tool."""
        rules = {
            "agents": {
                "test_agent": {
                    "allow": {
                        "servers": ["db"],
                        "tools": {"db": ["dangerous_tool", "safe_tool"]}
                    },
                    "deny": {
                        "tools": {"db": ["dangerous_tool"]}  # Also in allow
                    }
                }
            },
            "defaults": {"deny_on_missing_agent": True}
        }

        engine = PolicyEngine(rules)

        # Should deny dangerous_tool (deny overrides allow)
        assert engine.can_access_tool("test_agent", "db", "dangerous_tool") is False

        # Should allow safe_tool (only in allow, not in deny)
        assert engine.can_access_tool("test_agent", "db", "safe_tool") is True

    def test_wildcard_deny_overrides_explicit_allow(self):
        """Test that wildcard deny (level 2) overrides explicit allow (level 3)."""
        rules = {
            "agents": {
                "test_agent": {
                    "allow": {
                        "servers": ["db"],
                        "tools": {"db": ["delete_user", "delete_data", "get_user"]}
                    },
                    "deny": {
                        "tools": {"db": ["delete_*"]}  # Pattern deny
                    }
                }
            },
            "defaults": {"deny_on_missing_agent": True}
        }

        engine = PolicyEngine(rules)

        # Should DENY delete_user (wildcard deny wins over explicit allow)
        assert engine.can_access_tool("test_agent", "db", "delete_user") is False

        # Should DENY delete_data (wildcard deny wins over explicit allow)
        assert engine.can_access_tool("test_agent", "db", "delete_data") is False

        # Should ALLOW get_user (in allow list, doesn't match deny pattern)
        assert engine.can_access_tool("test_agent", "db", "get_user") is True

        # Should DENY delete_something_else (wildcard deny, not in explicit allow)
        assert engine.can_access_tool("test_agent", "db", "delete_something_else") is False

    def test_wildcard_deny_blocks_all_matching_tools(self):
        """Test that wildcard deny blocks all tools matching the pattern."""
        # This tests that wildcard deny (level 2) overrides explicit allow (level 3)
        rules = {
            "agents": {
                "test_agent": {
                    "allow": {
                        "servers": ["db"],
                        "tools": {"db": ["drop_old_data", "query"]}  # Explicit allow for tools
                    },
                    "deny": {
                        "tools": {"db": ["drop_*"]}  # Pattern deny
                    }
                }
            },
            "defaults": {"deny_on_missing_agent": True}
        }

        engine = PolicyEngine(rules)

        # Should DENY drop_old_data (wildcard deny beats explicit allow)
        # This is level 2 (wildcard deny) vs level 3 (explicit allow)
        assert engine.can_access_tool("test_agent", "db", "drop_old_data") is False

        # Should DENY drop_table (matches wildcard deny, not in explicit allow)
        assert engine.can_access_tool("test_agent", "db", "drop_table") is False

        # Should ALLOW query (in explicit allow, doesn't match deny pattern)
        assert engine.can_access_tool("test_agent", "db", "query") is True

    def test_complex_precedence_scenario(self):
        """Test complex scenario with multiple precedence levels."""
        rules = {
            "agents": {
                "backend": {
                    "allow": {
                        "servers": ["postgres"],
                        "tools": {
                            "postgres": ["*", "query", "read_data"]  # Wildcard + explicit
                        }
                    },
                    "deny": {
                        "tools": {
                            "postgres": ["drop_*", "delete_all"]  # Pattern + explicit
                        }
                    }
                }
            },
            "defaults": {"deny_on_missing_agent": True}
        }

        engine = PolicyEngine(rules)

        # Allowed by wildcard, not denied
        assert engine.can_access_tool("backend", "postgres", "insert_data") is True
        assert engine.can_access_tool("backend", "postgres", "query") is True

        # Denied by explicit deny
        assert engine.can_access_tool("backend", "postgres", "delete_all") is False

        # Denied by pattern
        assert engine.can_access_tool("backend", "postgres", "drop_table") is False
        assert engine.can_access_tool("backend", "postgres", "drop_index") is False


class TestImplicitGrant:
    """Test cases for implicit tool grant behavior."""

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
        """Test that explicit wildcard ['*'] grants all tools."""
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

    def test_deny_with_implicit_grant_per_server(self):
        """Test that deny.tools are server-specific with implicit grant."""
        rules = {
            "agents": {
                "test": {
                    "allow": {
                        "servers": ["db1", "db2"]
                        # No tools - implicit grant for both servers
                    },
                    "deny": {
                        "tools": {
                            "db1": ["drop_*"]  # Only deny on db1
                        }
                    }
                }
            }
        }

        engine = PolicyEngine(rules)

        # db1: implicit grant minus drop_*
        assert engine.can_access_tool("test", "db1", "query") is True
        assert engine.can_access_tool("test", "db1", "insert") is True
        assert engine.can_access_tool("test", "db1", "drop_table") is False  # Denied

        # db2: full implicit grant (no deny rules)
        assert engine.can_access_tool("test", "db2", "query") is True
        assert engine.can_access_tool("test", "db2", "insert") is True
        assert engine.can_access_tool("test", "db2", "drop_table") is True  # Allowed


class TestWildcardPatternMatching:
    """Test cases for wildcard pattern matching functionality."""

    def test_wildcard_star_matches_all(self):
        """Test that '*' pattern matches all tool names."""
        rules = {
            "agents": {
                "test": {
                    "allow": {
                        "servers": ["api"],
                        "tools": {"api": ["*"]}
                    }
                }
            }
        }

        engine = PolicyEngine(rules)

        assert engine.can_access_tool("test", "api", "any_tool") is True
        assert engine.can_access_tool("test", "api", "another_tool") is True
        assert engine.can_access_tool("test", "api", "get_data") is True

    def test_prefix_wildcard(self):
        """Test that 'get_*' pattern matches tools starting with 'get_'."""
        rules = {
            "agents": {
                "test": {
                    "allow": {
                        "servers": ["api"],
                        "tools": {"api": ["get_*"]}
                    }
                }
            }
        }

        engine = PolicyEngine(rules)

        assert engine.can_access_tool("test", "api", "get_user") is True
        assert engine.can_access_tool("test", "api", "get_data") is True
        assert engine.can_access_tool("test", "api", "get_all_records") is True
        assert engine.can_access_tool("test", "api", "set_user") is False
        assert engine.can_access_tool("test", "api", "user") is False

    def test_suffix_wildcard(self):
        """Test that '*_query' pattern matches tools ending with '_query'."""
        rules = {
            "agents": {
                "test": {
                    "allow": {
                        "servers": ["db"],
                        "tools": {"db": ["*_query"]}
                    }
                }
            }
        }

        engine = PolicyEngine(rules)

        assert engine.can_access_tool("test", "db", "read_query") is True
        assert engine.can_access_tool("test", "db", "write_query") is True
        assert engine.can_access_tool("test", "db", "complex_search_query") is True
        assert engine.can_access_tool("test", "db", "query") is False
        assert engine.can_access_tool("test", "db", "query_builder") is False

    def test_multiple_patterns(self):
        """Test that multiple patterns can be specified."""
        rules = {
            "agents": {
                "test": {
                    "allow": {
                        "servers": ["api"],
                        "tools": {"api": ["get_*", "list_*", "search_*"]}
                    }
                }
            }
        }

        engine = PolicyEngine(rules)

        assert engine.can_access_tool("test", "api", "get_user") is True
        assert engine.can_access_tool("test", "api", "list_items") is True
        assert engine.can_access_tool("test", "api", "search_data") is True
        assert engine.can_access_tool("test", "api", "delete_user") is False


class TestServerAccess:
    """Test cases for server-level access control."""

    def test_agent_not_in_rules_deny_default(self):
        """Test unknown agent with deny_on_missing_agent=true."""
        rules = {
            "agents": {
                "known_agent": {
                    "allow": {"servers": ["api"]}
                }
            },
            "defaults": {"deny_on_missing_agent": True}
        }

        engine = PolicyEngine(rules)

        assert engine.can_access_server("unknown_agent", "api") is False
        assert engine.can_access_server("unknown_agent", "any_server") is False

    def test_agent_not_in_rules_allow_default(self):
        """Test unknown agent with deny_on_missing_agent=false."""
        rules = {
            "agents": {
                "known_agent": {
                    "allow": {"servers": ["api"]}
                }
            },
            "defaults": {"deny_on_missing_agent": False}
        }

        engine = PolicyEngine(rules)

        # Unknown agents allowed when default is permissive
        assert engine.can_access_server("unknown_agent", "api") is True

    def test_server_in_allow_list(self):
        """Test that server in allow list is accessible."""
        rules = {
            "agents": {
                "test": {
                    "allow": {"servers": ["postgres", "redis"]}
                }
            }
        }

        engine = PolicyEngine(rules)

        assert engine.can_access_server("test", "postgres") is True
        assert engine.can_access_server("test", "redis") is True
        assert engine.can_access_server("test", "mongodb") is False

    def test_server_in_deny_list(self):
        """Test that server in deny list is blocked."""
        rules = {
            "agents": {
                "test": {
                    "allow": {"servers": ["*"]},
                    "deny": {"servers": ["production_db"]}
                }
            }
        }

        engine = PolicyEngine(rules)

        assert engine.can_access_server("test", "dev_db") is True
        assert engine.can_access_server("test", "production_db") is False

    def test_wildcard_server_access(self):
        """Test that wildcard '*' allows all servers."""
        rules = {
            "agents": {
                "admin": {
                    "allow": {"servers": ["*"]}
                }
            }
        }

        engine = PolicyEngine(rules)

        assert engine.can_access_server("admin", "any_server") is True
        assert engine.can_access_server("admin", "another_server") is True

    def test_wildcard_server_deny(self):
        """Test that wildcard deny blocks all servers."""
        rules = {
            "agents": {
                "restricted": {
                    "deny": {"servers": ["*"]}
                }
            }
        }

        engine = PolicyEngine(rules)

        assert engine.can_access_server("restricted", "any_server") is False


class TestToolAccess:
    """Test cases for tool-level access control."""

    def test_server_access_required_for_tool_access(self):
        """Test that agent must have server access before tool access."""
        rules = {
            "agents": {
                "test": {
                    "allow": {
                        "servers": ["api"],
                        "tools": {
                            "postgres": ["*"]  # Has tool rules but no server access
                        }
                    }
                }
            }
        }

        engine = PolicyEngine(rules)

        # Cannot access postgres tools without postgres server access
        assert engine.can_access_tool("test", "postgres", "query") is False

    def test_explicit_tool_allow(self):
        """Test explicit tool name in allow list."""
        rules = {
            "agents": {
                "test": {
                    "allow": {
                        "servers": ["db"],
                        "tools": {"db": ["query", "read"]}
                    }
                }
            }
        }

        engine = PolicyEngine(rules)

        assert engine.can_access_tool("test", "db", "query") is True
        assert engine.can_access_tool("test", "db", "read") is True
        assert engine.can_access_tool("test", "db", "write") is False

    def test_explicit_tool_deny(self):
        """Test explicit tool name in deny list."""
        rules = {
            "agents": {
                "test": {
                    "allow": {
                        "servers": ["db"],
                        "tools": {"db": ["*"]}
                    },
                    "deny": {
                        "tools": {"db": ["drop_table"]}
                    }
                }
            }
        }

        engine = PolicyEngine(rules)

        assert engine.can_access_tool("test", "db", "query") is True
        assert engine.can_access_tool("test", "db", "drop_table") is False

    def test_pattern_tool_allow(self):
        """Test pattern matching in tool allow rules."""
        rules = {
            "agents": {
                "readonly": {
                    "allow": {
                        "servers": ["db"],
                        "tools": {"db": ["get_*", "list_*", "read_*"]}
                    }
                }
            }
        }

        engine = PolicyEngine(rules)

        assert engine.can_access_tool("readonly", "db", "get_user") is True
        assert engine.can_access_tool("readonly", "db", "list_tables") is True
        assert engine.can_access_tool("readonly", "db", "read_data") is True
        assert engine.can_access_tool("readonly", "db", "write_data") is False

    def test_pattern_tool_deny(self):
        """Test pattern matching in tool deny rules."""
        rules = {
            "agents": {
                "safe": {
                    "allow": {
                        "servers": ["db"],
                        "tools": {"db": ["*"]}
                    },
                    "deny": {
                        "tools": {"db": ["drop_*", "delete_*", "truncate_*"]}
                    }
                }
            }
        }

        engine = PolicyEngine(rules)

        assert engine.can_access_tool("safe", "db", "query") is True
        assert engine.can_access_tool("safe", "db", "drop_table") is False
        assert engine.can_access_tool("safe", "db", "delete_all") is False
        assert engine.can_access_tool("safe", "db", "truncate_table") is False


class TestHelperMethods:
    """Test cases for helper methods."""

    def test_get_allowed_servers_basic(self):
        """Test getting list of allowed servers."""
        rules = {
            "agents": {
                "test": {
                    "allow": {"servers": ["api", "db", "cache"]}
                }
            }
        }

        engine = PolicyEngine(rules)
        servers = engine.get_allowed_servers("test")

        assert set(servers) == {"api", "db", "cache"}

    def test_get_allowed_servers_wildcard(self):
        """Test that wildcard returns ['*']."""
        rules = {
            "agents": {
                "admin": {
                    "allow": {"servers": ["*"]}
                }
            }
        }

        engine = PolicyEngine(rules)
        servers = engine.get_allowed_servers("admin")

        assert servers == ["*"]

    def test_get_allowed_servers_with_deny(self):
        """Test that denied servers are filtered out."""
        rules = {
            "agents": {
                "test": {
                    "allow": {"servers": ["api", "db", "cache"]},
                    "deny": {"servers": ["cache"]}
                }
            }
        }

        engine = PolicyEngine(rules)
        servers = engine.get_allowed_servers("test")

        assert "api" in servers
        assert "db" in servers
        assert "cache" not in servers

    def test_get_allowed_servers_unknown_agent(self):
        """Test get_allowed_servers for unknown agent."""
        rules = {
            "agents": {"known": {"allow": {"servers": ["api"]}}},
            "defaults": {"deny_on_missing_agent": True}
        }

        engine = PolicyEngine(rules)
        servers = engine.get_allowed_servers("unknown")

        assert servers == []

    def test_get_allowed_tools_wildcard(self):
        """Test that wildcard tools returns '*'."""
        rules = {
            "agents": {
                "test": {
                    "allow": {
                        "servers": ["api"],
                        "tools": {"api": ["*"]}
                    }
                }
            }
        }

        engine = PolicyEngine(rules)
        tools = engine.get_allowed_tools("test", "api")

        assert tools == "*"

    def test_get_allowed_tools_list(self):
        """Test that specific tools return list."""
        rules = {
            "agents": {
                "test": {
                    "allow": {
                        "servers": ["api"],
                        "tools": {"api": ["get_*", "list_*"]}
                    }
                }
            }
        }

        engine = PolicyEngine(rules)
        tools = engine.get_allowed_tools("test", "api")

        assert isinstance(tools, list)
        assert "get_*" in tools
        assert "list_*" in tools

    def test_get_allowed_tools_no_server_access(self):
        """Test that no server access returns empty list."""
        rules = {
            "agents": {
                "test": {
                    "allow": {
                        "servers": ["api"],
                        "tools": {"db": ["*"]}
                    }
                }
            }
        }

        engine = PolicyEngine(rules)
        tools = engine.get_allowed_tools("test", "db")

        assert tools == []

    def test_get_policy_decision_reason_server_denied(self):
        """Test policy reason when server is denied."""
        rules = {
            "agents": {
                "test": {
                    "allow": {"servers": ["api"]},
                    "deny": {"servers": ["db"]}
                }
            }
        }

        engine = PolicyEngine(rules)
        reason = engine.get_policy_decision_reason("test", "db")

        assert "denied" in reason.lower()
        assert "db" in reason

    def test_get_policy_decision_reason_server_allowed(self):
        """Test policy reason when server is allowed."""
        rules = {
            "agents": {
                "test": {
                    "allow": {"servers": ["api"]}
                }
            }
        }

        engine = PolicyEngine(rules)
        reason = engine.get_policy_decision_reason("test", "api")

        assert "allowed" in reason.lower()
        assert "api" in reason

    def test_get_policy_decision_reason_tool_denied(self):
        """Test policy reason when tool is denied."""
        rules = {
            "agents": {
                "test": {
                    "allow": {
                        "servers": ["db"],
                        "tools": {"db": ["*"]}
                    },
                    "deny": {
                        "tools": {"db": ["drop_table"]}
                    }
                }
            }
        }

        engine = PolicyEngine(rules)
        reason = engine.get_policy_decision_reason("test", "db", "drop_table")

        assert "denied" in reason.lower()
        assert "drop_table" in reason

    def test_get_policy_decision_reason_tool_allowed(self):
        """Test policy reason when tool is allowed."""
        rules = {
            "agents": {
                "test": {
                    "allow": {
                        "servers": ["db"],
                        "tools": {"db": ["query"]}
                    }
                }
            }
        }

        engine = PolicyEngine(rules)
        reason = engine.get_policy_decision_reason("test", "db", "query")

        assert "allowed" in reason.lower()
        assert "query" in reason

    def test_get_policy_decision_reason_unknown_agent(self):
        """Test policy reason for unknown agent."""
        rules = {
            "agents": {},
            "defaults": {"deny_on_missing_agent": True}
        }

        engine = PolicyEngine(rules)
        reason = engine.get_policy_decision_reason("unknown", "api")

        assert "not found" in reason.lower()
        assert "unknown" in reason

    def test_get_policy_decision_reason_wildcard_server_allow(self):
        """Test policy reason when server allowed by wildcard."""
        rules = {
            "agents": {
                "test": {
                    "allow": {"servers": ["*"]}
                }
            }
        }

        engine = PolicyEngine(rules)
        reason = engine.get_policy_decision_reason("test", "any_server")

        assert "wildcard" in reason.lower()
        assert "*" in reason

    def test_get_policy_decision_reason_pattern_deny(self):
        """Test policy reason when tool denied by pattern."""
        rules = {
            "agents": {
                "test": {
                    "allow": {
                        "servers": ["db"],
                        "tools": {"db": ["*"]}
                    },
                    "deny": {
                        "tools": {"db": ["drop_*"]}
                    }
                }
            }
        }

        engine = PolicyEngine(rules)
        reason = engine.get_policy_decision_reason("test", "db", "drop_table")

        assert "denied by pattern" in reason.lower()
        assert "drop_*" in reason

    def test_get_policy_decision_reason_pattern_allow(self):
        """Test policy reason when tool allowed by pattern."""
        rules = {
            "agents": {
                "test": {
                    "allow": {
                        "servers": ["db"],
                        "tools": {"db": ["get_*"]}
                    }
                }
            }
        }

        engine = PolicyEngine(rules)
        reason = engine.get_policy_decision_reason("test", "db", "get_user")

        assert "allowed by pattern" in reason.lower()
        assert "get_*" in reason

    def test_get_policy_decision_reason_tool_not_allowed(self):
        """Test policy reason when tool is not in allowed list."""
        rules = {
            "agents": {
                "test": {
                    "allow": {
                        "servers": ["db"],
                        "tools": {"db": ["query"]}
                    }
                }
            }
        }

        engine = PolicyEngine(rules)
        reason = engine.get_policy_decision_reason("test", "db", "write")

        assert "not in allowed list" in reason.lower()
        assert "write" in reason


class TestPolicyReload:
    """Test cases for policy reload functionality."""

    def test_reload_valid_rules(self):
        """Test successful reload with valid rules."""
        initial_rules = {
            "agents": {
                "agent1": {
                    "allow": {"servers": ["api"]}
                }
            },
            "defaults": {"deny_on_missing_agent": True}
        }

        engine = PolicyEngine(initial_rules)

        # Verify initial state
        assert engine.can_access_server("agent1", "api") is True
        assert engine.can_access_server("agent2", "db") is False

        # Reload with new rules
        new_rules = {
            "agents": {
                "agent1": {
                    "allow": {"servers": ["api", "db"]}
                },
                "agent2": {
                    "allow": {"servers": ["db"]}
                }
            },
            "defaults": {"deny_on_missing_agent": True}
        }

        success, error = engine.reload(new_rules)

        # Verify reload succeeded
        assert success is True
        assert error is None

        # Verify new rules are active
        assert engine.can_access_server("agent1", "db") is True
        assert engine.can_access_server("agent2", "db") is True

    def test_reload_invalid_rules_no_change(self):
        """Test that invalid rules don't modify engine state."""
        initial_rules = {
            "agents": {
                "agent1": {
                    "allow": {"servers": ["api"]}
                }
            },
            "defaults": {"deny_on_missing_agent": True}
        }

        engine = PolicyEngine(initial_rules)

        # Attempt to reload with invalid rules (malformed structure)
        invalid_rules = {
            "agents": {
                "agent1": {
                    "allow": {"servers": "not_a_list"}  # Should be list
                }
            }
        }

        success, error = engine.reload(invalid_rules)

        # Verify reload failed
        assert success is False
        assert error is not None
        assert "Validation error" in error

        # Verify original rules still active
        assert engine.can_access_server("agent1", "api") is True

    def test_reload_with_agent_additions(self):
        """Test reload that adds new agents."""
        initial_rules = {
            "agents": {
                "agent1": {
                    "allow": {"servers": ["api"]}
                }
            }
        }

        engine = PolicyEngine(initial_rules)

        new_rules = {
            "agents": {
                "agent1": {
                    "allow": {"servers": ["api"]}
                },
                "agent2": {
                    "allow": {"servers": ["db"]}
                },
                "agent3": {
                    "allow": {"servers": ["cache"]}
                }
            }
        }

        success, error = engine.reload(new_rules)

        assert success is True
        assert engine.can_access_server("agent2", "db") is True
        assert engine.can_access_server("agent3", "cache") is True

    def test_reload_with_agent_removals(self):
        """Test reload that removes agents."""
        initial_rules = {
            "agents": {
                "agent1": {"allow": {"servers": ["api"]}},
                "agent2": {"allow": {"servers": ["db"]}},
                "agent3": {"allow": {"servers": ["cache"]}}
            },
            "defaults": {"deny_on_missing_agent": True}
        }

        engine = PolicyEngine(initial_rules)

        new_rules = {
            "agents": {
                "agent1": {"allow": {"servers": ["api"]}}
            },
            "defaults": {"deny_on_missing_agent": True}
        }

        success, error = engine.reload(new_rules)

        assert success is True
        # Removed agents should be denied (if default is deny)
        assert engine.can_access_server("agent2", "db") is False
        assert engine.can_access_server("agent3", "cache") is False

    def test_reload_with_agent_modifications(self):
        """Test reload that modifies existing agent permissions."""
        initial_rules = {
            "agents": {
                "agent1": {
                    "allow": {
                        "servers": ["api"],
                        "tools": {"api": ["get_*"]}
                    }
                }
            }
        }

        engine = PolicyEngine(initial_rules)

        # Verify initial permissions
        assert engine.can_access_tool("agent1", "api", "get_user") is True
        assert engine.can_access_tool("agent1", "api", "set_user") is False

        # Reload with modified permissions
        new_rules = {
            "agents": {
                "agent1": {
                    "allow": {
                        "servers": ["api"],
                        "tools": {"api": ["*"]}  # Now allow all tools
                    }
                }
            }
        }

        success, error = engine.reload(new_rules)

        assert success is True
        # Verify new permissions
        assert engine.can_access_tool("agent1", "api", "get_user") is True
        assert engine.can_access_tool("agent1", "api", "set_user") is True

    def test_reload_with_defaults_change(self):
        """Test reload that changes default policy."""
        initial_rules = {
            "agents": {
                "agent1": {"allow": {"servers": ["api"]}}
            },
            "defaults": {"deny_on_missing_agent": True}
        }

        engine = PolicyEngine(initial_rules)

        # Unknown agent should be denied
        assert engine.can_access_server("unknown", "api") is False

        # Reload with permissive default
        new_rules = {
            "agents": {
                "agent1": {"allow": {"servers": ["api"]}}
            },
            "defaults": {"deny_on_missing_agent": False}
        }

        success, error = engine.reload(new_rules)

        assert success is True
        # Unknown agent should now be allowed
        assert engine.can_access_server("unknown", "api") is True

    def test_reload_empty_rules(self):
        """Test reload with empty agents section."""
        initial_rules = {
            "agents": {
                "agent1": {"allow": {"servers": ["api"]}}
            },
            "defaults": {"deny_on_missing_agent": True}
        }

        engine = PolicyEngine(initial_rules)

        # Reload with empty agents
        new_rules = {
            "agents": {},
            "defaults": {"deny_on_missing_agent": True}
        }

        success, error = engine.reload(new_rules)

        assert success is True
        # All agents should now be denied
        assert engine.can_access_server("agent1", "api") is False

    def test_reload_no_changes(self):
        """Test reload with identical rules."""
        rules = {
            "agents": {
                "agent1": {"allow": {"servers": ["api"]}}
            },
            "defaults": {"deny_on_missing_agent": True}
        }

        engine = PolicyEngine(rules)

        # Reload with same rules
        success, error = engine.reload(rules)

        assert success is True
        assert error is None
        # Should still work the same
        assert engine.can_access_server("agent1", "api") is True

    def test_reload_invalid_wildcard_pattern(self):
        """Test reload with invalid wildcard patterns."""
        initial_rules = {
            "agents": {
                "agent1": {"allow": {"servers": ["api"]}}
            }
        }

        engine = PolicyEngine(initial_rules)

        # Attempt reload with invalid pattern (multiple wildcards)
        invalid_rules = {
            "agents": {
                "agent1": {
                    "allow": {
                        "servers": ["api"],
                        "tools": {"api": ["get_*_data"]}  # Multiple wildcards not allowed
                    }
                }
            }
        }

        success, error = engine.reload(invalid_rules)

        # Should fail validation
        assert success is False
        assert error is not None
        # Original rules should remain
        assert engine.can_access_server("agent1", "api") is True

    def test_reload_preserves_deny_before_allow(self):
        """Test that reload maintains deny-before-allow precedence."""
        initial_rules = {
            "agents": {
                "agent1": {
                    "allow": {
                        "servers": ["db"],
                        "tools": {"db": ["*"]}
                    }
                }
            }
        }

        engine = PolicyEngine(initial_rules)

        # Reload with deny rules added
        new_rules = {
            "agents": {
                "agent1": {
                    "allow": {
                        "servers": ["db"],
                        "tools": {"db": ["*"]}
                    },
                    "deny": {
                        "tools": {"db": ["drop_*"]}
                    }
                }
            }
        }

        success, error = engine.reload(new_rules)

        assert success is True
        # Verify deny-before-allow is respected
        assert engine.can_access_tool("agent1", "db", "query") is True
        assert engine.can_access_tool("agent1", "db", "drop_table") is False


class TestDefaultAgent:
    """Test cases for agent named 'default' - used in fallback chain."""

    def test_default_agent_is_regular_agent(self):
        """Test that 'default' is treated as a regular agent name."""
        rules = {
            "agents": {
                "default": {
                    "allow": {"servers": ["api"]}
                },
                "researcher": {
                    "allow": {"servers": ["brave-search"]}
                }
            }
        }

        engine = PolicyEngine(rules)

        # 'default' should work like any other agent
        assert engine.can_access_server("default", "api") is True
        assert engine.can_access_server("default", "brave-search") is False
        assert engine.can_access_server("researcher", "brave-search") is True
        assert engine.can_access_server("researcher", "api") is False

    def test_default_agent_with_tool_permissions(self):
        """Test that policy evaluation works with agent_id='default'."""
        rules = {
            "agents": {
                "default": {
                    "allow": {
                        "servers": ["db"],
                        "tools": {"db": ["query", "read_*"]}
                    },
                    "deny": {
                        "tools": {"db": ["drop_*"]}
                    }
                }
            }
        }

        engine = PolicyEngine(rules)

        # Test server access
        assert engine.can_access_server("default", "db") is True

        # Test explicit tool permissions
        assert engine.can_access_tool("default", "db", "query") is True

        # Test wildcard allow patterns
        assert engine.can_access_tool("default", "db", "read_data") is True
        assert engine.can_access_tool("default", "db", "read_users") is True

        # Test wildcard deny patterns
        assert engine.can_access_tool("default", "db", "drop_table") is False

        # Test tool not in allow list
        assert engine.can_access_tool("default", "db", "write") is False

    def test_default_agent_with_deny_before_allow(self):
        """Test that deny-before-allow precedence works for 'default' agent."""
        rules = {
            "agents": {
                "default": {
                    "allow": {
                        "servers": ["db"],
                        "tools": {"db": ["*"]}  # Allow all
                    },
                    "deny": {
                        "tools": {"db": ["dangerous_op"]}  # But deny this one
                    }
                }
            }
        }

        engine = PolicyEngine(rules)

        # Should allow most tools
        assert engine.can_access_tool("default", "db", "query") is True
        assert engine.can_access_tool("default", "db", "read") is True

        # Should deny dangerous_op (explicit deny overrides wildcard allow)
        assert engine.can_access_tool("default", "db", "dangerous_op") is False

    def test_get_allowed_servers_for_default_agent(self):
        """Test helper method returns correct servers for 'default' agent."""
        rules = {
            "agents": {
                "default": {
                    "allow": {"servers": ["api", "db", "cache"]}
                }
            }
        }

        engine = PolicyEngine(rules)
        servers = engine.get_allowed_servers("default")

        assert set(servers) == {"api", "db", "cache"}

    def test_get_allowed_tools_for_default_agent(self):
        """Test helper method returns correct tools for 'default' agent."""
        rules = {
            "agents": {
                "default": {
                    "allow": {
                        "servers": ["api"],
                        "tools": {"api": ["get_*", "list_*"]}
                    }
                }
            }
        }

        engine = PolicyEngine(rules)
        tools = engine.get_allowed_tools("default", "api")

        assert isinstance(tools, list)
        assert "get_*" in tools
        assert "list_*" in tools

    def test_get_policy_decision_reason_for_default_agent(self):
        """Test policy reason works correctly for 'default' agent."""
        rules = {
            "agents": {
                "default": {
                    "allow": {
                        "servers": ["api"],
                        "tools": {"api": ["query"]}
                    }
                }
            }
        }

        engine = PolicyEngine(rules)

        # Test server access reason
        reason = engine.get_policy_decision_reason("default", "api")
        assert "allowed" in reason.lower()
        assert "api" in reason

        # Test tool access reason
        reason = engine.get_policy_decision_reason("default", "api", "query")
        assert "allowed" in reason.lower()
        assert "query" in reason

    def test_default_agent_coexists_with_other_agents(self):
        """Test that 'default' agent can coexist with other agents without conflicts."""
        rules = {
            "agents": {
                "default": {
                    "allow": {"servers": ["api"]}
                },
                "researcher": {
                    "allow": {"servers": ["brave-search"]}
                },
                "backend": {
                    "allow": {"servers": ["postgres"]}
                }
            }
        }

        engine = PolicyEngine(rules)

        # Each agent should have independent permissions
        assert engine.can_access_server("default", "api") is True
        assert engine.can_access_server("default", "brave-search") is False
        assert engine.can_access_server("default", "postgres") is False

        assert engine.can_access_server("researcher", "api") is False
        assert engine.can_access_server("researcher", "brave-search") is True

        assert engine.can_access_server("backend", "postgres") is True
        assert engine.can_access_server("backend", "api") is False

    def test_reload_with_default_agent(self):
        """Test that policy reload works correctly with 'default' agent."""
        initial_rules = {
            "agents": {
                "default": {
                    "allow": {"servers": ["api"]}
                }
            }
        }

        engine = PolicyEngine(initial_rules)

        # Verify initial state
        assert engine.can_access_server("default", "api") is True
        assert engine.can_access_server("default", "db") is False

        # Reload with updated permissions for 'default'
        new_rules = {
            "agents": {
                "default": {
                    "allow": {"servers": ["api", "db"]}
                }
            }
        }

        success, error = engine.reload(new_rules)

        # Verify reload succeeded
        assert success is True
        assert error is None

        # Verify new rules are active
        assert engine.can_access_server("default", "api") is True
        assert engine.can_access_server("default", "db") is True


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_agents_section(self):
        """Test with no agents defined."""
        rules = {
            "agents": {},
            "defaults": {"deny_on_missing_agent": True}
        }

        engine = PolicyEngine(rules)

        assert engine.can_access_server("any_agent", "any_server") is False

    def test_no_defaults_section(self):
        """Test with no defaults section."""
        rules = {
            "agents": {
                "test": {
                    "allow": {"servers": ["api"]}
                }
            }
        }

        engine = PolicyEngine(rules)

        # Should default to deny for unknown agents
        assert engine.can_access_server("unknown", "api") is False

    def test_empty_allow_deny_sections(self):
        """Test with empty allow/deny sections."""
        rules = {
            "agents": {
                "test": {
                    "allow": {},
                    "deny": {}
                }
            }
        }

        engine = PolicyEngine(rules)

        assert engine.can_access_server("test", "any_server") is False

    def test_agent_with_only_deny_rules(self):
        """Test agent that only has deny rules."""
        rules = {
            "agents": {
                "test": {
                    "deny": {"servers": ["production"]}
                }
            }
        }

        engine = PolicyEngine(rules)

        # No allow rules means no access
        assert engine.can_access_server("test", "dev") is False
        assert engine.can_access_server("test", "production") is False

    def test_case_sensitive_matching(self):
        """Test that tool/server names are case-sensitive."""
        rules = {
            "agents": {
                "test": {
                    "allow": {
                        "servers": ["API"],
                        "tools": {"API": ["GetData"]}
                    }
                }
            }
        }

        engine = PolicyEngine(rules)

        assert engine.can_access_server("test", "API") is True
        assert engine.can_access_server("test", "api") is False
        assert engine.can_access_tool("test", "API", "GetData") is True
        assert engine.can_access_tool("test", "API", "getdata") is False
