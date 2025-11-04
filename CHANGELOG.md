# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.1] - 2025-11-05

### Fixed
- PyPI README rendering: Images and relative links now display correctly on PyPI package page
- README images now properly resolve via GitHub raw content URLs
- Documentation links now properly resolve via GitHub blob URLs with anchor support

### Technical
- Implemented `hatch-fancy-pypi-readme` plugin for build-time README transformation
- Added three regex substitution patterns to convert relative paths to absolute GitHub URLs
- Images transform to `https://raw.githubusercontent.com/.../main/<path>`
- Links transform to `https://github.com/.../blob/main/<path>#<anchor>`
- No changes to source README.md - transformations apply only during package build

## [0.1.0] - 2025-11-04

### Added

#### Core Gateway Features
- Gateway server exposing 3 minimal tools (approximately 400 tokens vs 5,000-50,000+ tokens for direct MCP server loading)
- `list_servers` tool for discovering available MCP servers based on agent permissions
- `get_server_tools` tool for on-demand tool definition retrieval with filtering support
- `execute_tool` tool for transparent proxying to downstream MCP servers
- `get_gateway_status` diagnostic tool (debug mode only) for health monitoring and troubleshooting

#### Policy Engine
- Deny-before-allow policy evaluation with exact precedence order
- Per-agent access control for servers and individual tools
- Wildcard pattern support for tool names (`get_*`, `*_user`, `*`)
- Hierarchical agent naming support (e.g., `team.role`)
- Configuration validation with warning-only mode for undefined server references
- Optional agent identity with configurable fallback chain (GATEWAY_DEFAULT_AGENT environment variable or "default" agent in rules)
- `deny_on_missing_agent` setting for strict vs fallback access control modes

#### Proxy Infrastructure
- Transparent proxying to downstream MCP servers with session isolation
- Support for stdio transport (npx/uvx commands)
- Support for HTTP transport with streaming
- OAuth authentication auto-detection and support for downstream HTTP servers
- Thread-safe proxy operations with connection pooling
- Per-request session isolation preventing concurrent request interference

#### Hot Configuration Reload
- File watcher for `.mcp.json` and `.mcp-gateway-rules.json`
- Thread-safe configuration updates without gateway restart
- Reload status tracking with timestamps, error history, and success counts
- Graceful degradation on reload failures (continues with last valid config)
- Manual reload support via SIGHUP signal

#### Monitoring and Observability
- Comprehensive audit logging for all gateway operations
- Performance metrics tracking (latency, error rates) per agent and operation
- Structured JSONL audit log format with agent_id, operation, server, tool, decision, and latency
- Debug mode with `get_gateway_status` tool for production troubleshooting

#### CLI and Configuration
- Command-line interface with `--version` and `--debug` flags
- Environment variable configuration for all settings
- Standard `.mcp.json` format compatibility (Claude Code, Cursor, VS Code)
- Flexible configuration file paths with fallback locations
- Support for environment variable substitution in server configurations
- Server descriptions in `.mcp.json` for improved agent decision-making

### Documentation
- Comprehensive README with quick start guide, configuration examples, and troubleshooting
- Product Requirements Document (PRD) with complete specifications
- M0 Foundation specification and success report
- M1 Core specification and success report
- FastMCP 2.0 implementation guide with patterns and examples
- OAuth user guide for downstream server authentication
- Security guide covering rules file security, debug mode, and production best practices
- Claude Code subagent limitations documentation with workaround details
- Example agent configurations for researcher and MCP developer roles

### Testing
- Integration test suite covering all gateway tools
- MCP Inspector compatibility for interactive testing
- Test coverage for policy engine, proxy layer, and middleware
- Performance benchmarks validating <100ms P95 latency target

### Performance
- 90%+ context window reduction (400 tokens vs 5,000-50,000+ tokens)
- <30ms proxy overhead (P95)
- <50ms list_servers latency (P95)
- <300ms get_server_tools latency (P95)

[unreleased]: https://github.com/roddutra/agent-mcp-gateway/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/roddutra/agent-mcp-gateway/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/roddutra/agent-mcp-gateway/releases/tag/v0.1.0
