# Milestone 3: Developer Experience

**Status:** Not Started
**Target:** Excellent developer experience with easy setup, validation, deployment, and documentation

---

## Overview

M3 focuses on making the gateway easy to use, configure, deploy, and troubleshoot. This milestone adds:
- Single-agent mode for simplified development workflows
- Configuration validation CLI to catch errors early
- Docker container for easy deployment
- Comprehensive documentation and examples
- Testing infrastructure and utilities
- Development tools and helpers

**Key Success Metric:** Developers can go from zero to running gateway in <5 minutes with clear documentation and helpful tooling.

---

## Core Components

### 1. Single-Agent Mode
### 2. Configuration Validation CLI
### 3. Docker Container
### 4. Documentation
### 5. Testing Infrastructure
### 6. Development Tools

---

## Detailed Task Checklist

### Single-Agent Mode

- [ ] Implement default agent fallback
  - [ ] Support `GATEWAY_DEFAULT_AGENT` environment variable
  - [ ] Auto-inject agent_id when missing if default configured
  - [ ] Log when using default agent
  - [ ] Document single-agent use case

- [ ] Create single-agent configuration helper
  - [ ] Generate simple config for single developer
  - [ ] Allow all servers and tools for default agent
  - [ ] Provide template configuration

- [ ] Update middleware for single-agent mode
  - [ ] Use default agent when agent_id missing
  - [ ] Skip agent_id requirement if default configured
  - [ ] Maintain audit trail even in single-agent mode

**Code Reference:**
```python
# src/config.py
import os

def get_default_agent() -> str | None:
    """Get configured default agent, if any."""
    return os.getenv("GATEWAY_DEFAULT_AGENT")

# Middleware update
class AgentAccessControl(Middleware):
    def __init__(self, policy_engine: PolicyEngine, default_agent: str | None = None):
        self.policy_engine = policy_engine
        self.default_agent = default_agent

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        tool_call = context.message
        arguments = tool_call.arguments or {}

        # Extract agent identity
        agent_id = arguments.get("agent_id")

        if not agent_id:
            if self.default_agent:
                # Use default agent in single-agent mode
                agent_id = self.default_agent
                logger.debug(f"Using default agent: {agent_id}")
            elif self.policy_engine.defaults.get("deny_on_missing_agent", True):
                raise InvalidAgentIdError("agent_id required and no default configured")
            else:
                agent_id = "default"

        # ... rest of middleware logic
```

**Example Single-Agent Config:**
```json
{
  "agents": {
    "developer": {
      "allow": {
        "servers": ["*"],
        "tools": {"*": ["*"]}
      }
    }
  },
  "defaults": {
    "deny_on_missing_agent": false
  }
}
```

**Environment Variable:**
```bash
GATEWAY_DEFAULT_AGENT=developer
```

### Configuration Validation CLI

- [ ] Create validation command
  - [ ] Add `uv run python -m src.cli validate` command
  - [ ] Validate .mcp.json structure
  - [ ] Validate gateway-rules.json structure
  - [ ] Check for common errors
  - [ ] Provide helpful error messages

- [ ] Implement validation checks
  - [ ] Validate JSON syntax (error)
  - [ ] Check for required fields (error)
  - [ ] Warn about servers in rules not in mcp-config (warning only - runtime allows this)
  - [ ] Validate environment variable references (warning)
  - [ ] Check for conflicting rules (info)
  - [ ] Test connectivity to configured servers (warning)

- [ ] Add config generation commands
  - [ ] `generate-config --single-agent` for simple setup
  - [ ] `generate-config --multi-agent` for team setup
  - [ ] Interactive configuration builder

- [ ] Create config examples
  - [ ] Example configs for common scenarios
  - [ ] Documentation for each config option
  - [ ] Best practices guide

