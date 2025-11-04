# PyPI README Transformation

## Problem

PyPI doesn't render relative paths in README.md correctly, causing broken images and links. GitHub-relative paths like `./docs/assets/diagram.svg` or `#quick-start` don't work on PyPI because it hosts the package separately from the repository.

## Solution

The `hatch-fancy-pypi-readme` plugin transforms the README.md at build time, converting relative paths to absolute GitHub URLs before uploading to PyPI.

## How It Works

When building the package, hatch applies regex substitutions defined in `pyproject.toml` to:
1. Convert relative image paths → absolute GitHub URLs
2. Convert relative doc links → absolute GitHub URLs
3. Convert anchor links → absolute GitHub URLs with anchors
4. Leave external URLs unchanged

**Key Point:** The GitHub README.md remains unchanged. Transformation only affects the version uploaded to PyPI.

## Configuration

All transformations are configured in `pyproject.toml` under:

```toml
[tool.hatch.metadata.hooks.fancy-pypi-readme]
content-type = "text/markdown"

[[tool.hatch.metadata.hooks.fancy-pypi-readme.substitutions]]
pattern = 'regex pattern here'
replacement = 'replacement with GitHub URL'
```

## Examples

**Before (GitHub-relative):**
```markdown
![Diagram](./docs/assets/diagram.svg)
[Configuration Guide](docs/configuration-guide.md)
[Quick Start](#quick-start)
```

**After (PyPI-absolute):**
```markdown
![Diagram](https://raw.githubusercontent.com/roddutra/agent-mcp-gateway/main/docs/assets/diagram.svg)
[Configuration Guide](https://github.com/roddutra/agent-mcp-gateway/blob/main/docs/configuration-guide.md)
[Quick Start](https://github.com/roddutra/agent-mcp-gateway#quick-start)
```

## Future Updates

If new relative path patterns are added to README.md, update the regex patterns in `pyproject.toml`. The transformation happens automatically during `uv build`.

## References

- hatch-fancy-pypi-readme: https://github.com/hynek/hatch-fancy-pypi-readme
- Configuration location: `pyproject.toml` lines 91-124
