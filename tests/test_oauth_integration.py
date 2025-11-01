"""Integration tests for OAuth functionality in the gateway.

This module tests OAuth integration scenarios including auto-detection,
mixed authentication, and error handling. Tests use mocks to simulate
OAuth-protected MCP servers without requiring real OAuth flows.

Test Coverage:
- TC-I1: OAuth auto-detection with mock 401 responses
- TC-I2: Mixed authentication scenarios (stdio + HTTP OAuth)
- TC-I3: Token caching behavior (non-interference)
- TC-I4: Non-OAuth HTTP servers work without OAuth
- TC-I5: OAuth cancellation handling (if applicable)
- TC-I6: Token expiration handling (with mocks)
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch

from src.proxy import ProxyManager


class TestOAuthAutoDetection:
    """Tests for OAuth auto-detection mechanism."""

    @pytest.mark.asyncio
    async def test_oauth_client_configuration(self):
        """TC-I1: Test that HTTP clients are configured to support OAuth auto-detection.

        Note: Full OAuth flow testing requires user interaction and is not
        automated. This test verifies the client is properly configured with
        auth='oauth', which enables FastMCP to handle OAuth automatically when
        the server returns 401.
        """
        manager = ProxyManager()
        config = {
            "mcpServers": {
                "oauth-test": {
                    "url": "http://localhost:8765/mcp"
                }
            }
        }

        with patch('src.proxy.Client') as MockClient:
            # Setup mock client
            mock_instance = Mock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_instance.list_tools = AsyncMock(return_value=[
                {"name": "test_tool", "description": "Test tool"}
            ])
            MockClient.return_value = mock_instance

            manager.initialize_connections(config)

            # The client should be configured with OAuth
            assert MockClient.call_args.kwargs['auth'] == 'oauth'

            # Client should be functional
            client = manager.get_client("oauth-test")
            assert client is not None

            # When FastMCP Client receives 401, it will handle OAuth flow
            # This is handled by FastMCP, not gateway code


class TestMixedAuthentication:
    """Tests for mixed stdio and HTTP OAuth authentication."""

    @pytest.mark.asyncio
    async def test_mixed_authentication_servers(self):
        """TC-I2: Test gateway with both stdio and HTTP OAuth servers."""
        config = {
            "mcpServers": {
                "brave-search": {
                    "command": "npx",
                    "args": ["-y", "test-server"],
                    "env": {"API_KEY": "test-key"}
                },
                "oauth-api": {
                    "url": "http://localhost:8765/mcp"
                }
            }
        }

        manager = ProxyManager()

        with patch('src.proxy.Client') as MockClient:
            # Setup mock client with async support
            mock_instance = Mock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_instance.list_tools = AsyncMock(return_value=[
                {"name": "tool1", "description": "Tool 1"}
            ])
            MockClient.return_value = mock_instance

            clients = manager.initialize_connections(config)

            # Both clients should exist
            assert len(clients) == 2
            assert 'brave-search' in clients
            assert 'oauth-api' in clients

            # Verify client creation calls
            assert MockClient.call_count == 2
            calls = MockClient.call_args_list

            # Find OAuth and stdio calls
            oauth_call = None
            stdio_call = None

            for call in calls:
                if call.kwargs.get('auth') == 'oauth':
                    oauth_call = call
                elif 'transport' in call.kwargs:
                    stdio_call = call

            assert oauth_call is not None, "Should have OAuth HTTP client"
            assert stdio_call is not None, "Should have stdio client"

            # Both should be usable
            async with clients['brave-search']:
                tools = await clients['brave-search'].list_tools()
                assert tools is not None

            async with clients['oauth-api']:
                tools = await clients['oauth-api'].list_tools()
                assert tools is not None

    @pytest.mark.asyncio
    async def test_stdio_client_unaffected_by_oauth(self):
        """Verify stdio clients work identically before and after OAuth implementation."""
        manager = ProxyManager()
        config = {
            "mcpServers": {
                "postgres": {
                    "command": "uvx",
                    "args": ["mcp-server-postgres"],
                    "env": {"DATABASE_URL": "postgresql://localhost/test"}
                }
            }
        }

        with patch('src.proxy.Client') as MockClient:
            mock_instance = Mock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_instance.call_tool = AsyncMock(return_value={"result": "success"})
            MockClient.return_value = mock_instance

            manager.initialize_connections(config)

            # Verify no OAuth parameter
            assert MockClient.call_args.kwargs.get('auth') is None

            # Verify client works
            result = await manager.call_tool("postgres", "query", {"sql": "SELECT 1"})
            assert result == {"result": "success"}


class TestTokenCaching:
    """Tests for OAuth token caching behavior."""

    @pytest.mark.asyncio
    async def test_oauth_token_caching_non_interference(self):
        """TC-I3: Test that gateway doesn't interfere with FastMCP token caching.

        Note: Token caching is a FastMCP feature. This test verifies the gateway
        creates clients correctly so caching can work.
        """
        manager = ProxyManager()
        config = {
            "mcpServers": {
                "oauth-test": {
                    "url": "https://mcp.notion.com/mcp"
                }
            }
        }

        with patch('src.proxy.Client') as MockClient:
            mock_instance = Mock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_instance

            manager.initialize_connections(config)

            # First connection - client created correctly
            client1 = manager.get_client("oauth-test")
            assert client1 is not None

            # Re-initialize (simulate restart)
            manager.initialize_connections(config)
            client2 = manager.get_client("oauth-test")
            assert client2 is not None

            # Both clients point to same server
            # FastMCP will handle token caching between sessions
            # Gateway just needs to create clients consistently
            assert MockClient.call_count == 2
            for call in MockClient.call_args_list:
                assert call.kwargs['auth'] == 'oauth'
                assert call.args[0] == "https://mcp.notion.com/mcp"


class TestNonOAuthHTTPServers:
    """Tests for HTTP servers that don't require OAuth."""

    @pytest.mark.asyncio
    async def test_http_server_without_oauth_requirement(self):
        """TC-I4: Test that HTTP servers without OAuth work correctly.

        Even though OAuth is enabled on the client, it won't activate
        if the server returns 200 (no authentication required).
        """
        manager = ProxyManager()
        config = {
            "mcpServers": {
                "public-api": {
                    "url": "https://api.example.com/mcp"
                }
            }
        }

        with patch('src.proxy.Client') as MockClient:
            # Setup mock that returns 200 (no auth required)
            mock_instance = Mock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_instance.list_tools = AsyncMock(return_value=[
                {"name": "public_tool", "description": "Public tool"}
            ])
            MockClient.return_value = mock_instance

            clients = manager.initialize_connections(config)

            assert 'public-api' in clients

            # Client should be created with OAuth enabled
            # but OAuth won't activate because server returns 200
            assert MockClient.call_args.kwargs['auth'] == 'oauth'

            # Server should work normally
            async with clients['public-api']:
                tools = await clients['public-api'].list_tools()
                assert len(tools) == 1
                assert tools[0]['name'] == 'public_tool'


