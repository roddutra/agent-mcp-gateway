"""Proxy infrastructure for managing downstream MCP server connections."""

import asyncio
import logging
from typing import Any

from fastmcp.client import Client


logger = logging.getLogger(__name__)


class ProxyManager:
    """Manages connections to downstream MCP servers.

    This class initializes and maintains Client instances for each
    configured downstream MCP server. It supports both stdio (npx/uvx)
    and HTTP transports, implements lazy connection strategy, and provides
    graceful error handling for unreachable servers.
    """

    def __init__(self):
        """Initialize ProxyManager with empty client registry."""
        self._clients: dict[str, Client] = {}
        self._connection_status: dict[str, bool] = {}
        self._connection_errors: dict[str, str] = {}

    def initialize_connections(self, mcp_config: dict) -> dict[str, Client]:
        """Initialize Client instances from MCP configuration.

        Creates disconnected Client instances for lazy connection strategy.
        Connections are established on first use via async context manager.

        Args:
            mcp_config: MCP servers configuration dictionary with structure:
                {
                    "mcpServers": {
                        "server-name": {
                            "command": "npx",
                            "args": [...],
                            "env": {...}
                        }
                    }
                }

        Returns:
            Dictionary mapping server names to Client instances

        Raises:
            ValueError: If mcp_config is invalid or malformed
        """
        if not isinstance(mcp_config, dict):
            raise ValueError(
                f"MCP configuration must be a dict, got {type(mcp_config).__name__}"
            )

        mcp_servers = mcp_config.get("mcpServers", {})
        if not isinstance(mcp_servers, dict):
            raise ValueError(
                f'"mcpServers" must be a dict, got {type(mcp_servers).__name__}'
            )

        # Clear existing clients
        self._clients.clear()
        self._connection_status.clear()
        self._connection_errors.clear()

        # Create ProxyClient for each server
        for server_name, server_config in mcp_servers.items():
            try:
                client = self._create_client(server_name, server_config)
                self._clients[server_name] = client
                self._connection_status[server_name] = False  # Not yet connected
                self._connection_errors[server_name] = ""

                logger.info(f"Initialized ProxyClient for server: {server_name}")
            except Exception as e:
                logger.error(f"Failed to initialize client for {server_name}: {e}")
                self._connection_errors[server_name] = str(e)

        return self._clients

    def _create_client(self, server_name: str, server_config: dict) -> Client:
        """Create Client instance from server configuration.

        Args:
            server_name: Name of the server
            server_config: Server configuration dictionary

        Returns:
            Client instance (disconnected)

        Raises:
            ValueError: If server configuration is invalid
        """
        # Determine transport type
        has_command = "command" in server_config
        has_url = "url" in server_config

        if not has_command and not has_url:
            raise ValueError(
                f'Server "{server_name}" must specify either "command" (stdio) '
                f'or "url" (HTTP) transport'
            )

        if has_command and has_url:
            raise ValueError(
                f'Server "{server_name}" cannot have both "command" and "url"'
            )

        # Create stdio client
        if has_command:
            command = server_config["command"]
            args = server_config.get("args", [])
            env = server_config.get("env", {})

            if not isinstance(command, str):
                raise ValueError(
                    f'Server "{server_name}": "command" must be a string'
                )
            if not isinstance(args, list):
                raise ValueError(
                    f'Server "{server_name}": "args" must be a list'
                )
            if not isinstance(env, dict):
                raise ValueError(
                    f'Server "{server_name}": "env" must be a dict'
                )

            logger.debug(
                f"Creating stdio Client for {server_name}: "
                f"command={command}, args={args}"
            )

            # FastMCP Client expects MCPConfig with mcpServers key
            # We need to wrap the single server config
            client_config = {
                "mcpServers": {
                    server_name: server_config
                }
            }
            return Client(transport=client_config)

        # Create HTTP client
        if has_url:
            url = server_config["url"]
            headers = server_config.get("headers", {})

            if not isinstance(url, str):
                raise ValueError(
                    f'Server "{server_name}": "url" must be a string'
                )
            if not isinstance(headers, dict):
                raise ValueError(
                    f'Server "{server_name}": "headers" must be a dict'
                )

            logger.debug(f"Creating HTTP Client for {server_name}: url={url}")

            # FastMCP Client expects MCPConfig with mcpServers key
            # We need to wrap the single server config
            client_config = {
                "mcpServers": {
                    server_name: server_config
                }
            }
            return Client(transport=client_config)

        # Should never reach here due to earlier validation
        raise ValueError(f'Server "{server_name}" has invalid configuration')

    def get_client(self, server_name: str) -> Client:
        """Get Client instance for a server.

        Returns the disconnected Client for the specified server.
        The caller should use 'async with client:' to establish a connection
        and perform operations.

        Args:
            server_name: Name of the server

        Returns:
            Client instance for the server

        Raises:
            KeyError: If server_name is not found in initialized clients
            RuntimeError: If server had initialization errors
        """
        if server_name not in self._clients:
            # Check if it had initialization error
            if server_name in self._connection_errors and self._connection_errors[server_name]:
                raise RuntimeError(
                    f'Server "{server_name}" is unavailable: '
                    f'{self._connection_errors[server_name]}'
                )
            raise KeyError(
                f'Server "{server_name}" not found in configured servers'
            )

        return self._clients[server_name]

    async def test_connection(
        self,
        server_name: str,
        timeout_ms: int = 5000,
        max_retries: int = 3
    ) -> bool:
        """Test connection to a server with retry logic.

        Attempts to connect to the server and retrieve its tool list.
        Uses exponential backoff for retries.

        Args:
            server_name: Name of the server to test
            timeout_ms: Connection timeout in milliseconds (default: 5000)
            max_retries: Maximum number of retry attempts (default: 3)

        Returns:
            True if connection successful, False otherwise

        Raises:
            KeyError: If server_name is not found in initialized clients
        """
        client = self.get_client(server_name)

        timeout_sec = timeout_ms / 1000.0
        base_delay = 0.5  # Start with 500ms delay

        for attempt in range(max_retries):
            try:
                logger.debug(
                    f"Testing connection to {server_name} "
                    f"(attempt {attempt + 1}/{max_retries})"
                )

                async with asyncio.timeout(timeout_sec):
                    async with client:
                        # Try to list tools as connection test
                        await client.list_tools()

                        self._connection_status[server_name] = True
                        self._connection_errors[server_name] = ""
                        logger.info(f"Successfully connected to server: {server_name}")
                        return True

            except asyncio.TimeoutError:
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    f"Connection timeout for {server_name} on attempt {attempt + 1}. "
                    f"Retrying in {delay}s..."
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(delay)

            except Exception as e:
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    f"Connection error for {server_name} on attempt {attempt + 1}: {e}. "
                    f"Retrying in {delay}s..."
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(delay)

        # All retries failed
        error_msg = f"Failed to connect after {max_retries} attempts"
        self._connection_status[server_name] = False
        self._connection_errors[server_name] = error_msg
        logger.error(f"Failed to connect to server {server_name}: {error_msg}")
        return False

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any],
        timeout_ms: int | None = None
    ) -> Any:
        """Call a tool on a downstream server.

        Establishes a fresh session for each call (automatic session isolation).

        Args:
            server_name: Name of the server
            tool_name: Name of the tool to call
            arguments: Tool arguments
            timeout_ms: Optional timeout in milliseconds

        Returns:
            Tool execution result

        Raises:
            KeyError: If server_name is not found
            RuntimeError: If server is unavailable or tool call fails
            asyncio.TimeoutError: If operation times out
        """
        client = self.get_client(server_name)

        try:
            if timeout_ms:
                timeout_sec = timeout_ms / 1000.0
                async with asyncio.timeout(timeout_sec):
                    async with client:
                        result = await client.call_tool(tool_name, arguments)
                        return result
            else:
                async with client:
                    result = await client.call_tool(tool_name, arguments)
                    return result

        except asyncio.TimeoutError:
            logger.error(
                f"Timeout calling tool {tool_name} on server {server_name} "
                f"(timeout: {timeout_ms}ms)"
            )
            raise

        except Exception as e:
            logger.error(
                f"Error calling tool {tool_name} on server {server_name}: {e}"
            )
            raise RuntimeError(
                f"Failed to call tool {tool_name} on server {server_name}: {e}"
            )

    async def list_tools(self, server_name: str) -> list[Any]:
        """List all tools available from a server.

        Args:
            server_name: Name of the server

        Returns:
            List of tool definitions

        Raises:
            KeyError: If server_name is not found
            RuntimeError: If server is unavailable
        """
        client = self.get_client(server_name)

        try:
            async with client:
                tools = await client.list_tools()
                return tools
        except Exception as e:
            logger.error(f"Error listing tools from server {server_name}: {e}")
            raise RuntimeError(
                f"Failed to list tools from server {server_name}: {e}"
            )

    def get_server_status(self, server_name: str) -> dict[str, Any]:
        """Get connection status for a server.

        Args:
            server_name: Name of the server

        Returns:
            Dictionary with status information:
                {
                    "connected": bool,
                    "error": str,
                    "initialized": bool
                }
        """
        return {
            "connected": self._connection_status.get(server_name, False),
            "error": self._connection_errors.get(server_name, ""),
            "initialized": server_name in self._clients
        }

    def get_all_servers(self) -> list[str]:
        """Get list of all initialized server names.

        Returns:
            List of server names
        """
        return list(self._clients.keys())

    async def close_all_connections(self):
        """Close all Client connections.

        This is a cleanup method for graceful shutdown.
        Note: Since we use disconnected clients with context managers,
        there are no persistent connections to close. This method is
        provided for API completeness and future extensibility.
        """
        logger.info("Closing all proxy connections")

        # With disconnected clients, each 'async with' creates and closes
        # its own session, so no explicit cleanup needed

        # Clear internal state
        self._connection_status.clear()
        self._connection_errors.clear()

        logger.info(f"Closed connections for {len(self._clients)} servers")
