#!/usr/bin/env python3
"""Integration test for Agent MCP Gateway."""

import asyncio
import json
from fastmcp import Client


async def test_list_servers():
    """Test the list_servers tool with different agents."""

    print("Starting integration test...")
    print("=" * 60)

    # Use main_test.py which sets test config paths
    async with Client("main_test.py") as client:
        print("\nGateway connected successfully!")

        # Test 1: Researcher agent (should see brave-search)
        print("\n1. Testing researcher agent:")
        result = await client.call_tool("list_servers", {
            "agent_id": "researcher"
        })
        data = result.content[0].text if hasattr(result.content[0], 'text') else result.content
        servers = json.loads(data) if isinstance(data, str) else data
        print(f"   Allowed servers: {json.dumps(servers, indent=2)}")
        assert len(servers) == 1
        assert servers[0]["name"] == "brave-search"
        assert servers[0]["transport"] == "stdio"
        print("   ✓ Researcher can access brave-search only")

        # Test 2: Backend agent (should see postgres and filesystem)
        print("\n2. Testing backend agent:")
        result = await client.call_tool("list_servers", {
            "agent_id": "backend"
        })
        data = result.content[0].text if hasattr(result.content[0], 'text') else result.content
        servers = json.loads(data) if isinstance(data, str) else data
        print(f"   Allowed servers: {json.dumps(servers, indent=2)}")
        assert len(servers) == 2
        server_names = {s["name"] for s in servers}
        assert "postgres" in server_names
        assert "filesystem" in server_names
        print("   ✓ Backend can access postgres and filesystem")

        # Test 3: Admin agent (should see all servers)
        print("\n3. Testing admin agent:")
        result = await client.call_tool("list_servers", {
            "agent_id": "admin"
        })
        data = result.content[0].text if hasattr(result.content[0], 'text') else result.content
        servers = json.loads(data) if isinstance(data, str) else data
        print(f"   Allowed servers: {json.dumps(servers, indent=2)}")
        assert len(servers) == 3
        server_names = {s["name"] for s in servers}
        assert "brave-search" in server_names
        assert "postgres" in server_names
        assert "filesystem" in server_names
        print("   ✓ Admin can access all servers (wildcard access)")

        # Test 4: Unknown agent (should see no servers with deny_on_missing_agent=true)
        print("\n4. Testing unknown agent:")
        result = await client.call_tool("list_servers", {
            "agent_id": "unknown_agent"
        })
        if result.content:
            data = result.content[0].text if hasattr(result.content[0], 'text') else result.content
            servers = json.loads(data) if isinstance(data, str) else data
        else:
            servers = []
        print(f"   Allowed servers: {json.dumps(servers, indent=2)}")
        assert len(servers) == 0
        print("   ✓ Unknown agent denied (default policy)")

        # Test 5: Test with metadata
        print("\n5. Testing with metadata:")
        result = await client.call_tool("list_servers", {
            "agent_id": "researcher",
            "include_metadata": True
        })
        data = result.content[0].text if hasattr(result.content[0], 'text') else result.content
        servers = json.loads(data) if isinstance(data, str) else data
        print(f"   Server details: {json.dumps(servers, indent=2)}")
        assert "command" in servers[0]
        print("   ✓ Metadata included when requested")

    print("\n" + "=" * 60)
    print("All integration tests passed! ✓")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_list_servers())
