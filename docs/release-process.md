# Release Process

Workflow for version bumping, building, and publishing to PyPI and MCP Registry.

## Quick Reference

**Automated (Recommended):**
```bash
# Bump → Lock → Update server.json → Commit → Tag → Push
uv version --bump patch && uv lock
# Manually update server.json version fields, then:
git add pyproject.toml uv.lock CHANGELOG.md server.json && \
git commit -m "Bump version to $(uv version)" && \
git push origin main && \
git tag -a v$(uv version) -m "Release $(uv version)" && \
git push origin v$(uv version)
```

**Manual (Testing only):**
```bash
uv version --bump patch && uv lock && rm -rf dist/ && uv build --no-sources && \
uv publish --token $PYPI_TOKEN && git tag -a v$(uv version) -m "Release $(uv version)" && \
git push origin --tags
```

## Pre-Release Checklist

- [ ] Features/fixes merged to main
- [ ] Tests passing
- [ ] CHANGELOG.md ready with changes

## Release Steps

### 1. Version Bump

```bash
uv version --bump patch  # Bug fixes (0.1.0 → 0.1.1)
uv version --bump minor  # Features (0.1.0 → 0.2.0)
uv version --bump major  # Breaking (0.1.0 → 1.0.0)
```

Updates `pyproject.toml` version field.

### 2. Update Lockfile

```bash
uv lock
```

**Critical:** Always run after version bump to sync `uv.lock` package metadata.

### 3. Update server.json

Manually edit both version fields in `server.json`:
- Root `version`
- `packages[0].version`

**Critical:** MCP Registry requires these match `pyproject.toml` version.

### 4. Update CHANGELOG.md

Add version section following [Keep a Changelog](https://keepachangelog.com/) format:

```markdown
## [0.1.1] - 2025-11-05
### Fixed
- Bug description
### Added
- Feature description
```

### 5. Commit Changes

```bash
git add pyproject.toml uv.lock server.json CHANGELOG.md
git commit -m "Bump version to 0.1.1"
git push origin main
```

### 6. Create and Push Tag

```bash
git tag -a v0.1.1 -m "Release 0.1.1"
git push origin v0.1.1
```

**Tag format:** `vX.Y.Z` triggers GitHub Actions automation.

### 7. Monitor Workflows

Visit https://github.com/roddutra/agent-mcp-gateway/actions to verify:
1. PyPI Publishing
2. GitHub Release creation
3. MCP Registry publishing (runs after PyPI)

### 8. Verify Installation

```bash
uv cache clean
uvx agent-mcp-gateway@latest --version
```

## GitHub Actions Automation

Pushing a `v*.*.*` tag triggers three workflows:

### Workflows

| Workflow | File | Trigger | Actions |
|----------|------|---------|---------|
| PyPI Publishing | `publish-pypi.yml` | Tag push | Builds with `uv build --no-sources`, publishes via OIDC |
| GitHub Release | `release-github.yml` | Tag push | Extracts CHANGELOG, creates release with install instructions |
| MCP Registry | `publish-mcp-registry.yml` | After PyPI success | Publishes `server.json` metadata via OIDC |

### Prerequisites (One-Time Setup)

**PyPI Trusted Publisher:**
1. Visit https://pypi.org/manage/project/agent-mcp-gateway/settings/publishing/
2. Add publisher: Owner `roddutra`, Repository `agent-mcp-gateway`, Workflow `publish-pypi.yml`, Environment `pypi`

No API tokens needed (OIDC authentication).

### Troubleshooting Workflows

**PyPI fails:**
- Verify trusted publisher configured
- Check tag format is `v*.*.*`
- Verify `pyproject.toml` version matches tag

**GitHub Release fails:**
- Verify `CHANGELOG.md` has version section
- Check repository has `contents: write` permission

**MCP Registry fails:**
- Verify PyPI published successfully
- Check `server.json` versions match `pyproject.toml`
- Can manually trigger via Actions UI

**Rollback:**
```bash
git tag -d v0.1.2 && git push origin :refs/tags/v0.1.2
# Fix issues, recreate tag
git tag -a v0.1.2 -m "Release 0.1.2" && git push origin v0.1.2
```

## Manual Publishing (Testing Only)

### Build Package
```bash
rm -rf dist/
uv build --no-sources  # Excludes tests/docs
```

### Test on TestPyPI
```bash
uv publish --token $PYPI_TEST_TOKEN --publish-url https://test.pypi.org/legacy/
uvx --index-url https://test.pypi.org/simple/ agent-mcp-gateway@latest --version
```

### Publish to PyPI
```bash
uv publish --token $PYPI_TOKEN
```

Token setup: https://pypi.org/manage/account/ (use project-specific tokens).

## Post-Release Checklist

- [ ] All workflows completed: https://github.com/roddutra/agent-mcp-gateway/actions
- [ ] PyPI available: https://pypi.org/project/agent-mcp-gateway/
- [ ] MCP Registry: `curl https://registry.mcp.io/api/servers/io.github.roddutra/agent-mcp-gateway`
- [ ] GitHub release: https://github.com/roddutra/agent-mcp-gateway/releases
- [ ] Installation verified: `uvx agent-mcp-gateway@latest --version`

## Files Modified

| File | Change |
|------|--------|
| `pyproject.toml` | Version field |
| `uv.lock` | Package metadata |
| `server.json` | Root and package versions |
| `CHANGELOG.md` | New version section |

## Rollback Procedure

### Yank from PyPI
```bash
pip install twine
twine yank agent-mcp-gateway 0.1.1 --reason "Critical bug"
```

### Delete Tag
```bash
git tag -d v0.1.1
git push origin :refs/tags/v0.1.1
```

### Re-Release
Increment version (never reuse), follow release process.

## Common Issues

| Problem | Solution |
|---------|----------|
| "Version already exists" | `uv version --bump patch && uv lock && rm -rf dist/ && uv build --no-sources` |
| uv.lock version mismatch | Run `uv lock` after `uv version` |
| Token authentication failed | `echo $PYPI_TOKEN` to verify, `source ~/.zshrc` to reload |
| Old version cached | `uv cache clean` before installing |

## Related Documentation

- [MCP Registry Publishing](mcp-registry-publishing.md)
- [PyPI README Transformation](pypi-readme-transformation.md)
- [CHANGELOG.md](../CHANGELOG.md)
