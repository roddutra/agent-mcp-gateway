"""Unit tests for OAuth functionality in proxy infrastructure.

This module tests OAuth parameter passing for HTTP clients while ensuring
stdio clients remain unaffected. Tests verify that the gateway correctly
enables OAuth for HTTP MCP servers without breaking backward compatibility.

Test Coverage:
- TC-U1: HTTP client gets OAuth parameter
- TC-U2: stdio client does NOT get OAuth parameter
- TC-U3: HTTP client with headers gets OAuth
- TC-U4: Multiple HTTP clients all get OAuth
- TC-U5: Mixed transports (stdio + HTTP) work correctly
- TC-U6: Backward compatibility - existing HTTP clients still work
- TC-U7: Backward compatibility - existing stdio clients still work
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch

from src.proxy import ProxyManager


class TestOAuthParameterPassing:
    """Test cases for OAuth parameter in Client creation."""

    def test_create_http_client_with_oauth_enabled(self):
        """TC-U1: Verify HTTP clients are created with auth='oauth' parameter."""
        manager = ProxyManager()
        config = {
            "url": "https://mcp.notion.com/mcp"
        }

        with patch('src.proxy.Client') as MockClient:
            # Setup mock to return a valid client instance
            mock_instance = Mock()
            MockClient.return_value = mock_instance

            client = manager._create_client("notion", config)

            # Verify Client was called with auth="oauth"
            MockClient.assert_called_once()
            call_args = MockClient.call_args

            # Check positional args - URL should be first arg
            assert len(call_args.args) >= 1
            assert call_args.args[0] == "https://mcp.notion.com/mcp"

            # Check keyword args - auth should be "oauth"
            assert 'auth' in call_args.kwargs
            assert call_args.kwargs['auth'] == 'oauth'

            # Verify client was returned
            assert client is mock_instance

    def test_create_stdio_client_without_oauth(self):
        """TC-U2: Verify stdio clients are NOT created with OAuth parameter."""
        manager = ProxyManager()
        config = {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-brave-search"]
        }

        with patch('src.proxy.Client') as MockClient:
            # Setup mock to return a valid client instance
            mock_instance = Mock()
            MockClient.return_value = mock_instance

            client = manager._create_client("brave-search", config)

            # Verify Client was called WITHOUT auth parameter
            MockClient.assert_called_once()
            call_kwargs = MockClient.call_args.kwargs

            # Check that 'auth' is not in kwargs or is None
            assert call_kwargs.get('auth') is None

            # Verify transport parameter was passed instead
            assert 'transport' in call_kwargs
            assert 'mcpServers' in call_kwargs['transport']
            assert 'brave-search' in call_kwargs['transport']['mcpServers']

            # Verify client was returned
            assert client is mock_instance

    def test_create_http_client_with_headers_and_oauth(self):
        """TC-U3: Verify HTTP clients with custom headers also get OAuth enabled."""
        manager = ProxyManager()
        config = {
            "url": "https://api.example.com/mcp",
            "headers": {
                "X-API-Version": "2024-01-01",
                "X-Custom-Header": "value"
            }
        }

        with patch('src.proxy.Client') as MockClient:
            # Setup mock to return a valid client instance
            mock_instance = Mock()
            MockClient.return_value = mock_instance

            client = manager._create_client("custom-api", config)

            # Verify Client was called with auth="oauth"
            MockClient.assert_called_once()
            call_args = MockClient.call_args

            # Check auth parameter
            assert call_args.kwargs['auth'] == 'oauth'

            # Check URL parameter
            assert call_args.args[0] == "https://api.example.com/mcp"

            # Note: Current implementation prioritizes OAuth over custom headers
            # This is expected behavior per the implementation in proxy.py
            # Custom headers may conflict with OAuth, as noted in implementation

            # Verify client was returned
            assert client is mock_instance

    def test_initialize_multiple_http_oauth_clients(self):
        """TC-U4: Verify multiple HTTP servers all get OAuth enabled."""
        manager = ProxyManager()
        config = {
            "mcpServers": {
                "notion": {
                    "url": "https://mcp.notion.com/mcp"
                },
                "github": {
                    "url": "https://api.github.com/mcp"
                }
            }
        }

        with patch('src.proxy.Client') as MockClient:
            # Setup mock to return a valid client instance
            mock_instance = Mock()
            MockClient.return_value = mock_instance

            manager.initialize_connections(config)

            # Verify both calls included OAuth
            assert MockClient.call_count == 2

            for call in MockClient.call_args_list:
                # Each call should have auth='oauth'
                assert 'auth' in call.kwargs
                assert call.kwargs['auth'] == 'oauth'

                # Each call should have a URL as first positional arg
                assert len(call.args) >= 1
                assert call.args[0] in [
                    "https://mcp.notion.com/mcp",
                    "https://api.github.com/mcp"
                ]

    def test_initialize_mixed_stdio_and_http_transports(self):
        """TC-U5: Verify mixed stdio + HTTP config creates correct clients."""
        manager = ProxyManager()
        config = {
            "mcpServers": {
                "brave-search": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-brave-search"],
                    "env": {"BRAVE_API_KEY": "${BRAVE_API_KEY}"}
                },
                "notion": {
                    "url": "https://mcp.notion.com/mcp"
                }
            }
        }

        with patch('src.proxy.Client') as MockClient:
            # Setup mock to return a valid client instance
            mock_instance = Mock()
            MockClient.return_value = mock_instance

            clients = manager.initialize_connections(config)

            assert len(clients) == 2
            assert 'brave-search' in clients
            assert 'notion' in clients

            # Verify the two calls had different configurations
            assert MockClient.call_count == 2
            calls = MockClient.call_args_list

            # Find the OAuth call and the stdio call
            oauth_call = None
            stdio_call = None

            for call in calls:
                if call.kwargs.get('auth') == 'oauth':
                    oauth_call = call
                elif 'transport' in call.kwargs:
                    stdio_call = call

            # Verify we found both types
            assert oauth_call is not None, "Should have one OAuth HTTP call"
            assert stdio_call is not None, "Should have one stdio transport call"

            # Verify OAuth call structure
            assert len(oauth_call.args) >= 1
            assert oauth_call.args[0] == "https://mcp.notion.com/mcp"

            # Verify stdio call structure
            assert 'mcpServers' in stdio_call.kwargs['transport']
            assert 'brave-search' in stdio_call.kwargs['transport']['mcpServers']

    def test_backward_compatible_http_client(self):
        """TC-U6: Verify adding OAuth doesn't break existing HTTP client functionality."""
        manager = ProxyManager()
        config = {
            "url": "https://api.example.com/mcp"
        }

        # Should not raise any errors
        with patch('src.proxy.Client') as MockClient:
            mock_instance = Mock()
            MockClient.return_value = mock_instance

            client = manager._create_client("example", config)

            assert client is not None
            assert client is mock_instance

            # Verify Client was called successfully
            MockClient.assert_called_once()

            # OAuth parameter should be present (new behavior)
            # but shouldn't break client creation
            assert MockClient.call_args.kwargs.get('auth') == 'oauth'

    def test_backward_compatible_stdio_client(self):
        """TC-U7: Verify stdio clients are completely unaffected by OAuth changes."""
        manager = ProxyManager()
        config = {
            "command": "uvx",
            "args": ["mcp-server-postgres"],
            "env": {"DATABASE_URL": "postgresql://localhost/test"}
        }

        with patch('src.proxy.Client') as MockClient:
            mock_instance = Mock()
            MockClient.return_value = mock_instance

            client = manager._create_client("postgres", config)

            call_kwargs = MockClient.call_args.kwargs

            # auth should not be present OR should be None
            assert call_kwargs.get('auth') is None

            # transport should be present with correct structure
            assert 'transport' in call_kwargs
            assert 'mcpServers' in call_kwargs['transport']
            assert 'postgres' in call_kwargs['transport']['mcpServers']

            # Original config should be preserved
            server_config = call_kwargs['transport']['mcpServers']['postgres']
            assert server_config['command'] == 'uvx'
            assert server_config['args'] == ["mcp-server-postgres"]
            assert server_config['env'] == {"DATABASE_URL": "postgresql://localhost/test"}


