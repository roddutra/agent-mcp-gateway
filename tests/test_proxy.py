"""Unit tests for proxy infrastructure."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, Mock

from src.proxy import ProxyManager


@pytest.fixture
def mock_client():
    """Create a mock Client that can be used in tests."""
    client = Mock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.list_tools = AsyncMock(return_value=[])
    client.call_tool = AsyncMock(return_value={"result": "success"})
    return client


class TestProxyManagerInitialization:
    """Test cases for ProxyManager initialization."""

    def test_initialization(self):
        """Test ProxyManager initializes with empty state."""
        manager = ProxyManager()

        assert manager._clients == {}
        assert manager._connection_status == {}
        assert manager._connection_errors == {}

    def test_initialize_connections_with_stdio_server(self):
        """Test initializing connections with stdio transport."""
        manager = ProxyManager()
        config = {
            "mcpServers": {
                "test-server": {
                    "command": "npx",
                    "args": ["-y", "test-server"],
                    "env": {"API_KEY": "test-key"}
                }
            }
        }

        clients = manager.initialize_connections(config)

        assert "test-server" in clients
        assert "test-server" in manager._clients
        assert manager._connection_status["test-server"] is False
        assert manager._connection_errors["test-server"] == ""

    def test_initialize_connections_with_http_server(self):
        """Test initializing connections with HTTP transport."""
        manager = ProxyManager()
        config = {
            "mcpServers": {
                "http-server": {
                    "url": "https://example.com/mcp",
                    "headers": {"Authorization": "Bearer token"}
                }
            }
        }

        clients = manager.initialize_connections(config)

        assert "http-server" in clients
        assert "http-server" in manager._clients

    def test_initialize_connections_with_mixed_transports(self):
        """Test initializing connections with both stdio and HTTP servers."""
        manager = ProxyManager()
        config = {
            "mcpServers": {
                "stdio-server": {
                    "command": "uvx",
                    "args": ["mcp-server-test"]
                },
                "http-server": {
                    "url": "http://localhost:8080/mcp"
                }
            }
        }

        clients = manager.initialize_connections(config)

        assert len(clients) == 2
        assert "stdio-server" in clients
        assert "http-server" in clients

    def test_initialize_connections_invalid_config_type(self):
        """Test error when config is not a dictionary."""
        manager = ProxyManager()

        with pytest.raises(ValueError) as exc_info:
            manager.initialize_connections("not-a-dict")
        assert "must be a dict" in str(exc_info.value)

    def test_initialize_connections_invalid_mcpservers_type(self):
        """Test error when mcpServers is not a dictionary."""
        manager = ProxyManager()
        config = {"mcpServers": "not-a-dict"}

        with pytest.raises(ValueError) as exc_info:
            manager.initialize_connections(config)
        assert "mcpServers" in str(exc_info.value)
        assert "must be a dict" in str(exc_info.value)

    def test_initialize_connections_clears_previous_state(self):
        """Test that re-initialization clears previous state."""
        manager = ProxyManager()

        # First initialization
        config1 = {
            "mcpServers": {
                "server1": {
                    "command": "npx",
                    "args": ["test1"]
                }
            }
        }
        manager.initialize_connections(config1)
        assert "server1" in manager._clients

        # Second initialization with different config
        config2 = {
            "mcpServers": {
                "server2": {
                    "command": "npx",
                    "args": ["test2"]
                }
            }
        }
        manager.initialize_connections(config2)

        # Only server2 should be present
        assert "server1" not in manager._clients
        assert "server2" in manager._clients
        assert len(manager._clients) == 1


class TestCreateClient:
    """Test cases for ProxyClient creation."""

    def test_create_stdio_client_minimal(self):
        """Test creating stdio client with minimal configuration."""
        manager = ProxyManager()
        config = {"command": "npx", "args": ["-y", "test"]}

        client = manager._create_client("test", config)

        assert client is not None

    def test_create_stdio_client_with_env(self):
        """Test creating stdio client with environment variables."""
        manager = ProxyManager()
        config = {
            "command": "uvx",
            "args": ["test-server"],
            "env": {
                "API_KEY": "secret123",
                "DEBUG": "true"
            }
        }

        client = manager._create_client("test", config)

        assert client is not None

    def test_create_http_client(self):
        """Test creating HTTP client."""
        manager = ProxyManager()
        config = {
            "url": "https://example.com/mcp"
        }

        client = manager._create_client("test", config)

        assert client is not None

    def test_create_http_client_with_headers(self):
        """Test creating HTTP client with custom headers."""
        manager = ProxyManager()
        config = {
            "url": "https://example.com/mcp",
            "headers": {
                "Authorization": "Bearer token",
                "X-Custom-Header": "value"
            }
        }

        client = manager._create_client("test", config)

        assert client is not None

    def test_create_client_missing_transport(self):
        """Test error when neither command nor url is provided."""
        manager = ProxyManager()
        config = {"args": ["-y", "test"]}

        with pytest.raises(ValueError) as exc_info:
            manager._create_client("test", config)
        assert "must specify either" in str(exc_info.value)

    def test_create_client_both_transports(self):
        """Test error when both command and url are provided."""
        manager = ProxyManager()
        config = {
            "command": "npx",
            "url": "https://example.com"
        }

        with pytest.raises(ValueError) as exc_info:
            manager._create_client("test", config)
        assert "cannot have both" in str(exc_info.value)

    def test_create_client_invalid_command_type(self):
        """Test error when command is not a string."""
        manager = ProxyManager()
        config = {"command": 123, "args": []}

        with pytest.raises(ValueError) as exc_info:
            manager._create_client("test", config)
        assert "command" in str(exc_info.value)
        assert "must be a string" in str(exc_info.value)

    def test_create_client_invalid_args_type(self):
        """Test error when args is not a list."""
        manager = ProxyManager()
        config = {"command": "npx", "args": "not-a-list"}

        with pytest.raises(ValueError) as exc_info:
            manager._create_client("test", config)
        assert "args" in str(exc_info.value)
        assert "must be a list" in str(exc_info.value)

    def test_create_client_invalid_env_type(self):
        """Test error when env is not a dict."""
        manager = ProxyManager()
        config = {"command": "npx", "args": [], "env": "not-a-dict"}

        with pytest.raises(ValueError) as exc_info:
            manager._create_client("test", config)
        assert "env" in str(exc_info.value)
        assert "must be a dict" in str(exc_info.value)

    def test_create_client_invalid_url_type(self):
        """Test error when url is not a string."""
        manager = ProxyManager()
        config = {"url": 123}

        with pytest.raises(ValueError) as exc_info:
            manager._create_client("test", config)
        assert "url" in str(exc_info.value)
        assert "must be a string" in str(exc_info.value)

    def test_create_client_invalid_headers_type(self):
        """Test error when headers is not a dict."""
        manager = ProxyManager()
        config = {"url": "https://example.com", "headers": "not-a-dict"}

        with pytest.raises(ValueError) as exc_info:
            manager._create_client("test", config)
        assert "headers" in str(exc_info.value)
        assert "must be a dict" in str(exc_info.value)


class TestGetClient:
    """Test cases for retrieving ProxyClient instances."""

    def test_get_client_success(self):
        """Test successfully retrieving an initialized client."""
        manager = ProxyManager()
        config = {
            "mcpServers": {
                "test-server": {
                    "command": "npx",
                    "args": ["test"]
                }
            }
        }
        manager.initialize_connections(config)

        client = manager.get_client("test-server")

        assert client is not None

    def test_get_client_not_found(self):
        """Test error when requesting non-existent server."""
        manager = ProxyManager()
        config = {"mcpServers": {}}
        manager.initialize_connections(config)

        with pytest.raises(KeyError) as exc_info:
            manager.get_client("nonexistent")
        assert "not found" in str(exc_info.value)

    def test_get_client_with_initialization_error(self):
        """Test error when server had initialization error."""
        manager = ProxyManager()
        manager._connection_errors["failed-server"] = "Initialization failed"

        with pytest.raises(RuntimeError) as exc_info:
            manager.get_client("failed-server")
        assert "unavailable" in str(exc_info.value)
        assert "Initialization failed" in str(exc_info.value)


class TestConnectionTesting:
    """Test cases for connection testing and retry logic."""

    @pytest.mark.asyncio
    async def test_test_connection_success(self, mock_client):
        """Test successful connection on first attempt."""
        manager = ProxyManager()
        config = {
            "mcpServers": {
                "test-server": {
                    "command": "npx",
                    "args": ["test"]
                }
            }
        }

        # Mock Client creation to return our mock client
        with patch('src.proxy.Client', return_value=mock_client):
            manager.initialize_connections(config)
            result = await manager.test_connection("test-server")

        assert result is True
        assert manager._connection_status["test-server"] is True
        assert manager._connection_errors["test-server"] == ""

    @pytest.mark.asyncio
    async def test_test_connection_timeout(self):
        """Test connection timeout with retries."""
        manager = ProxyManager()
        config = {
            "mcpServers": {
                "test-server": {
                    "command": "npx",
                    "args": ["test"]
                }
            }
        }
        manager.initialize_connections(config)

        # Mock the client to timeout
        client = manager.get_client("test-server")

        async def timeout_mock():
            await asyncio.sleep(10)  # Longer than timeout

        with patch.object(client, 'list_tools', side_effect=timeout_mock):
            with patch.object(client, '__aenter__', AsyncMock(return_value=client)):
                with patch.object(client, '__aexit__', AsyncMock(return_value=None)):
                    result = await manager.test_connection(
                        "test-server",
                        timeout_ms=100,
                        max_retries=2
                    )

        assert result is False
        assert manager._connection_status["test-server"] is False
        assert "Failed to connect" in manager._connection_errors["test-server"]

    @pytest.mark.asyncio
    async def test_test_connection_error_with_retries(self):
        """Test connection error triggers retries."""
        manager = ProxyManager()
        config = {
            "mcpServers": {
                "test-server": {
                    "command": "npx",
                    "args": ["test"]
                }
            }
        }

        # Fail first attempt, succeed on second
        call_count = 0

        async def failing_then_success():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("Connection refused")
            return []

        mock_client = Mock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.list_tools = failing_then_success

        with patch('src.proxy.Client', return_value=mock_client):
            manager.initialize_connections(config)
            result = await manager.test_connection(
                "test-server",
                max_retries=3
            )

        assert result is True
        assert call_count == 2  # Failed once, then succeeded

    @pytest.mark.asyncio
    async def test_test_connection_exponential_backoff(self):
        """Test exponential backoff between retries."""
        manager = ProxyManager()
        config = {
            "mcpServers": {
                "test-server": {
                    "command": "npx",
                    "args": ["test"]
                }
            }
        }
        manager.initialize_connections(config)

        client = manager.get_client("test-server")

        # Track sleep calls to verify exponential backoff
        sleep_calls = []

        async def track_sleep(duration):
            sleep_calls.append(duration)

        with patch.object(client, 'list_tools', side_effect=Exception("Error")):
            with patch.object(client, '__aenter__', AsyncMock(return_value=client)):
                with patch.object(client, '__aexit__', AsyncMock(return_value=None)):
                    with patch('asyncio.sleep', side_effect=track_sleep):
                        result = await manager.test_connection(
                            "test-server",
                            max_retries=3
                        )

        assert result is False
        # Should have 2 sleeps (retries - 1)
        assert len(sleep_calls) == 2
        # Verify exponential backoff: 0.5, 1.0
        assert sleep_calls[0] == 0.5
        assert sleep_calls[1] == 1.0


class TestCallTool:
    """Test cases for calling tools on downstream servers."""

    @pytest.mark.asyncio
    async def test_call_tool_success(self, mock_client):
        """Test successfully calling a tool."""
        manager = ProxyManager()
        config = {
            "mcpServers": {
                "test-server": {
                    "command": "npx",
                    "args": ["test"]
                }
            }
        }

        expected_result = {"status": "success", "data": "test"}
        mock_client.call_tool = AsyncMock(return_value=expected_result)

        with patch('src.proxy.Client', return_value=mock_client):
            manager.initialize_connections(config)
            result = await manager.call_tool(
                "test-server",
                "test_tool",
                {"arg1": "value1"}
            )

        assert result == expected_result
        mock_client.call_tool.assert_called_once_with("test_tool", {"arg1": "value1"})

    @pytest.mark.asyncio
    async def test_call_tool_with_timeout(self):
        """Test calling tool with timeout."""
        manager = ProxyManager()
        config = {
            "mcpServers": {
                "test-server": {
                    "command": "npx",
                    "args": ["test"]
                }
            }
        }
        manager.initialize_connections(config)

        client = manager.get_client("test-server")

        async def slow_tool(*args, **kwargs):
            await asyncio.sleep(10)
            return {"result": "data"}

        with patch.object(client, 'call_tool', side_effect=slow_tool):
            with patch.object(client, '__aenter__', AsyncMock(return_value=client)):
                with patch.object(client, '__aexit__', AsyncMock(return_value=None)):
                    with pytest.raises(asyncio.TimeoutError):
                        await manager.call_tool(
                            "test-server",
                            "slow_tool",
                            {},
                            timeout_ms=100
                        )

    @pytest.mark.asyncio
    async def test_call_tool_server_not_found(self):
        """Test error when calling tool on non-existent server."""
        manager = ProxyManager()
        config = {"mcpServers": {}}
        manager.initialize_connections(config)

        with pytest.raises(KeyError):
            await manager.call_tool("nonexistent", "tool", {})

    @pytest.mark.asyncio
    async def test_call_tool_execution_error(self):
        """Test error when tool execution fails."""
        manager = ProxyManager()
        config = {
            "mcpServers": {
                "test-server": {
                    "command": "npx",
                    "args": ["test"]
                }
            }
        }

        mock_client = Mock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.call_tool = AsyncMock(side_effect=Exception("Tool error"))

        with patch('src.proxy.Client', return_value=mock_client):
            manager.initialize_connections(config)
            with pytest.raises(RuntimeError) as exc_info:
                await manager.call_tool(
                    "test-server",
                    "failing_tool",
                    {}
                )

        assert "Failed to call tool" in str(exc_info.value)
        assert "Tool error" in str(exc_info.value)


class TestListTools:
    """Test cases for listing tools from servers."""

    @pytest.mark.asyncio
    async def test_list_tools_success(self, mock_client):
        """Test successfully listing tools from a server."""
        manager = ProxyManager()
        config = {
            "mcpServers": {
                "test-server": {
                    "command": "npx",
                    "args": ["test"]
                }
            }
        }

        expected_tools = [
            {"name": "tool1", "description": "Tool 1"},
            {"name": "tool2", "description": "Tool 2"}
        ]
        mock_client.list_tools = AsyncMock(return_value=expected_tools)

        with patch('src.proxy.Client', return_value=mock_client):
            manager.initialize_connections(config)
            result = await manager.list_tools("test-server")

        assert result == expected_tools

    @pytest.mark.asyncio
    async def test_list_tools_server_not_found(self):
        """Test error when listing tools from non-existent server."""
        manager = ProxyManager()
        config = {"mcpServers": {}}
        manager.initialize_connections(config)

        with pytest.raises(KeyError):
            await manager.list_tools("nonexistent")

    @pytest.mark.asyncio
    async def test_list_tools_connection_error(self):
        """Test error when connection fails during list_tools."""
        manager = ProxyManager()
        config = {
            "mcpServers": {
                "test-server": {
                    "command": "npx",
                    "args": ["test"]
                }
            }
        }
        manager.initialize_connections(config)

        client = manager.get_client("test-server")

        with patch.object(client, 'list_tools', side_effect=ConnectionError("Failed")):
            with patch.object(client, '__aenter__', AsyncMock(return_value=client)):
                with patch.object(client, '__aexit__', AsyncMock(return_value=None)):
                    with pytest.raises(RuntimeError) as exc_info:
                        await manager.list_tools("test-server")

        assert "Failed to list tools" in str(exc_info.value)


class TestServerStatus:
    """Test cases for server status tracking."""

    def test_get_server_status_initialized(self):
        """Test getting status of initialized server."""
        manager = ProxyManager()
        config = {
            "mcpServers": {
                "test-server": {
                    "command": "npx",
                    "args": ["test"]
                }
            }
        }
        manager.initialize_connections(config)

        status = manager.get_server_status("test-server")

        assert status["initialized"] is True
        assert status["connected"] is False
        assert status["error"] == ""

    def test_get_server_status_not_initialized(self):
        """Test getting status of non-initialized server."""
        manager = ProxyManager()

        status = manager.get_server_status("nonexistent")

        assert status["initialized"] is False
        assert status["connected"] is False
        assert status["error"] == ""

    def test_get_server_status_with_error(self):
        """Test getting status of server with initialization error."""
        manager = ProxyManager()
        manager._connection_errors["failed-server"] = "Init error"

        status = manager.get_server_status("failed-server")

        assert status["error"] == "Init error"

    def test_get_all_servers(self):
        """Test getting list of all initialized servers."""
        manager = ProxyManager()
        config = {
            "mcpServers": {
                "server1": {"command": "npx", "args": ["test1"]},
                "server2": {"url": "https://example.com"},
                "server3": {"command": "uvx", "args": ["test3"]}
            }
        }
        manager.initialize_connections(config)

        servers = manager.get_all_servers()

        assert len(servers) == 3
        assert "server1" in servers
        assert "server2" in servers
        assert "server3" in servers


class TestCloseConnections:
    """Test cases for closing connections."""

    @pytest.mark.asyncio
    async def test_close_all_connections(self):
        """Test closing all connections."""
        manager = ProxyManager()
        config = {
            "mcpServers": {
                "server1": {"command": "npx", "args": ["test1"]},
                "server2": {"url": "https://example.com"}
            }
        }
        manager.initialize_connections(config)

        # Set some connection status
        manager._connection_status["server1"] = True
        manager._connection_errors["server2"] = "Some error"

        await manager.close_all_connections()

        # Status should be cleared
        assert len(manager._connection_status) == 0
        assert len(manager._connection_errors) == 0

    @pytest.mark.asyncio
    async def test_close_all_connections_empty_manager(self):
        """Test closing connections when no clients exist."""
        manager = ProxyManager()

        # Should not raise error
        await manager.close_all_connections()

        assert len(manager._clients) == 0


class TestLazyConnectionStrategy:
    """Test cases for lazy connection strategy."""

    def test_clients_created_disconnected(self):
        """Test that clients are created in disconnected state."""
        manager = ProxyManager()
        config = {
            "mcpServers": {
                "test-server": {
                    "command": "npx",
                    "args": ["test"]
                }
            }
        }

        manager.initialize_connections(config)

        # Verify client exists but is not connected
        assert "test-server" in manager._clients
        assert manager._connection_status["test-server"] is False

    @pytest.mark.asyncio
    async def test_connection_established_on_first_use(self, mock_client):
        """Test that connection is established when using client."""
        manager = ProxyManager()
        config = {
            "mcpServers": {
                "test-server": {
                    "command": "npx",
                    "args": ["test"]
                }
            }
        }

        mock_client.call_tool = AsyncMock(return_value={"result": "ok"})

        with patch('src.proxy.Client', return_value=mock_client):
            manager.initialize_connections(config)
            result = await manager.call_tool("test-server", "test_tool", {})

        assert result == {"result": "ok"}

    @pytest.mark.asyncio
    async def test_each_use_creates_fresh_session(self):
        """Test that each tool call creates a fresh session."""
        manager = ProxyManager()
        config = {
            "mcpServers": {
                "test-server": {
                    "command": "npx",
                    "args": ["test"]
                }
            }
        }

        enter_call_count = 0
        exit_call_count = 0

        async def count_enter(*args):
            nonlocal enter_call_count
            enter_call_count += 1
            return mock_client

        async def count_exit(*args):
            nonlocal exit_call_count
            exit_call_count += 1

        mock_client = Mock()
        mock_client.__aenter__ = count_enter
        mock_client.__aexit__ = count_exit
        mock_client.call_tool = AsyncMock(return_value={})

        with patch('src.proxy.Client', return_value=mock_client):
            manager.initialize_connections(config)
            # Make multiple calls
            await manager.call_tool("test-server", "tool1", {})
            await manager.call_tool("test-server", "tool2", {})
            await manager.call_tool("test-server", "tool3", {})

        # Each call should enter and exit context (fresh session)
        assert enter_call_count == 3
        assert exit_call_count == 3


class TestReload:
    """Test cases for configuration reload functionality."""

    @pytest.mark.asyncio
    async def test_reload_add_servers(self):
        """Test reloading with new servers added."""
        manager = ProxyManager()

        # Initial config with one server
        initial_config = {
            "mcpServers": {
                "server1": {
                    "command": "npx",
                    "args": ["test1"]
                }
            }
        }
        manager.initialize_connections(initial_config)
        assert len(manager._clients) == 1

        # New config with additional server
        new_config = {
            "mcpServers": {
                "server1": {
                    "command": "npx",
                    "args": ["test1"]
                },
                "server2": {
                    "command": "uvx",
                    "args": ["test2"]
                }
            }
        }

        success, error = await manager.reload(new_config)

        assert success is True
        assert error is None
        assert len(manager._clients) == 2
        assert "server1" in manager._clients
        assert "server2" in manager._clients

    @pytest.mark.asyncio
    async def test_reload_remove_servers(self):
        """Test reloading with servers removed."""
        manager = ProxyManager()

        # Initial config with two servers
        initial_config = {
            "mcpServers": {
                "server1": {
                    "command": "npx",
                    "args": ["test1"]
                },
                "server2": {
                    "url": "https://example.com"
                }
            }
        }
        manager.initialize_connections(initial_config)
        assert len(manager._clients) == 2

        # New config with one server removed
        new_config = {
            "mcpServers": {
                "server1": {
                    "command": "npx",
                    "args": ["test1"]
                }
            }
        }

        success, error = await manager.reload(new_config)

        assert success is True
        assert error is None
        assert len(manager._clients) == 1
        assert "server1" in manager._clients
        assert "server2" not in manager._clients
        assert "server2" not in manager._connection_status
        assert "server2" not in manager._connection_errors

    @pytest.mark.asyncio
    async def test_reload_update_servers(self):
        """Test reloading with server config changed."""
        manager = ProxyManager()

        # Initial config
        initial_config = {
            "mcpServers": {
                "server1": {
                    "command": "npx",
                    "args": ["test1"],
                    "env": {"KEY": "old"}
                }
            }
        }
        manager.initialize_connections(initial_config)
        old_client = manager._clients["server1"]

        # New config with updated server
        new_config = {
            "mcpServers": {
                "server1": {
                    "command": "npx",
                    "args": ["test1"],
                    "env": {"KEY": "new"}
                }
            }
        }

        success, error = await manager.reload(new_config)

        assert success is True
        assert error is None
        assert len(manager._clients) == 1
        assert "server1" in manager._clients
        # New client should be created
        assert manager._clients["server1"] is not old_client

    @pytest.mark.asyncio
    async def test_reload_unchanged_servers(self):
        """Test reloading preserves unchanged servers."""
        manager = ProxyManager()

        # Initial config
        initial_config = {
            "mcpServers": {
                "server1": {
                    "command": "npx",
                    "args": ["test1"]
                },
                "server2": {
                    "url": "https://example.com"
                }
            }
        }
        manager.initialize_connections(initial_config)
        server1_client = manager._clients["server1"]
        server2_client = manager._clients["server2"]

        # Reload with same config
        success, error = await manager.reload(initial_config)

        assert success is True
        assert error is None
        assert len(manager._clients) == 2
        # Same client instances should be preserved
        assert manager._clients["server1"] is server1_client
        assert manager._clients["server2"] is server2_client

    @pytest.mark.asyncio
    async def test_reload_mixed_changes(self):
        """Test reloading with add, remove, update, and unchanged servers."""
        manager = ProxyManager()

        # Initial config
        initial_config = {
            "mcpServers": {
                "keep-same": {
                    "command": "npx",
                    "args": ["keep"]
                },
                "update-me": {
                    "command": "npx",
                    "args": ["old"]
                },
                "remove-me": {
                    "url": "https://remove.com"
                }
            }
        }
        manager.initialize_connections(initial_config)
        keep_same_client = manager._clients["keep-same"]
        assert len(manager._clients) == 3

        # New config with mixed changes
        new_config = {
            "mcpServers": {
                "keep-same": {
                    "command": "npx",
                    "args": ["keep"]
                },
                "update-me": {
                    "command": "uvx",  # Changed command
                    "args": ["new"]
                },
                "add-me": {
                    "url": "https://add.com"
                }
            }
        }

        success, error = await manager.reload(new_config)

        assert success is True
        assert error is None
        assert len(manager._clients) == 3
        assert "keep-same" in manager._clients
        assert "update-me" in manager._clients
        assert "add-me" in manager._clients
        assert "remove-me" not in manager._clients
        # Unchanged server should have same client
        assert manager._clients["keep-same"] is keep_same_client

    @pytest.mark.asyncio
    async def test_reload_invalid_config_type(self):
        """Test reload fails with invalid config type."""
        manager = ProxyManager()
        initial_config = {"mcpServers": {}}
        manager.initialize_connections(initial_config)

        success, error = await manager.reload("not-a-dict")

        assert success is False
        assert error is not None
        assert "must be a dict" in error

    @pytest.mark.asyncio
    async def test_reload_invalid_mcpservers_type(self):
        """Test reload fails with invalid mcpServers type."""
        manager = ProxyManager()
        initial_config = {"mcpServers": {}}
        manager.initialize_connections(initial_config)

        success, error = await manager.reload({"mcpServers": "not-a-dict"})

        assert success is False
        assert error is not None
        assert "mcpServers" in error
        assert "must be a dict" in error

    @pytest.mark.asyncio
    async def test_reload_invalid_server_config(self):
        """Test reload fails with invalid server configuration."""
        manager = ProxyManager()
        initial_config = {"mcpServers": {}}
        manager.initialize_connections(initial_config)

        # Server with both command and url (invalid)
        new_config = {
            "mcpServers": {
                "invalid": {
                    "command": "npx",
                    "url": "https://example.com"
                }
            }
        }

        success, error = await manager.reload(new_config)

        assert success is False
        assert error is not None
        assert "invalid" in error
        assert "cannot have both" in error

    @pytest.mark.asyncio
    async def test_reload_invalid_server_missing_transport(self):
        """Test reload fails when server missing transport."""
        manager = ProxyManager()
        initial_config = {"mcpServers": {}}
        manager.initialize_connections(initial_config)

        new_config = {
            "mcpServers": {
                "invalid": {
                    "args": ["test"]
                }
            }
        }

        success, error = await manager.reload(new_config)

        assert success is False
        assert error is not None
        assert "must specify either" in error

    @pytest.mark.asyncio
    async def test_reload_empty_config(self):
        """Test reloading with empty server list."""
        manager = ProxyManager()

        # Initial config with servers
        initial_config = {
            "mcpServers": {
                "server1": {"command": "npx", "args": ["test1"]},
                "server2": {"url": "https://example.com"}
            }
        }
        manager.initialize_connections(initial_config)
        assert len(manager._clients) == 2

        # Reload with empty config
        empty_config = {"mcpServers": {}}
        success, error = await manager.reload(empty_config)

        assert success is True
        assert error is None
        assert len(manager._clients) == 0

    @pytest.mark.asyncio
    async def test_reload_updates_current_config(self):
        """Test that reload updates the stored current config."""
        manager = ProxyManager()

        initial_config = {
            "mcpServers": {
                "server1": {"command": "npx", "args": ["test1"]}
            }
        }
        manager.initialize_connections(initial_config)
        assert manager._current_config == initial_config

        new_config = {
            "mcpServers": {
                "server2": {"url": "https://example.com"}
            }
        }
        success, error = await manager.reload(new_config)

        assert success is True
        assert manager._current_config == new_config

    @pytest.mark.asyncio
    async def test_reload_partial_failure_continues(self):
        """Test that reload continues even if some servers fail to create."""
        manager = ProxyManager()

        initial_config = {"mcpServers": {}}
        manager.initialize_connections(initial_config)

        # Config with one valid and one server that will fail creation
        new_config = {
            "mcpServers": {
                "valid-server": {
                    "command": "npx",
                    "args": ["test"]
                },
                "another-valid": {
                    "url": "https://example.com"
                }
            }
        }

        # Mock _create_client to fail for one server
        original_create = manager._create_client

        def mock_create(name, config):
            if name == "valid-server":
                raise Exception("Simulated failure")
            return original_create(name, config)

        with patch.object(manager, '_create_client', side_effect=mock_create):
            success, error = await manager.reload(new_config)

        # Reload should succeed overall despite partial failure
        assert success is True
        assert error is None
        # The server that succeeded should be present
        assert "another-valid" in manager._clients
        # The failed server should have an error recorded
        assert "valid-server" in manager._connection_errors
        assert manager._connection_errors["valid-server"] != ""

    @pytest.mark.asyncio
    async def test_config_changed_helper(self):
        """Test the _config_changed helper method."""
        manager = ProxyManager()

        config1 = {
            "mcpServers": {
                "server1": {"command": "npx", "args": ["test1"]},
                "server2": {"url": "https://example.com"}
            }
        }
        manager.initialize_connections(config1)

        # Same config should not be changed
        assert manager._config_changed("server1", config1) is False
        assert manager._config_changed("server2", config1) is False

        # Different config should be changed
        config2 = {
            "mcpServers": {
                "server1": {"command": "uvx", "args": ["test1"]},  # Changed
                "server2": {"url": "https://example.com"}  # Same
            }
        }
        assert manager._config_changed("server1", config2) is True
        assert manager._config_changed("server2", config2) is False
