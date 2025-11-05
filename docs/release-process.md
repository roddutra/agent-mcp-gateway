# Release Process

This guide documents the complete workflow for version bumping, building, and publishing Agent MCP Gateway to PyPI.

## Quick Reference

**Automated (Recommended):**
```bash
# Version bump → Lock → Commit → Tag → Push (automation handles build + publish + release)
uv version --bump patch && uv lock && \
git add pyproject.toml uv.lock CHANGELOG.md && \
git commit -m "Bump version to $(uv version)" && \
git push origin main && \
git tag -a v$(uv version) -m "Release $(uv version)" && \
git push origin v$(uv version)
```

**Manual (For testing or troubleshooting):**
```bash
# Version bump → Lock → Build → Publish → Tag → Push
uv version --bump patch && uv lock && rm -rf dist/ && uv build --no-sources && \
uv publish --token $PYPI_TOKEN && git tag -a v$(uv version) -m "Release $(uv version)" && \
git push origin --tags
```

## Pre-Release Checklist

Before starting a release:

- [ ] All features/fixes merged to main branch
- [ ] Tests passing
- [ ] Documentation updated
- [ ] CHANGELOG.md ready with unreleased changes

## Step-by-Step Release Process

### 1. Version Bumping

Use `uv version` to update the version in `pyproject.toml`:

```bash
# Patch release (0.1.0 → 0.1.1) - bug fixes
uv version --bump patch

# Minor release (0.1.0 → 0.2.0) - new features (backward compatible)
uv version --bump minor

# Major release (0.1.0 → 1.0.0) - breaking changes
uv version --bump major

# Or set specific version
uv version 0.2.0
```

**Files Modified:**
- `pyproject.toml` - `version` field updated

### 2. Update Lockfile (CRITICAL)

Always run `uv lock` after version bump to sync `uv.lock` with `pyproject.toml`:

```bash
uv lock
```

**Why Critical:** The lockfile contains package metadata including version. Skipping this step causes version mismatches between source and lock state.

**Files Modified:**
- `uv.lock` - Package version and metadata updated

### 3. Update CHANGELOG.md

Add a new version section documenting changes:

```markdown
## [0.1.1] - 2025-11-05

### Fixed
- Bug fix description

### Added
- New feature description

### Changed
- Enhancement description

### Removed
- Deprecated feature removed
```