class TestOAuthIntegrationWithProxyManager:
    """Integration tests for OAuth with ProxyManager operations."""

    @pytest.mark.asyncio
    async def test_http_oauth_client_can_be_retrieved(self):
        """Verify HTTP OAuth clients can be retrieved and used."""
        manager = ProxyManager()
        config = {
            "mcpServers": {
                "notion": {
                    "url": "https://mcp.notion.com/mcp"
                }
            }
        }

        with patch('src.proxy.Client') as MockClient:
            # Setup mock client with async context manager support
            mock_instance = Mock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_instance

            manager.initialize_connections(config)

            # Should be able to retrieve the client
            client = manager.get_client("notion")
            assert client is not None

            # Verify OAuth was enabled during creation
            assert MockClient.call_args.kwargs['auth'] == 'oauth'

    @pytest.mark.asyncio
    async def test_mixed_clients_both_retrievable(self):
        """Verify both stdio and HTTP OAuth clients can coexist."""
        manager = ProxyManager()
        config = {
            "mcpServers": {
                "brave-search": {
                    "command": "npx",
                    "args": ["-y", "test-server"]
                },
                "notion": {
                    "url": "https://mcp.notion.com/mcp"
                }
            }
        }

        with patch('src.proxy.Client') as MockClient:
            # Setup mock client with async context manager support
            mock_instance = Mock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_instance

            manager.initialize_connections(config)

            # Both clients should be retrievable
            brave_client = manager.get_client("brave-search")
            notion_client = manager.get_client("notion")

            assert brave_client is not None
            assert notion_client is not None

            # Verify server list
            servers = manager.get_all_servers()
            assert len(servers) == 2
            assert "brave-search" in servers
            assert "notion" in servers
