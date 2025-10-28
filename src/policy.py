"""Policy evaluation engine for Agent MCP Gateway.

This module implements the core policy engine that evaluates agent permissions
against configured rules. It enforces a strict deny-before-allow precedence
and supports wildcard pattern matching for flexible rule definitions.

Precedence Order (CRITICAL - DO NOT CHANGE):
1. Explicit deny rules (specific tool names)
2. Explicit allow rules (specific tool names)
3. Wildcard deny rules (patterns like drop_*)
4. Wildcard allow rules (patterns like get_* or *)
5. Default policy (from defaults.deny_on_missing_agent)
"""

import fnmatch
from typing import Literal


class PolicyEngine:
    """Evaluates agent permissions against configured rules.

    This class implements the security policy evaluation logic for the gateway.
    It determines whether agents can access specific servers and tools based on
    configurable allow/deny rules with wildcard pattern support.
    """

    def __init__(self, rules: dict):
        """Initialize policy engine with rules dictionary.

        Args:
            rules: Gateway rules configuration with structure:
                {
                    "agents": {
                        "agent_id": {
                            "allow": {"servers": [...], "tools": {...}},
                            "deny": {"servers": [...], "tools": {...}}
                        }
                    },
                    "defaults": {"deny_on_missing_agent": bool}
                }
        """
        self.rules = rules
        self.agents = rules.get("agents", {})
        self.defaults = rules.get("defaults", {})

    def can_access_server(self, agent_id: str, server: str) -> bool:
        """Check if agent can access a server.

        An agent can access a server if:
        - The agent exists in the rules
        - The server is in the agent's allow.servers list (or "*" is present)
        - The server is not in the agent's deny.servers list

        Args:
            agent_id: Agent identifier
            server: Server name

        Returns:
            True if agent can access server, False otherwise
        """
        # Check if agent exists in rules
        if agent_id not in self.agents:
            # Unknown agent - check default policy
            return not self.defaults.get("deny_on_missing_agent", True)

        agent_rules = self.agents[agent_id]

        # Check deny rules first (deny takes precedence)
        deny_servers = agent_rules.get("deny", {}).get("servers", [])
        if server in deny_servers or "*" in deny_servers:
            return False

        # Check for wildcard deny patterns
        for pattern in deny_servers:
            if self._matches_pattern(server, pattern):
                return False

        # Check allow rules
        allow_servers = agent_rules.get("allow", {}).get("servers", [])

        # Explicit allow or wildcard allow
        if server in allow_servers or "*" in allow_servers:
            return True

        # Check for wildcard allow patterns
        for pattern in allow_servers:
            if self._matches_pattern(server, pattern):
                return True

        # Not explicitly allowed
        return False

    def can_access_tool(self, agent_id: str, server: str, tool: str) -> bool:
        """Check if agent can access a specific tool.

        Applies deny-before-allow precedence:
        1. Explicit deny rules (specific tool names)
        2. Explicit allow rules (specific tool names)
        3. Wildcard deny rules (patterns like drop_*)
        4. Wildcard allow rules (patterns like get_* or *)
        5. Default policy

        Args:
            agent_id: Agent identifier
            server: Server name
            tool: Tool name

        Returns:
            True if agent can access tool, False otherwise
        """
        # First, agent must have access to the server
        if not self.can_access_server(agent_id, server):
            return False

        # Check if agent exists in rules
        if agent_id not in self.agents:
            # Unknown agent but has server access - check default policy
            return not self.defaults.get("deny_on_missing_agent", True)

        agent_rules = self.agents[agent_id]

        # Get tool rules for this server
        deny_tools = agent_rules.get("deny", {}).get("tools", {}).get(server, [])
        allow_tools = agent_rules.get("allow", {}).get("tools", {}).get(server, [])

        # Separate explicit rules from wildcard patterns
        explicit_deny = []
        wildcard_deny = []
        explicit_allow = []
        wildcard_allow = []

        for rule in deny_tools:
            if "*" in rule:
                wildcard_deny.append(rule)
            else:
                explicit_deny.append(rule)

        for rule in allow_tools:
            if "*" in rule:
                wildcard_allow.append(rule)
            else:
                explicit_allow.append(rule)

        # Apply precedence order (CRITICAL - DO NOT CHANGE)

        # 1. Explicit deny rules
        if tool in explicit_deny:
            return False

        # 2. Explicit allow rules
        if tool in explicit_allow:
            return True

        # 3. Wildcard deny rules
        for pattern in wildcard_deny:
            if self._matches_pattern(tool, pattern):
                return False

        # 4. Wildcard allow rules
        for pattern in wildcard_allow:
            if self._matches_pattern(tool, pattern):
                return True

        # 5. Default policy - if no rules match, deny
        return False

    def get_allowed_servers(self, agent_id: str) -> list[str]:
        """Get list of servers this agent can access.

        Note: This returns the configured server list, not all possible servers.
        If wildcard "*" is present, returns ["*"] to indicate all servers allowed.

        Args:
            agent_id: Agent identifier

        Returns:
            List of server names the agent can access, or ["*"] for wildcard
        """
        # Check if agent exists in rules
        if agent_id not in self.agents:
            # Unknown agent - check default policy
            if self.defaults.get("deny_on_missing_agent", True):
                return []
            else:
                # If not denying unknown agents, return empty list
                # (caller should interpret this as "depends on what servers exist")
                return []

        agent_rules = self.agents[agent_id]
        allow_servers = agent_rules.get("allow", {}).get("servers", [])
        deny_servers = agent_rules.get("deny", {}).get("servers", [])

        # If wildcard allow and no wildcard deny, return wildcard
        if "*" in allow_servers and "*" not in deny_servers:
            return ["*"]

        # Filter out denied servers
        allowed = []
        for server in allow_servers:
            if server == "*":
                continue

            # Check if this server is denied
            is_denied = False
            if server in deny_servers:
                is_denied = True
            else:
                # Check wildcard deny patterns
                for pattern in deny_servers:
                    if self._matches_pattern(server, pattern):
                        is_denied = True
                        break

            if not is_denied:
                allowed.append(server)

        return allowed

    def get_allowed_tools(self, agent_id: str, server: str) -> list[str] | Literal["*"]:
        """Get list of allowed tools for agent on server.

        Returns either a list of specific tool names or "*" to indicate
        all tools are allowed (subject to deny rules being checked at access time).

        Args:
            agent_id: Agent identifier
            server: Server name

        Returns:
            List of tool names or "*" for wildcard access
        """
        # Agent must have server access first
        if not self.can_access_server(agent_id, server):
            return []

        # Check if agent exists in rules
        if agent_id not in self.agents:
            # Unknown agent but has server access
            if not self.defaults.get("deny_on_missing_agent", True):
                return "*"
            return []

        agent_rules = self.agents[agent_id]
        allow_tools = agent_rules.get("allow", {}).get("tools", {}).get(server, [])

        # If wildcard allow, return "*"
        if "*" in allow_tools:
            return "*"

        # Return list of allowed tools (including patterns)
        return allow_tools

    def get_policy_decision_reason(self, agent_id: str, server: str, tool: str | None = None) -> str:
        """Get human-readable reason for policy decision.

        Provides clear explanation of why access was allowed or denied,
        useful for debugging and audit logs.

        Args:
            agent_id: Agent identifier
            server: Server name
            tool: Optional tool name

        Returns:
            String explaining why access was allowed/denied
        """
        # Check if agent exists
        if agent_id not in self.agents:
            if self.defaults.get("deny_on_missing_agent", True):
                return f"Agent '{agent_id}' not found in rules; default policy denies access"
            else:
                return f"Agent '{agent_id}' not found in rules; default policy allows access"

        agent_rules = self.agents[agent_id]

        # Check server access
        deny_servers = agent_rules.get("deny", {}).get("servers", [])
        allow_servers = agent_rules.get("allow", {}).get("servers", [])

        # Check explicit server deny
        if server in deny_servers:
            return f"Server '{server}' explicitly denied for agent '{agent_id}'"

        # Check wildcard server deny
        for pattern in deny_servers:
            if self._matches_pattern(server, pattern):
                return f"Server '{server}' denied by pattern '{pattern}' for agent '{agent_id}'"

        # Check server allow
        server_allowed = False
        server_allow_reason = ""

        if server in allow_servers:
            server_allowed = True
            server_allow_reason = f"Server '{server}' explicitly allowed"
        elif "*" in allow_servers:
            server_allowed = True
            server_allow_reason = "Server allowed by wildcard '*'"
        else:
            # Check wildcard patterns
            for pattern in allow_servers:
                if self._matches_pattern(server, pattern):
                    server_allowed = True
                    server_allow_reason = f"Server '{server}' allowed by pattern '{pattern}'"
                    break

        if not server_allowed:
            return f"Server '{server}' not in allowed list for agent '{agent_id}'"

        # If no tool specified, return server access reason
        if tool is None:
            return server_allow_reason

        # Check tool access
        deny_tools = agent_rules.get("deny", {}).get("tools", {}).get(server, [])
        allow_tools = agent_rules.get("allow", {}).get("tools", {}).get(server, [])

        # Check explicit tool deny
        if tool in deny_tools:
            return f"Tool '{tool}' explicitly denied for agent '{agent_id}' on server '{server}'"

        # Check explicit tool allow
        if tool in allow_tools:
            return f"Tool '{tool}' explicitly allowed for agent '{agent_id}' on server '{server}'"

        # Check wildcard deny patterns
        for pattern in deny_tools:
            if "*" in pattern and self._matches_pattern(tool, pattern):
                return f"Tool '{tool}' denied by pattern '{pattern}' for agent '{agent_id}' on server '{server}'"

        # Check wildcard allow patterns
        for pattern in allow_tools:
            if "*" in pattern and self._matches_pattern(tool, pattern):
                return f"Tool '{tool}' allowed by pattern '{pattern}' for agent '{agent_id}' on server '{server}'"

        # No matching rule
        return f"Tool '{tool}' not in allowed list for agent '{agent_id}' on server '{server}'"

    def _matches_pattern(self, name: str, pattern: str) -> bool:
        """Check if name matches wildcard pattern.

        Uses glob-style pattern matching:
        - * matches any sequence of characters
        - ? matches any single character
        - [seq] matches any character in seq
        - [!seq] matches any character not in seq

        Args:
            name: String to match
            pattern: Pattern with wildcards (*, get_*, etc.)

        Returns:
            True if name matches pattern
        """
        return fnmatch.fnmatch(name, pattern)
