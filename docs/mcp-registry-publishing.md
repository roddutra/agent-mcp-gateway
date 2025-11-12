# MCP Registry Publishing

This document outlines how agent-mcp-gateway is published to the [MCP Registry](https://github.com/modelcontextprotocol/registry) to enable discovery by MCP clients.

## Overview

The MCP Registry is a centralized directory where users and clients can discover MCP servers. Publishing to the registry makes agent-mcp-gateway discoverable via tools like `npx @modelcontextprotocol/inspector`.

## Publishing Strategy

**Automated GitHub Actions** (chosen over manual CLI publishing):

- Publishes automatically when version tags are pushed (e.g., `v0.2.3`)
- Uses GitHub OIDC authentication (no secrets required)
- Runs alongside existing PyPI publishing workflow
- Maintains version synchronization across registries

## Configuration Files

### `server.json`

Located in project root, defines registry metadata:

```json
{
  "$schema": "https://registry.mcp.io/schema/server.json",
  "name": "io.github.roddutra/agent-mcp-gateway",
  "description": "Gateway proxy for MCP servers with per-agent access control",
  "homepage": "https://github.com/roddutra/agent-mcp-gateway",
  "packages": {
    "pypi": {
      "packageName": "agent-mcp-gateway"
    }
  }
}
```

**Key fields:**
- `name`: Uses `io.github.{username}/{repo}` pattern for GitHub OIDC auth
- `packages.pypi.packageName`: Links to PyPI package for ownership validation

### GitHub Actions Workflow

`.github/workflows/publish-mcp-registry.yml` handles automated publishing:

1. Triggered on version tags matching `v*.*.*`
2. Installs `mcp-publisher` CLI
3. Authenticates via GitHub OIDC tokens
4. Runs `mcp-publisher publish`
5. Executes only after successful PyPI publish

## Publishing Process

Publishing happens automatically when you follow the standard release process:

1. Update version in `pyproject.toml` and `CHANGELOG.md`
2. Run `uv lock` to sync lockfile
3. Commit changes
4. Push version tag: `git tag v0.2.3 && git push origin v0.2.3`
5. GitHub Actions workflows execute:
   - PyPI publishing (existing workflow)
   - MCP Registry publishing (new workflow)
   - GitHub release creation (existing workflow)

See `docs/release-process.md` for complete release workflow.

## Ownership Validation

The registry validates ownership via PyPI package listing:

- Package `agent-mcp-gateway` must exist on PyPI
- Package metadata must reference the MCP server name
- GitHub repository must match the package's project URL

This validation is already satisfied by the existing PyPI package and README content.

## Authentication

Uses **GitHub OIDC tokens** (no manual secrets):

- Server name pattern `io.github.{username}/*` enables automatic GitHub auth
- Workflow runs with `id-token: write` permission
- Registry validates token claims against repository
- No API keys or tokens needed in repository secrets

## Verification

After publishing, verify the server appears in the registry:

1. Search via API: `curl https://registry.mcp.io/api/servers/io.github.roddutra/agent-mcp-gateway`
2. Use MCP Inspector: `npx @modelcontextprotocol/inspector`
3. Check registry web interface

## Troubleshooting

**Publishing fails:**
- Verify PyPI package exists and is accessible
- Check GitHub repository is public
- Ensure workflow has `id-token: write` permission
- Review workflow logs for specific errors

**Server not appearing:**
- Allow up to 10 minutes for registry indexing
- Verify `server.json` schema validation passed
- Check name format matches `io.github.{username}/{repo}` pattern

## References

- [MCP Registry Publishing Guide](https://github.com/modelcontextprotocol/registry/blob/main/docs/guides/publishing/publish-server.md)
- [GitHub Actions Publishing](https://github.com/modelcontextprotocol/registry/blob/main/docs/guides/publishing/github-actions.md)
- [Registry Schema](https://registry.mcp.io/schema/server.json)