**Code Reference:**
```python
# src/cli.py
import click
import json
from pathlib import Path
from typing import List, Tuple

@click.group()
def cli():
    """Agent MCP Gateway CLI."""
    pass

@cli.command()
@click.option("--mcp-config", default="./config/.mcp.json", help="Path to MCP servers config")
@click.option("--rules", default="./config/gateway-rules.json", help="Path to gateway rules")
def validate(mcp_config: str, rules: str):
    """Validate gateway configuration files."""
    click.echo("🔍 Validating configuration files...")

    errors = []
    warnings = []

    # Validate MCP config
    mcp_errors, mcp_warnings = validate_mcp_config(mcp_config)
    errors.extend(mcp_errors)
    warnings.extend(mcp_warnings)

    # Validate rules config
    rules_errors, rules_warnings = validate_rules_config(rules, mcp_config)
    errors.extend(rules_errors)
    warnings.extend(rules_warnings)

    # Report results
    if errors:
        click.echo(f"\n❌ Found {len(errors)} error(s):")
        for error in errors:
            click.echo(f"  • {error}", err=True)

    if warnings:
        click.echo(f"\n⚠️  Found {len(warnings)} warning(s):")
        for warning in warnings:
            click.echo(f"  • {warning}")

    if not errors and not warnings:
        click.echo("\n✅ Configuration is valid!")
        return

    if errors:
        raise click.ClickException("Configuration validation failed")

def validate_mcp_config(path: str) -> Tuple[List[str], List[str]]:
    """Validate MCP servers configuration."""
    errors = []
    warnings = []

    try:
        with open(path, 'r') as f:
            config = json.load(f)
    except FileNotFoundError:
        errors.append(f"MCP config file not found: {path}")
        return errors, warnings
    except json.JSONDecodeError as e:
        errors.append(f"Invalid JSON in MCP config: {e}")
        return errors, warnings

    # Check structure
    if "mcpServers" not in config:
        errors.append("MCP config missing 'mcpServers' key")
        return errors, warnings

    servers = config["mcpServers"]
    if not servers:
        warnings.append("No MCP servers configured")

    # Validate each server
    for name, server_config in servers.items():
        has_command = "command" in server_config
        has_url = "url" in server_config

        if not has_command and not has_url:
            errors.append(f"Server '{name}' missing 'command' or 'url'")

        if has_command and has_url:
            warnings.append(f"Server '{name}' has both 'command' and 'url' (will use url)")

        # Check for env var references
        if "env" in server_config:
            for key, value in server_config["env"].items():
                if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                    env_var = value[2:-1]
                    import os
                    if env_var not in os.environ:
                        warnings.append(f"Server '{name}' references undefined env var: {env_var}")

    return errors, warnings

def validate_rules_config(rules_path: str, mcp_path: str) -> Tuple[List[str], List[str]]:
    """Validate gateway rules configuration."""
    errors = []
    warnings = []

    # Load both configs
    try:
        with open(rules_path, 'r') as f:
            rules = json.load(f)
    except FileNotFoundError:
        errors.append(f"Rules config file not found: {rules_path}")
        return errors, warnings
    except json.JSONDecodeError as e:
        errors.append(f"Invalid JSON in rules config: {e}")
        return errors, warnings

    try:
        with open(mcp_path, 'r') as f:
            mcp_config = json.load(f)
    except:
        # Already validated in validate_mcp_config
        return errors, warnings

    available_servers = set(mcp_config.get("mcpServers", {}).keys())

    # Validate agents
    agents = rules.get("agents", {})
    if not agents:
        warnings.append("No agents configured")

    for agent_name, agent_rules in agents.items():
        # Check allow rules
        if "allow" in agent_rules:
            allow = agent_rules["allow"]
            if "servers" in allow:
                for server in allow["servers"]:
                    if server != "*" and server not in available_servers:
                        # Note: Runtime treats this as a warning, not an error
                        # CLI can be stricter to help catch configuration issues early
                        warnings.append(f"Agent '{agent_name}' references unknown server: {server}")

        # Check deny rules
        if "deny" in agent_rules:
            deny = agent_rules["deny"]
            if "servers" in deny:
                for server in deny["servers"]:
                    if server != "*" and server not in available_servers:
                        # Note: Runtime treats this as a warning, not an error
                        warnings.append(f"Agent '{agent_name}' denies unknown server: {server}")

    return errors, warnings

@cli.command()
@click.option("--type", type=click.Choice(["single-agent", "multi-agent"]), default="single-agent")
@click.option("--output", default="./config", help="Output directory")
def generate_config(type: str, output: str):
    """Generate example configuration files."""
    output_path = Path(output)
    output_path.mkdir(parents=True, exist_ok=True)

    if type == "single-agent":
        _generate_single_agent_config(output_path)
    else:
        _generate_multi_agent_config(output_path)

    click.echo(f"✅ Generated {type} configuration in {output}")

def _generate_single_agent_config(output_path: Path):
    """Generate single-agent configuration."""
    mcp_config = {
        "mcpServers": {
            "example": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-example"],
                "env": {}
            }
        }
    }

    rules_config = {
        "agents": {
            "developer": {
                "allow": {
                    "servers": ["*"],
                    "tools": {"*": ["*"]}
                }
            }
        },
        "defaults": {
            "deny_on_missing_agent": false
        }
    }

    with open(output_path / ".mcp.json", "w") as f:
        json.dump(mcp_config, f, indent=2)

    with open(output_path / "gateway-rules.json", "w") as f:
        json.dump(rules_config, f, indent=2)

if __name__ == "__main__":
    cli()
```

