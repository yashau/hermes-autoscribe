---
name: autoscribe
description: Set up self-evolving semantic documentation search for projects with multiple repos
category: software-development
version: 1.0.0
tags: [mcp, semantic-search, documentation, claude-code, vector-db]
---

# Autoscribe

A portable system for self-evolving, semantically-searchable documentation across multiple repositories.

## What It Does

Autoscribe creates a per-project semantic search infrastructure:

1. **MCP Server** - Provides semantic search tools that Claude Code can query
2. **Vector Database** - Local Qdrant instance storing embeddings of specs and docs
3. **Git Integration** - Pre-commit hooks auto-index documentation on every commit
4. **Fireworks Embeddings** - Uses Kimi/Fireworks API for document embeddings (OpenAI-compatible)
5. **Multi-Repo Support** - One project can span multiple git repositories anywhere on the filesystem

## Architecture

```
~/.hermes/autoscribe/projects/<project>/
├── config.json           # Project config with repo mappings
├── qdrant_data/          # Local vector database
└── server.sock           # MCP server socket

Each repo gets:
├── .claude/
│   ├── rules/autodoc.md      # Forces spec-first workflow
│   ├── skills/iterate.md     # Search/discovery instructions for Claude
│   └── specs/                # Where specs live (Claude creates these)
└── .git/hooks/pre-commit     # Auto-indexes on commit
```

## Quick Start

```bash
# 1. Initialize a project (needs FIREWORKS_API_KEY in env or --fireworks-api-key)
hermes autoscribe init my-project

# 2. Add repositories (can be anywhere)
hermes autoscribe add-repo my-project /path/to/backend --name backend
hermes autoscribe add-repo my-project /path/to/frontend --name frontend
hermes autoscribe add-repo my-project /path/to/shared-lib --name shared

# 3. Check status
hermes autoscribe status my-project

# 4. Manual reindex if needed
hermes autoscribe reindex my-project backend
```

## For Claude Code Users

Once set up, Claude Code automatically:

1. **Before coding**: Searches `.claude/specs/` via MCP to find existing specs
2. **Gap detection**: If no spec exists, the `autodoc.md` rule forces Claude to write one first
3. **During coding**: Can cross-reference specs across all project repos
4. **After coding**: Self-heals documentation if implementation diverged from spec

### Example Claude Code workflow:

```
User: "Implement the payment flow"

Claude internally:
1. Calls search_specs("payment flow") → finds payment-gateway.md (backend) + checkout-ui.md (frontend)
2. Reads both specs
3. Implements the feature
4. If the implementation revealed the spec was wrong, updates the spec
```

## Commands

| Command | Description |
|---------|-------------|
| `hermes autoscribe init <project>` | Create new project |
| `hermes autoscribe add-repo <project> <path> --name <name>` | Add a repo to project |
| `hermes autoscribe remove-repo <project> <name>` | Remove repo from project |
| `hermes autoscribe status <project>` | Show indexing status per repo |
| `hermes autoscribe reindex <project> [repo]` | Manual full/partial reindex |
| `hermes autoscribe delete <project>` | Delete project entirely |

## Configuration

Project config at `~/.hermes/autoscribe/projects/<project>/config.json`:

```json
{
  "project_name": "my-project",
  "repos": {
    "backend": {
      "path": "/path/to/backend",
      "include": [
        ".claude/specs/**/*.md",
        "docs/**/*.md",
        "README.md"
      ]
    }
  },
  "embedding": {
    "provider": "fireworks",
    "model": "nomic-ai/nomic-embed-text-v1",
    "base_url": "https://api.fireworks.ai/inference/v1",
    "api_key": "fw-..."
  }
}
```

## MCP Tools Available to Claude Code

Once the MCP server is running (automatic after `init`), these tools are available:

- `search_specs(query, repo=None, top_k=5)` - Semantic search across all project specs
- `get_spec(feature_name)` - Exact lookup by filename (without .md extension)
- `list_specs()` - List all indexed specs
- `trigger_reindex()` - Manual reindex trigger

## Design Decisions

**Why git pre-commit hooks vs cron?**
- Docs only change on commits, so indexing at commit boundary is sufficient
- Simpler than file watchers, more precise than cron
- Never blocks commit (hook exits 0 even if indexing fails)

**Why per-project servers vs one global server?**
- Project isolation prevents cross-project pollution
- Different projects can have different embedding models/settings
- Easier to delete/move projects independently

**Why Fireworks/Kimi for embeddings?**
- User already has credits and API keys
- OpenAI-compatible endpoint requires no special handling
- `nomic-embed-text-v1` is high quality for code/docs

**Why not index source code?**
- Specs are the "source of truth" - code is implementation
- Forces Claude to think in terms of documented intent
- Smaller, more manageable index

## Troubleshooting

**MCP server not connecting:**
```bash
# Check if server is registered in Hermes config
hermes config | grep autoscribe

# Re-register
hermes autoscribe status <project>
```

**Git hook not firing:**
```bash
# Check hook exists and is executable
ls -la .git/hooks/pre-commit

# Manually test indexing
hermes autoscribe reindex <project> <repo>
```

**Embeddings failing:**
- Verify `FIREWORKS_API_KEY` is set
- Check key has access to `nomic-ai/nomic-embed-text-v1`
- Look at `~/.hermes/autoscribe/projects/<project>/config.json` for correct API key

## Requirements

- Python 3.8+
- `qdrant-client` (pip install qdrant-client)
- `fastmcp` (pip install fastmcp)
- Fireworks API key with access to embedding models
- Git (for pre-commit hooks)

## Files

- `server.py` - MCP server implementation
- `cli.py` - Hermes CLI integration
- `SKILL.md` - This documentation