Follow [Keep a Changelog](https://keepachangelog.com/) format.

**Files Modified:**
- `CHANGELOG.md` - New version section added

### 4. Commit Version Bump

Commit all version-related changes:

```bash
git add pyproject.toml uv.lock CHANGELOG.md
git commit -m "Bump version to 0.1.1"
git push origin main
```

**Files Committed:**
- `pyproject.toml`
- `uv.lock`
- `CHANGELOG.md`

### 5. Build Package

Clean previous builds and create new distribution:

```bash
# Remove old builds
rm -rf dist/

# Build source distribution and wheel
uv build --no-sources
```

**Flag Explanation:**
- `--no-sources`: Exclude unnecessary source files (tests, docs) from distribution

**Output:**
- `dist/agent_mcp_gateway-X.Y.Z.tar.gz` - Source distribution
- `dist/agent_mcp_gateway-X.Y.Z-py3-none-any.whl` - Wheel (faster install)

### 6. Test on TestPyPI (Recommended)

Publish to TestPyPI first to verify everything works:

```bash
# Publish to test repository
uv publish --token $PYPI_TEST_TOKEN --publish-url https://test.pypi.org/legacy/

# Test installation (use --index-url for TestPyPI)
uvx --index-url https://test.pypi.org/simple/ agent-mcp-gateway@latest --version
```

**Setup TestPyPI Token:**
1. Create account at https://test.pypi.org/
2. Generate API token at https://test.pypi.org/manage/account/
3. Add to shell config: `export PYPI_TEST_TOKEN="pypi-..."`

### 7. Publish to PyPI

**Automated (Recommended):** Publishing is handled automatically by GitHub Actions when you push a tag (see Section 11). Skip this step and proceed to creating the git tag.

**Manual (For testing or troubleshooting):**

Publish to production PyPI:

```bash
# Ensure token is loaded
source ~/.zshrc  # or source ~/.bashrc

# Publish to PyPI
uv publish --token $PYPI_TOKEN
```

**PyPI Token Setup (Manual Only):**
1. Visit https://pypi.org/manage/account/
2. Create project-specific token for `agent-mcp-gateway`
3. Add to shell config: `export PYPI_TOKEN="pypi-..."`

**Security Note:** Use project-specific tokens (not account-wide) to limit damage if compromised.

**Trusted Publishing (Automated):** The GitHub Actions workflow uses OpenID Connect (OIDC) trusted publishing, which requires no API tokens. See Section 11 for setup instructions.

### 8. Create Git Tag

Tag the release in git:

```bash
# Create annotated tag
git tag -a v0.1.1 -m "Release version 0.1.1"

# Push tag to remote
git push origin v0.1.1

# Or push all tags
git push origin --tags
```

**Tag Format:** `vX.Y.Z` (e.g., `v0.1.1`, `v1.0.0`)

### 9. Verify Installation

Test that the package installs correctly:

```bash
# Clear cache to ensure fresh download
uv cache clean

# Test installation with uvx (no install)
uvx agent-mcp-gateway@latest --version

# Or test persistent installation
uv tool install agent-mcp-gateway
agent-mcp-gateway --version
```

### 10. Create GitHub Release

**Automated (Recommended):** GitHub releases are created automatically when you push a tag (see Section 11). The workflow extracts changelog content and adds installation instructions automatically.

**Manual (For testing or troubleshooting):**

Create a GitHub Release manually:

1. Visit: https://github.com/roddutra/agent-mcp-gateway/releases/new
2. Select tag: `v0.1.1`
3. Release title: `v0.1.1`
4. Description: Copy from `CHANGELOG.md` and add installation instructions
5. Attach dist files (optional):
   - `dist/agent_mcp_gateway-0.1.1.tar.gz`
   - `dist/agent_mcp_gateway-0.1.1-py3-none-any.whl`

**Benefits:**
- Users see release notes on GitHub
- Installation instructions visible on releases page
- Better discoverability

### 11. Automated Release via GitHub Actions

The project uses GitHub Actions for automated releases. When you push a version tag, two workflows run automatically:

#### Workflows

**1. PyPI Publishing** (`.github/workflows/publish-pypi.yml`)
- Triggers on tag push matching `v*.*.*` pattern
- Builds distributions with `uv build --no-sources`
- Publishes to PyPI using OpenID Connect (OIDC) trusted publishing
- No API tokens required

**2. GitHub Release** (`.github/workflows/release-github.yml`)
- Triggers on tag push matching `v*.*.*` pattern
- Extracts changelog section from `CHANGELOG.md` for the tagged version
- Creates GitHub release with:
  - Changelog content as release notes
  - Installation instructions (uvx and uv tool install commands)
  - Link to PyPI package page

#### Using Automated Releases

**Standard Workflow:**
```bash
# 1. Bump version and update lockfile
uv version --bump patch
uv lock

# 2. Update CHANGELOG.md with release notes for new version

# 3. Commit version changes
git add pyproject.toml uv.lock CHANGELOG.md
git commit -m "Bump version to $(uv version)"
git push origin main

# 4. Create and push tag - this triggers automation
git tag -a v$(uv version) -m "Release $(uv version)"
git push origin v$(uv version)

# 5. Monitor workflows at https://github.com/roddutra/agent-mcp-gateway/actions
```

#### Prerequisites

**PyPI Trusted Publisher Setup (One-time):**
1. Visit https://pypi.org/manage/project/agent-mcp-gateway/settings/publishing/
2. Add trusted publisher with these settings:
   - **Owner:** `roddutra`
   - **Repository name:** `agent-mcp-gateway`
   - **Workflow name:** `publish-pypi.yml`
   - **Environment name:** `pypi`

**GitHub Environment (Optional):**
- Create a "pypi" environment in repository settings for additional protection
- No secrets needed (uses OIDC)

#### Monitoring Workflows

After pushing a tag:
1. Visit https://github.com/roddutra/agent-mcp-gateway/actions
2. Check "Publish to PyPI" workflow status
3. Check "Create GitHub Release" workflow status
4. Both workflows run independently and can succeed/fail separately

#### Troubleshooting

**PyPI Publish Fails:**
- Verify trusted publisher configured correctly at PyPI
- Check workflow logs for authentication errors
- Ensure tag format matches `v*.*.*` (e.g., `v0.1.2`, not `0.1.2`)
- Verify version in `pyproject.toml` matches tag

**GitHub Release Fails:**
- Check that `CHANGELOG.md` has a section for the version being released
- Verify tag exists: `git tag -l`
- Check workflow permissions in repository settings (needs `contents: write`)

**Both Workflows Fail:**
- Verify tag was pushed: `git push origin --tags` or `git push origin v0.1.2`
- Check Actions tab for detailed error messages
- Tag format must be `v*.*.*` to trigger workflows

**Rollback:**
If both workflows fail, delete the tag and retry:
```bash
# Delete local and remote tag
git tag -d v0.1.2
git push origin :refs/tags/v0.1.2

# Fix issues, then recreate tag
git tag -a v0.1.2 -m "Release 0.1.2"
git push origin v0.1.2
```

#### Testing Workflows

**Test with a pre-release tag:**
```bash
# Create test tag
git tag -a v0.1.2-test -m "Test release automation"
git push origin v0.1.2-test

# Monitor workflows, verify publish and release creation

# Clean up test artifacts
gh release delete v0.1.2-test --yes
git tag -d v0.1.2-test
git push origin :refs/tags/v0.1.2-test
```

## Post-Release Checklist

After release:

- [ ] Both GitHub Actions workflows completed successfully
- [ ] Package available on PyPI: https://pypi.org/project/agent-mcp-gateway/
- [ ] GitHub Release created with changelog: https://github.com/roddutra/agent-mcp-gateway/releases
- [ ] Installation verified with `uvx agent-mcp-gateway@latest --version`
- [ ] Git tag visible on GitHub: https://github.com/roddutra/agent-mcp-gateway/tags
- [ ] Announce release (Twitter, Discord, etc.)

## Files Modified During Release

Summary of all files that change during a release:

| File | Change | Step |
|------|--------|------|
| `pyproject.toml` | Version field updated | 1. Version Bump |
| `uv.lock` | Package metadata synced | 2. Update Lockfile |
| `CHANGELOG.md` | New version section added | 3. Update Changelog |
| `dist/*` | Build artifacts created | 5. Build Package |

## Rollback Procedure

If a release has critical issues:

### 1. Yank from PyPI

```bash
# Yank version (marks as unavailable but doesn't delete)
pip install twine
twine yank agent-mcp-gateway 0.1.1 --reason "Critical bug in X"
```

**Note:** Yanked versions remain visible but won't be installed by default.

### 2. Delete Git Tag

```bash
# Delete local tag
git tag -d v0.1.1

# Delete remote tag
git push origin :refs/tags/v0.1.1
```

### 3. Fix and Re-Release

Increment version (e.g., `0.1.1` → `0.1.2`) and follow release process again. Never reuse version numbers.

## Troubleshooting

### "Version already exists" Error

**Problem:** Trying to publish a version that already exists on PyPI.

**Solution:** Bump version and rebuild:
```bash
uv version --bump patch
uv lock
rm -rf dist/
uv build --no-sources
```

### uv.lock Version Mismatch

**Problem:** `uv.lock` shows old version after version bump.

**Solution:** Always run `uv lock` after `uv version`:
```bash
uv lock
```

### Token Authentication Failed

**Problem:** PyPI rejects token.

**Solution:** Verify token is loaded and valid:
```bash
echo $PYPI_TOKEN  # Should show pypi-...
source ~/.zshrc   # Reload shell config
```

### Installation Verification Fails

**Problem:** `uvx agent-mcp-gateway@latest` shows old version.

**Solution:** Clear uv cache:
```bash
uv cache clean
uvx agent-mcp-gateway@latest --version
```

## Semantic Versioning

Follow [Semantic Versioning](https://semver.org/):

- **MAJOR (X.0.0)**: Breaking changes (incompatible API changes)
- **MINOR (0.X.0)**: New features (backward compatible)
- **PATCH (0.0.X)**: Bug fixes (backward compatible)

**Pre-release versions:**
- Alpha: `0.1.0-alpha.1`
- Beta: `0.1.0-beta.1`
- RC: `0.1.0-rc.1`

## Automated Releases

This project uses GitHub Actions for automated releases. See **Section 11: Automated Release via GitHub Actions** for complete details.

**Implemented Workflows:**
- `.github/workflows/publish-pypi.yml` - Automated PyPI publishing with trusted publishing (no tokens)
- `.github/workflows/release-github.yml` - Automated GitHub release creation with changelog extraction

**Benefits:**
- Consistent releases across PyPI and GitHub
- No manual token management (OIDC trusted publishing)
- Automatic changelog extraction and formatting
- Reduced manual errors

## Related Documentation

- [PyPI README Transformation](pypi-readme-transformation.md) - Build-time README fixes for PyPI
- [CHANGELOG.md](../CHANGELOG.md) - Release history
- [PyPI Package Page](https://pypi.org/project/agent-mcp-gateway/) - Published package