### Docker Container

- [ ] Create Dockerfile
  - [ ] Multi-stage build for smaller image
  - [ ] Python 3.12+ base image
  - [ ] Install uv for dependency management
  - [ ] Copy source code
  - [ ] Install dependencies
  - [ ] Set up non-root user
  - [ ] Expose port 8000
  - [ ] Health check configuration

- [ ] Create docker-compose.yml
  - [ ] Gateway service definition
  - [ ] Volume mounts for configs
  - [ ] Environment variable configuration
  - [ ] Network configuration
  - [ ] Example downstream services (optional)

- [ ] Add container documentation
  - [ ] Build instructions
  - [ ] Run instructions
  - [ ] Configuration via environment variables
  - [ ] Volume mount examples
  - [ ] Docker Compose usage

**Code Reference:**
```dockerfile
# Dockerfile
FROM python:3.12-slim AS builder

# Install uv
RUN pip install uv

WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen

# Production stage
FROM python:3.12-slim

# Create non-root user
RUN useradd -m -u 1000 gateway && \
    mkdir -p /app /config /logs && \
    chown -R gateway:gateway /app /config /logs

WORKDIR /app

# Copy dependencies from builder
COPY --from=builder --chown=gateway:gateway /app/.venv /app/.venv

# Copy application code
COPY --chown=gateway:gateway src/ ./src/
COPY --chown=gateway:gateway main.py ./

# Switch to non-root user
USER gateway

# Environment variables
ENV PATH="/app/.venv/bin:$PATH" \
    GATEWAY_MCP_CONFIG="/config/.mcp.json" \
    GATEWAY_RULES="/config/gateway-rules.json" \
    GATEWAY_TRANSPORT="http" \
    GATEWAY_HTTP_HOST="0.0.0.0" \
    GATEWAY_HTTP_PORT="8000"

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

# Run gateway
CMD ["python", "main.py"]
```

```yaml
# docker-compose.yml
version: '3.8'

services:
  gateway:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./config:/config:ro
      - ./logs:/logs
    environment:
      - GATEWAY_MCP_CONFIG=/config/.mcp.json
      - GATEWAY_RULES=/config/gateway-rules.json
      - GATEWAY_TRANSPORT=http
      - GATEWAY_DEFAULT_AGENT=developer
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 3s
      retries: 3
    restart: unless-stopped
```

### Documentation

- [ ] Create comprehensive README.md
  - [ ] Project overview
  - [ ] Quick start guide
  - [ ] Installation instructions
  - [ ] Configuration guide
  - [ ] Usage examples
  - [ ] API reference
  - [ ] Troubleshooting

- [ ] Create user guides
  - [ ] Getting started tutorial
  - [ ] Configuration guide
  - [ ] Policy rules guide
  - [ ] Deployment guide
  - [ ] Monitoring guide

- [ ] Create developer documentation
  - [ ] Architecture overview
  - [ ] Contributing guidelines
  - [ ] Development setup
  - [ ] Testing guide
  - [ ] Release process

- [ ] Create example configurations
  - [ ] Single developer setup
  - [ ] Multi-agent team setup
  - [ ] Production deployment
  - [ ] Common use cases