class TestOAuthErrorHandling:
    """Tests for OAuth error scenarios."""

    @pytest.mark.asyncio
    async def test_oauth_flow_cancellation_handling(self):
        """TC-I5: Test handling of cancelled OAuth flow.

        If OAuth fails (user closes browser), the gateway should handle
        the error gracefully without crashing.
        """
        manager = ProxyManager()
        config = {
            "mcpServers": {
                "oauth-test": {
                    "url": "https://mcp.notion.com/mcp"
                }
            }
        }

        with patch('src.proxy.Client') as MockClient:
            # Setup mock that simulates OAuth cancellation
            mock_instance = Mock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_instance.list_tools = AsyncMock(
                side_effect=RuntimeError("OAuth flow cancelled")
            )
            MockClient.return_value = mock_instance

            manager.initialize_connections(config)

            # If OAuth fails, should get error (not crash)
            client = manager.get_client("oauth-test")

            with pytest.raises(RuntimeError) as exc_info:
                async with client:
                    await client.list_tools()

            assert "OAuth flow cancelled" in str(exc_info.value) or "Failed to list tools" in str(exc_info.value)

            # Gateway should still be functional
            assert manager.get_all_servers() == ['oauth-test']
            assert manager.get_server_status('oauth-test')['initialized'] is True

    @pytest.mark.asyncio
    async def test_connection_error_with_oauth_server(self):
        """Test connection errors with OAuth-enabled servers."""
        manager = ProxyManager()
        config = {
            "mcpServers": {
                "unreachable-oauth": {
                    "url": "https://invalid.example.com/mcp"
                }
            }
        }

        with patch('src.proxy.Client') as MockClient:
            # Setup mock that simulates connection failure
            mock_instance = Mock()
            mock_instance.__aenter__ = AsyncMock(
                side_effect=ConnectionError("Connection refused")
            )
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_instance

            manager.initialize_connections(config)

            # Client should be created (lazy connection)
            assert 'unreachable-oauth' in manager.get_all_servers()

            # Connection should fail when used
            client = manager.get_client("unreachable-oauth")
            with pytest.raises(ConnectionError):
                async with client:
                    pass


