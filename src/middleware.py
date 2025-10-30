"""Access control middleware for Agent MCP Gateway.

This module implements the AgentAccessControl middleware that enforces
per-agent access rules for gateway tools. It extracts agent identity from
tool call arguments, validates permissions, and manages agent context state.
"""

from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.exceptions import ToolError
from .policy import PolicyEngine


class AgentAccessControl(Middleware):
    """Enforces per-agent access rules for gateway operations.

    This middleware intercepts tool calls to:
    1. Extract agent_id from arguments
    2. Validate agent identity (handle missing agent_id based on default policy)
    3. Store agent in context state for downstream use
    4. Remove agent_id from arguments before forwarding to tools
    5. Allow gateway tools to perform their own authorization

    Gateway tools (list_servers, get_server_tools, execute_tool) handle their
    own permission checks, so the middleware just extracts and cleans agent_id
    without blocking them.
    """

    def __init__(self, policy_engine: PolicyEngine):
        """Initialize middleware with policy engine.

        Args:
            policy_engine: PolicyEngine instance for evaluating access rules
        """
        self.policy_engine = policy_engine

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        """Intercept tool calls to extract and validate agent identity.

        This hook:
        - Extracts agent_id from tool arguments
        - Validates agent identity based on default policy
        - Applies fallback chain if agent_id is missing (when deny_on_missing_agent: false)
        - Stores agent in context state for downstream tools
        - Keeps agent_id in arguments (gateway tools need it)
        - Allows gateway tools to pass through (they do own auth)

        Args:
            context: Middleware context containing the tool call message
            call_next: Callable to invoke next middleware/handler in chain

        Returns:
            Result from downstream handler

        Raises:
            ToolError: If agent_id is missing and default policy denies access,
                      or if fallback chain fails to find a valid agent
        """
        # Extract the tool call message
        tool_call = context.message
        arguments = tool_call.arguments or {}

        # Extract agent_id from arguments
        agent_id = arguments.get("agent_id")

        # Handle missing agent_id based on default policy
        if not agent_id:
            # Check if default policy allows missing agents
            deny_on_missing = self.policy_engine.defaults.get("deny_on_missing_agent", True)
            if deny_on_missing:
                raise ToolError(
                    "Missing required parameter 'agent_id'. "
                    "All tool calls must include agent identity."
                )

            # Apply fallback chain (deny_on_missing_agent: false)
            # Priority: 1. GATEWAY_DEFAULT_AGENT env var, 2. "default" agent in rules
            agent_id = self._resolve_fallback_agent(context)

            # Inject the resolved agent_id back into arguments for gateway tools
            if agent_id:
                arguments["agent_id"] = agent_id
                tool_call.arguments = arguments

        # Store agent in context state for downstream tools
        # This allows gateway tools to access the current agent
        if context.fastmcp_context:
            context.fastmcp_context.set_state("current_agent", agent_id)

        # NOTE: We do NOT remove agent_id from arguments because the gateway
        # tools (list_servers, get_server_tools, execute_tool) need it as
        # a parameter to perform their authorization checks.
        # If we ever add direct proxying to downstream servers in the future,
        # we would need to remove it at that point.

        # Gateway tools (list_servers, get_server_tools, execute_tool) are
        # allowed through - they perform their own permission checks using
        # the agent_id parameter
        return await call_next(context)

    def _resolve_fallback_agent(self, context: MiddlewareContext) -> str:
        """Resolve fallback agent when agent_id is missing and deny_on_missing_agent: false.

        Fallback priority order:
        1. GATEWAY_DEFAULT_AGENT environment variable (read from gateway module)
        2. Agent named "default" in gateway rules configuration
        3. Raise helpful error if neither is configured

        Args:
            context: Middleware context to access gateway state

        Returns:
            Resolved agent_id from fallback chain

        Raises:
            ToolError: If no fallback agent is configured or if fallback agent doesn't exist in rules
        """
        # Import here to avoid circular dependency
        from .gateway import get_default_agent_id

        # Try to get default agent from environment variable (stored in gateway module)
        default_agent_from_env = get_default_agent_id()

        # Priority 1: GATEWAY_DEFAULT_AGENT environment variable
        if default_agent_from_env:
            # Validate that this agent exists in policy rules
            if default_agent_from_env in self.policy_engine.agents:
                return default_agent_from_env
            else:
                raise ToolError(
                    f"Missing 'agent_id' parameter and fallback agent '{default_agent_from_env}' "
                    f"is not configured in gateway rules.\n"
                    f"Either provide 'agent_id' in your tool calls, or ask the user to configure "
                    f"the gateway fallback settings. See gateway documentation for configuration options."
                )

        # Priority 2: Agent named "default" in gateway rules
        if "default" in self.policy_engine.agents:
            return "default"

        # Priority 3: No fallback configured - provide helpful error
        raise ToolError(
            "Missing 'agent_id' parameter and no fallback agent configured.\n"
            "Either provide 'agent_id' in your tool calls, or ask the user to configure "
            "the gateway fallback settings. See gateway documentation for configuration options."
        )

    async def on_list_tools(self, context: MiddlewareContext, call_next):
        """Pass through list_tools requests without filtering.

        Gateway tools (list_servers, get_server_tools, execute_tool) should
        always be visible to all agents since they perform their own
        authorization based on agent_id passed in arguments.

        This differs from a traditional MCP proxy that might filter downstream
        tools at the middleware level. Our gateway exposes only 3 gateway tools
        that act as an API for discovering and executing downstream tools.

        Args:
            context: Middleware context containing the list request
            call_next: Callable to invoke next middleware/handler in chain

        Returns:
            Full list of gateway tools from downstream handler
        """
        # No filtering needed - gateway tools handle their own authorization
        return await call_next(context)
