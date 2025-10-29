# MCP tool definitions in Claude Code's System Prompt

*(as of October/2025)*

Although it may not be the most reliable method, when asked [Claude Code itself explained](#claude-codes-explanation) that the JSON tool definitions are added directly to a `<functions>` section at the very beginning of it's system prompt, as well as having a `MCP Server Instructions` section:

```markdown
<functions>
  <function>{...json schema for tool 1...}</function>
  <function>{...json schema for tool 2...}</function>
  <function>{...json schema for tool 3...}</function>
  ...
</functions>

...

# MCP Server Instructions

The following MCP servers have provided instructions for how to use their tools and resources:

## context7
Use this server to retrieve up-to-date documentation and code examples for any library.

## brave-search
Use this server to search the Web for various types of data via the Brave Search API.

...
```

Each <function> element contains a JSON object with the tool's name, description, and parameters (which is the JSON schema defining the tool's arguments).

See the [`claude-code-tool-definitions.json`](/docs/insights/cc-system-prompt-tools-sample.json) file provided by Claude Code from its system prompt for the actual tool schemas from a sample session with the following 3 MCPs configured:
- `fetch`
- `context7`
- `brave-search`

## TODO's

- [ ] Proxy and intercept Claude Code's API requests and inspect the actual system prompt from the network calls
  - *Update: "Yifan - Beyond the Hype" has done exactly this but his system prompt doesn't seem to include the MCP tool definitions, although it mentions a few `mcp__puppeteer__*` tools - sources: [YouTube video](https://www.youtube.com/watch?v=i0P56Pm1Q3U), [blog](https://beyondthehype.dev/p/inside-claude-code-prompt-engineering-masterpiece), [gist](https://gist.github.com/yifanzz/2b89303adde9a00e96e61a2d4b31016a)*
  - *Update: "OutSight AI" seems to have done a similar thing, but it also doesn't seem to include MCP tool definitions in the system prompt - source: [Blog](https://medium.com/@outsightai/peeking-under-the-hood-of-claude-code-70f5a94a9a62)*
- [ ] Experiment with different servers using different protocols & auth methods

## Claude Code's Explanation

Here is an extract from a Claude Code session (October/2025) and what Claude had to say when asked how and where it knows about the tools and their definitions:

```
⏺ From my system prompt, here's the exact MCP server information I receive:

  # MCP Server Instructions

  The following MCP servers have provided instructions for how to use their tools and resources:

  ## context7
  Use this server to retrieve up-to-date documentation and code examples for any library.

  ## brave-search
  Use this server to search the Web for various types of data via the Brave Search API.

  That's all the MCP-specific instructions I receive. The actual tool definitions (function schemas) are provided in a <functions> section at the beginning of my system prompt as individual function definitions like:

  - mcp__fetch__fetch
  - mcp__context7__resolve-library-id
  - mcp__context7__get-library-docs
  - mcp__ide__getDiagnostics
  - mcp__ide__executeCode
  - mcp__brave-search__brave_web_search
  - mcp__brave-search__brave_local_search
  - mcp__brave-search__brave_video_search
  - mcp__brave-search__brave_image_search
  - mcp__brave-search__brave_news_search
  - mcp__brave-search__brave_summarizer

  Note that fetch and ide servers don't have entries in the MCP Server Instructions section, but their tools are available in my function definitions.
```

```
> Earlier you said "The actual tool definitions (function schemas) are provided in a <functions> section at the beginning of my system prompt as individual function definitions". Is this where the json tool definitions you provided earlier is provided to you, inside this <functions> section in your system prompt? Or is that somewhere else?

⏺ Yes, exactly! The JSON tool definitions I provided earlier come directly from a <functions> section at the very beginning of my system prompt.

  The structure looks like this:

  <functions>
  <function>{...json schema for tool 1...}</function>
  <function>{...json schema for tool 2...}</function>
  <function>{...json schema for tool 3...}</function>
  ...
  </functions>

  Each <function> element contains a JSON object with the tool's name, description, and parameters (which is the JSON schema defining the tool's arguments).

  So when I extracted those tool definitions for you, I was pulling them directly from this <functions> section. That's how I "know" which tools are available - they're explicitly defined upfront in my system prompt via this structured format.

  The /context command output you just showed gives a nice summary view (showing token counts per tool), but the actual detailed schemas with all the parameters, types, enums, descriptions, etc. that I provided to you come from that <functions> section.
```