**README.md Outline:**
```markdown
# Agent MCP Gateway

Context Window-Preserving MCP Proxy with Dynamic Discovery

## Overview
[Brief description of the problem and solution]

## Quick Start

### Installation
```bash
# Clone repository
git clone https://github.com/yourusername/agent-mcp-gateway.git
cd agent-mcp-gateway

# Install dependencies
uv sync

# Configure
cp config/.mcp.json.example config/.mcp.json
cp config/gateway-rules.example.json config/gateway-rules.json

# Run
GATEWAY_DEFAULT_AGENT=developer uv run python main.py
```

### Docker Quick Start
```bash
docker compose up
```

## Configuration

### MCP Servers
[Configuration guide]

### Gateway Rules
[Policy configuration guide]

### Environment Variables
[All environment variables]

## Usage

### Single-Agent Mode
[Example]

### Multi-Agent Mode
[Example]

## API Reference

### Tools
- `list_servers(agent_id)`
- `get_server_tools(agent_id, server, ...)`
- `execute_tool(agent_id, server, tool, args, ...)`

## Deployment

### Docker
[Docker deployment guide]

### Production Considerations
[Security, monitoring, scaling]

## Development

### Running Tests
```bash
uv run pytest
```

### Contributing
[Link to CONTRIBUTING.md]

## Troubleshooting
[Common issues and solutions]

## License
[License info]
```

### Testing Infrastructure

- [ ] Expand test suite
  - [ ] Unit tests for all modules (>80% coverage)
  - [ ] Integration tests for all workflows
  - [ ] Performance tests
  - [ ] Security tests

- [ ] Add test utilities
  - [ ] Mock MCP servers for testing
  - [ ] Test fixtures for common scenarios
  - [ ] Helper functions for test setup
  - [ ] Performance benchmarking tools

- [ ] Set up CI/CD
  - [ ] GitHub Actions workflow
  - [ ] Run tests on push
  - [ ] Build Docker image
  - [ ] Publish releases

- [ ] Add testing documentation
  - [ ] How to run tests
  - [ ] How to write tests
  - [ ] Test coverage requirements
  - [ ] Performance benchmarks

**Code Reference:**
```python
# tests/conftest.py
import pytest
from fastmcp import FastMCP
from src.config import load_mcp_config, load_gateway_rules
from src.policy import PolicyEngine
from src.gateway import gateway

@pytest.fixture
def test_mcp_config():
    """Provide test MCP configuration."""
    return {
        "mcpServers": {
            "test-server": {
                "command": "python",
                "args": ["-m", "tests.mock_server"]
            }
        }
    }

@pytest.fixture
def test_gateway_rules():
    """Provide test gateway rules."""
    return {
        "agents": {
            "test-agent": {
                "allow": {
                    "servers": ["test-server"],
                    "tools": {"test-server": ["*"]}
                }
            }
        },
        "defaults": {
            "deny_on_missing_agent": true
        }
    }

@pytest.fixture
def policy_engine(test_gateway_rules):
    """Provide configured policy engine."""
    return PolicyEngine(test_gateway_rules)

@pytest.fixture
async def mock_mcp_server():
    """Provide a mock MCP server for testing."""
    server = FastMCP(name="MockServer")

    @server.tool
    def test_tool(param: str) -> str:
        return f"Executed with: {param}"

    return server
```

```yaml
# .github/workflows/test.yml
name: Tests

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v3

    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.12'

    - name: Install uv
      run: pip install uv

    - name: Install dependencies
      run: uv sync

    - name: Run tests
      run: uv run pytest --cov=src tests/

    - name: Check coverage
      run: uv run pytest --cov=src --cov-fail-under=80 tests/

    - name: Lint
      run: |
        uv run ruff check src/
        uv run mypy src/

  docker:
    runs-on: ubuntu-latest
    needs: test

    steps:
    - uses: actions/checkout@v3

    - name: Build Docker image
      run: docker build -t agent-mcp-gateway:test .

    - name: Test Docker image
      run: |
        docker run -d --name test-gateway -p 8000:8000 agent-mcp-gateway:test
        sleep 5
        curl -f http://localhost:8000/health
        docker stop test-gateway
```

