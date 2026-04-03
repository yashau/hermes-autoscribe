# Hermes Autoscribe Skill

Self-evolving documentation with semantic search for any project. A portable, reusable skill for Hermes Agent.

## What It Does

Creates per-project semantic search systems:
- One MCP server per logical project
- Multiple repos per project (any directory structure)
- Git pre-commit hooks auto-index specs/docs on commit
- Claude Code queries the MCP server to discover specs before coding

## Quick Install

```bash
git clone https://github.com/yourname/hermes-autoscribe.git ~/.hermes/skills/autoscribe
```

Then add this to your `~/.hermes/config.yaml`:
```yaml
enabled_skills:
  - autoscribe
```

## Dependencies

```bash
pip install qdrant-client openai mcp
```

## Quick Start

```bash
# Initialize a new project
hermes autoscribe init my-project

# Add repos to the project
hermes autoscribe add-repo my-project /path/to/backend --name backend
hermes autoscribe add-repo my-project /path/to/frontend --name frontend

# Check status
hermes autoscribe status my-project
```

## Files

| File | Purpose |
|------|---------|
| `server.py` | MCP server - serves semantic search tools |
| `cli.py` | Hermes skill CLI - `hermes autoscribe` commands |
| `skill.yaml` | Skill metadata |
| `SKILL.md` | Skill documentation |
| `install.py` | Automated installation script |

## How It Works

1. **Project Config**: Stored in `~/.hermes/autoscribe/projects/<name>/config.json`
2. **Vector DB**: Local Qdrant at `~/.hermes/autoscribe/projects/<name>/qdrant_data/`
3. **Git Hooks**: Each repo gets `.git/hooks/pre-commit` that triggers reindex
4. **MCP Server**: Registered in Hermes config, starts on-demand when tools are called

## Claude Code Integration

Once set up, Claude Code automatically:
1. Searches `.claude/specs/` via `search_specs` MCP tool before implementing features
2. Writes missing specs (enforced by autodoc rule in `.claude/rules/autodoc.md`)
3. Updates specs when implementation diverges (self-healing)

## Environment Variables

- `FIREWORKS_API_KEY` - Required for embeddings (via Fireworks AI)

## License

MIT
