# Agent MCP Gateway

An MCP gateway that aggregates your existing MCP servers and lets you define which servers and individual tools each agent or subagent can access. Solves Claude Code's MCP context window waste where all tool definitions load upfront instead of being discovered when actually needed.

## Tech Stack
- FastMCP (version 2)

## Docs

- [Product Requirements Document (PRD)](/docs/specs/PRD.md)
- [FastMCP 2.0 Implementation Guide for MCP Gateway Server](/docs/fastmcp-implementation-guide.md)
- [Claude Code Subagent Identification in MCP](/docs/claude-code-subagent-mcp-limitations.md)