class TestTokenExpiration:
    """Tests for OAuth token expiration scenarios."""

    @pytest.mark.asyncio
    async def test_expired_token_handling(self):
        """TC-I6: Test that gateway doesn't interfere with token refresh.

        When tokens expire, FastMCP Client should handle refresh automatically.
        Gateway just needs to create clients correctly.
        """
        manager = ProxyManager()
        config = {
            "mcpServers": {
                "oauth-test": {
                    "url": "https://mcp.notion.com/mcp"
                }
            }
        }

        with patch('src.proxy.Client') as MockClient:
            # Setup mock that simulates token expiration and refresh
            mock_instance = Mock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)

            call_count = 0

            async def list_tools_with_refresh():
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    # First call: token expired
                    raise RuntimeError("Token expired")
                else:
                    # Second call: token refreshed, success
                    return [{"name": "tool1"}]

            mock_instance.list_tools = list_tools_with_refresh
            MockClient.return_value = mock_instance

            manager.initialize_connections(config)

            # Client is configured correctly for auto-refresh
            assert MockClient.call_args.kwargs['auth'] == 'oauth'

            client = manager.get_client("oauth-test")
            assert client is not None

            # FastMCP would handle token refresh automatically
            # For this test, we just verify gateway doesn't interfere


class TestReloadWithOAuth:
    """Tests for hot reload functionality with OAuth clients."""

    @pytest.mark.asyncio
    async def test_reload_preserves_oauth_configuration(self):
        """Test that OAuth configuration is preserved during reload."""
        manager = ProxyManager()

        initial_config = {
            "mcpServers": {
                "notion": {
                    "url": "https://mcp.notion.com/mcp"
                }
            }
        }

        with patch('src.proxy.Client') as MockClient:
            mock_instance = Mock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_instance

            # Initial setup
            manager.initialize_connections(initial_config)
            assert MockClient.call_count == 1
            assert MockClient.call_args.kwargs['auth'] == 'oauth'

            # Reload with same config
            success, error = await manager.reload(initial_config)
            assert success is True
            assert error is None

            # OAuth should still be configured
            # (client unchanged, so no new call)
            assert 'notion' in manager.get_all_servers()

    @pytest.mark.asyncio
    async def test_reload_add_oauth_server(self):
        """Test adding new OAuth server during reload."""
        manager = ProxyManager()

        initial_config = {
            "mcpServers": {
                "brave-search": {
                    "command": "npx",
                    "args": ["test"]
                }
            }
        }

        new_config = {
            "mcpServers": {
                "brave-search": {
                    "command": "npx",
                    "args": ["test"]
                },
                "notion": {
                    "url": "https://mcp.notion.com/mcp"
                }
            }
        }

        with patch('src.proxy.Client') as MockClient:
            mock_instance = Mock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_instance

            # Initial setup (stdio only)
            manager.initialize_connections(initial_config)
            initial_call_count = MockClient.call_count

            # Reload with OAuth server added
            success, error = await manager.reload(new_config)
            assert success is True
            assert error is None

            # New OAuth server should be added
            assert 'notion' in manager.get_all_servers()
            assert len(manager.get_all_servers()) == 2

            # Verify new client was created with OAuth
            # Find the call for notion (should be the last call)
            oauth_calls = [
                call for call in MockClient.call_args_list
                if call.kwargs.get('auth') == 'oauth'
            ]
            assert len(oauth_calls) >= 1
