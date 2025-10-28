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
        - Stores agent in context state for downstream tools
        - Removes agent_id from arguments before forwarding
        - Allows gateway tools to pass through (they do own auth)

        Args:
            context: Middleware context containing the tool call message
            call_next: Callable to invoke next middleware/handler in chain

        Returns:
            Result from downstream handler

        Raises:
            ToolError: If agent_id is missing and default policy denies access
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
            # If default policy is permissive, continue without agent_id
            # (though this is unusual - most deployments should deny)

        # Store agent in context state for downstream tools
        # This allows gateway tools to access the current agent
        if context.fastmcp_context:
            context.fastmcp_context.set_state("current_agent", agent_id)

        # Remove agent_id from arguments before forwarding
        # Gateway tools and downstream servers don't need this parameter
        clean_arguments = {k: v for k, v in arguments.items() if k != "agent_id"}
        tool_call.arguments = clean_arguments

        # Gateway tools (list_servers, get_server_tools, execute_tool) are
        # allowed through - they perform their own permission checks using
        # the agent_id stored in context state
        return await call_next(context)

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