### Development Tools

- [ ] Add development helpers
  - [ ] Hot reload for development
  - [ ] Debug mode with verbose logging
  - [ ] Interactive config builder
  - [ ] Log viewer utility

- [ ] Create debugging tools
  - [ ] Policy evaluation tester
  - [ ] Request/response inspector
  - [ ] Performance profiler
  - [ ] Connection diagnostics

- [ ] Add code quality tools
  - [ ] Linting with ruff
  - [ ] Type checking with mypy
  - [ ] Code formatting with ruff format
  - [ ] Pre-commit hooks

**Code Reference:**
```python
# src/dev_tools.py
import click
from src.policy import PolicyEngine

@click.command()
@click.option("--rules", default="./config/gateway-rules.json")
@click.argument("agent_id")
@click.argument("server")
@click.argument("tool")
def test_policy(rules: str, agent_id: str, server: str, tool: str):
    """Test policy evaluation for a specific scenario."""
    from src.config import load_gateway_rules

    gateway_rules = load_gateway_rules(rules)
    policy_engine = PolicyEngine(gateway_rules)

    # Test server access
    can_access_server = policy_engine.can_access_server(agent_id, server)
    click.echo(f"Server access: {'✅ ALLOWED' if can_access_server else '❌ DENIED'}")

    if can_access_server:
        # Test tool access
        can_access_tool = policy_engine.can_access_tool(agent_id, server, tool)
        click.echo(f"Tool access: {'✅ ALLOWED' if can_access_tool else '❌ DENIED'}")

        if not can_access_tool:
            reason = policy_engine.get_deny_reason(agent_id, server, tool)
            click.echo(f"Reason: {reason}")

if __name__ == "__main__":
    test_policy()
```

```toml
# pyproject.toml additions
[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W"]
ignore = ["E501"]

[tool.mypy]
python_version = "3.12"
strict = true
warn_return_any = true
warn_unused_configs = true

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = "-v --cov=src --cov-report=html --cov-report=term"
```

---

## Success Criteria

### Usability Requirements
- [ ] Gateway runs with single command
- [ ] Configuration validation prevents common errors
- [ ] Clear error messages for all failure modes
- [ ] Documentation covers all use cases
- [ ] Examples work out of the box

### Developer Experience Requirements
- [ ] Quick start in <5 minutes
- [ ] Single-agent mode works without complex config
- [ ] Config validation catches 90%+ of errors
- [ ] Docker deployment works on first try
- [ ] Comprehensive examples provided

### Quality Requirements
- [ ] Test coverage >80%
- [ ] All code linted and type-checked
- [ ] CI/CD pipeline passes
- [ ] Documentation is complete and accurate
- [ ] Docker image <500MB

### Deployment Requirements
- [ ] Docker image builds successfully
- [ ] Docker Compose works out of box
- [ ] Health checks enable monitoring
- [ ] Logs are structured and useful
- [ ] Easy to configure in production

---

## Documentation Checklist

- [ ] README.md with quick start
- [ ] Configuration guide
- [ ] Deployment guide
- [ ] API reference
- [ ] Troubleshooting guide
- [ ] Contributing guidelines
- [ ] Example configurations
- [ ] Architecture documentation
- [ ] Development setup guide
- [ ] Testing guide

---

## Dependencies

**External:**
- click (for CLI)
- Docker (for containerization)
- pytest (for testing)
- ruff (for linting)
- mypy (for type checking)

**Internal:**
- M0 (Foundation) - Core infrastructure
- M1 (Core) - Gateway functionality
- M2 (Production) - HTTP transport, health checks

---

## Documentation References

- **FastMCP Server:** https://gofastmcp.com/servers/server
- **Docker Best Practices:** https://docs.docker.com/develop/dev-best-practices/
- **Python Packaging:** https://packaging.python.org/
- **Testing Best Practices:** https://docs.pytest.org/

---

## Notes

- Single-agent mode is essential for quick prototyping and development
- Configuration validation prevents most deployment issues
- Docker makes deployment consistent across environments
- Good documentation reduces support burden
- Testing infrastructure enables confident refactoring
- CI/CD automates quality checks
- Developer tools make debugging easier
- Examples are the best documentation
