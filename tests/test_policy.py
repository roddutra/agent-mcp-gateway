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

    def test_explicit_allow_overrides_wildcard_deny(self):
        """Test that explicit allow (level 2) overrides wildcard deny (level 3)."""
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

        # Should ALLOW delete_user (explicit allow wins over wildcard deny)
        assert engine.can_access_tool("test_agent", "db", "delete_user") is True

        # Should ALLOW delete_data (explicit allow wins over wildcard deny)
        assert engine.can_access_tool("test_agent", "db", "delete_data") is True

        # Should allow get_user (in allow list, doesn't match deny pattern)
        assert engine.can_access_tool("test_agent", "db", "get_user") is True

        # Should DENY delete_something_else (wildcard deny, not in explicit allow)
        assert engine.can_access_tool("test_agent", "db", "delete_something_else") is False

    def test_wildcard_deny_blocks_tools_not_in_explicit_allow(self):
        """Test that wildcard deny blocks tools not explicitly allowed."""
        # This tests that explicit allow > wildcard deny precedence
        rules = {
            "agents": {
                "test_agent": {
                    "allow": {
                        "servers": ["db"],
                        "tools": {"db": ["drop_old_data"]}  # Explicit allow for one tool
                    },
                    "deny": {
                        "tools": {"db": ["drop_*"]}  # Pattern deny
                    }
                }
            },
            "defaults": {"deny_on_missing_agent": True}
        }

        engine = PolicyEngine(rules)

        # Should ALLOW drop_old_data (explicit allow beats wildcard deny)
        # This is level 2 (explicit allow) vs level 3 (wildcard deny)
        assert engine.can_access_tool("test_agent", "db", "drop_old_data") is True

        # Should DENY drop_table (matches wildcard deny, not in explicit allow)
        assert engine.can_access_tool("test_agent", "db", "drop_table") is False

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

    def test_no_tool_rules_defaults_to_deny(self):
        """Test that no tool rules means deny access."""
        rules = {
            "agents": {
                "test": {
                    "allow": {
                        "servers": ["db"]
                        # No tools section
                    }
                }
            }
        }

        engine = PolicyEngine(rules)

        # Has server access but no tool permissions
        assert engine.can_access_server("test", "db") is True
        assert engine.can_access_tool("test", "db", "any_tool") is False


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
