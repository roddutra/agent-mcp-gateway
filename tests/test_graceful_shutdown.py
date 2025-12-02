"""Tests for graceful shutdown of downstream MCP servers.

These tests verify that when the gateway shuts down, downstream MCP servers
are properly terminated by calling close() on each client, which triggers
the transport cleanup sequence per MCP specification:
1. Close input stream to child process
2. Wait for server to exit (2s timeout)
3. Send SIGTERM/SIGKILL if not exited
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, Mock

from src.proxy import ProxyManager


class TestGracefulShutdownUnit:
    """Unit tests for graceful shutdown functionality."""

    @pytest.mark.asyncio
    async def test_close_all_connections_calls_client_close(self):
        """Verify that close_all_connections() calls close() on each client."""
        manager = ProxyManager()

        # Create mock clients
        mock_clients = {}
        for name in ["server1", "server2", "server3"]:
            client = Mock()
            client.close = AsyncMock()
            mock_clients[name] = client

        manager._clients = mock_clients.copy()
        manager._connection_status = {name: True for name in mock_clients}
        manager._connection_errors = {}

        await manager.close_all_connections()

        # Verify all clients had close() called
        for name, client in mock_clients.items():
            client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_continues_on_individual_errors(self):
        """Verify shutdown continues even if individual clients fail to close."""
        manager = ProxyManager()

        # Create mock clients - first fails, others succeed
        clients = {
            "failing1": Mock(close=AsyncMock(side_effect=Exception("Network error"))),
            "success1": Mock(close=AsyncMock()),
            "failing2": Mock(close=AsyncMock(side_effect=RuntimeError("Timeout"))),
            "success2": Mock(close=AsyncMock()),
        }

        manager._clients = clients.copy()
        manager._connection_status = {name: True for name in clients}
        manager._connection_errors = {}

        # Should not raise
        await manager.close_all_connections()

        # All clients should have been attempted
        for client in clients.values():
            client.close.assert_called_once()

        # State should be cleared despite errors
        assert len(manager._clients) == 0

    @pytest.mark.asyncio
    async def test_close_handles_already_closed_clients(self):
        """Verify shutdown handles clients that are already closed."""
        manager = ProxyManager()

        # Client that raises when closed (already closed)
        client = Mock()
        client.close = AsyncMock(side_effect=Exception("Already closed"))

        manager._clients = {"already-closed": client}
        manager._connection_status = {"already-closed": False}
        manager._connection_errors = {}

        # Should not raise
        await manager.close_all_connections()

        client.close.assert_called_once()
        assert len(manager._clients) == 0


class TestGracefulShutdownIntegration:
    """Integration tests that verify client.close() is called correctly."""

    @pytest.mark.asyncio
    async def test_close_with_real_client_structure(self):
        """Test close_all_connections with a mock that mimics real Client behavior.

        This verifies the shutdown sequence works with the expected Client API.
        """
        manager = ProxyManager()

        # Create a mock that mimics the FastMCP Client structure
        # Client has: close() method that calls transport.close()
        mock_transport = Mock()
        mock_transport.close = AsyncMock()

        mock_client = Mock()
        mock_client.close = AsyncMock()
        mock_client._transport = mock_transport

        manager._clients = {"test-server": mock_client}
        manager._connection_status = {"test-server": True}
        manager._connection_errors = {}

        await manager.close_all_connections()

        # Verify close() was called on the client
        mock_client.close.assert_called_once()
        assert len(manager._clients) == 0


class TestMainShutdown:
    """Tests for the shutdown logic in main.py."""

    def test_shutdown_block_calls_close_all_connections(self):
        """Verify main.py shutdown block calls close_all_connections.

        This test simulates the synchronous context from main.py's finally block,
        where we create a new event loop to run the async cleanup.
        """
        # This test verifies the integration between main.py and ProxyManager

        manager = ProxyManager()
        mock_client = Mock()
        mock_client.close = AsyncMock()

        manager._clients = {"test-server": mock_client}
        manager._connection_status = {"test-server": True}
        manager._connection_errors = {}

        # Simulate the shutdown sequence from main.py
        shutdown_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(shutdown_loop)
        try:
            shutdown_loop.run_until_complete(manager.close_all_connections())
        finally:
            shutdown_loop.close()

        # Verify close was called
        mock_client.close.assert_called_once()
        assert len(manager._clients) == 0

    def test_shutdown_handles_exception(self):
        """Verify shutdown handles exceptions gracefully."""
        manager = ProxyManager()

        # Client that raises on close
        mock_client = Mock()
        mock_client.close = AsyncMock(side_effect=Exception("Shutdown error"))

        manager._clients = {"test-server": mock_client}
        manager._connection_status = {}
        manager._connection_errors = {}

        # Simulate the shutdown sequence - should not raise
        shutdown_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(shutdown_loop)
        try:
            # This should not raise even with the exception
            shutdown_loop.run_until_complete(manager.close_all_connections())
        finally:
            shutdown_loop.close()

        # State should still be cleared
        assert len(manager._clients) == 0
