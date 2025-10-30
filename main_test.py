"""Test entry point for Agent MCP Gateway with test configs."""

import os

# Set test config paths before importing anything else
os.environ["GATEWAY_MCP_CONFIG"] = "./config/.mcp.test.json"
os.environ["GATEWAY_RULES"] = "./config/gateway-rules.json"

# Now import and run main
from main import main

if __name__ == "__main__":
    main()
