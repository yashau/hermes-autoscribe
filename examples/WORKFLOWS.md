# Autoscribe Examples

## Example 1: Single Repo Project

```bash
# Initialize project
hermes autoscribe init my-app

# Add your main repo
hermes autoscribe add-repo my-app ~/Projects/my-app --name main

# Check status
hermes autoscribe status my-app
```

## Example 2: Multi-Repo Project

```bash
# Project with backend, frontend, and shared library
hermes autoscribe init fullstack-app

hermes autoscribe add-repo fullstack-app ~/Projects/backend --name backend
hermes autoscribe add-repo fullstack-app ~/Projects/frontend --name frontend
hermes autoscribe add-repo fullstack-app ~/Projects/shared --name shared-lib

# Search across all repos
# (Claude Code uses this via MCP)
# search_specs("authentication flow")  # searches backend + frontend + shared
```

## Example 3: Using with Claude Code

After setup, in Claude Code:

```
User: "Add payment processing to the backend"

Claude:
1. Calls search_specs("payment processing") via MCP
2. If found: reads the spec
3. If not found: "I'll create a payment processing spec first..."
4. Writes spec to .claude/specs/payment-processing.md
5. Implements the feature
6. On commit, git hook auto-indexes the new spec
```

## Example 4: Manual Reindex

```bash
# Reindex entire project
hermes autoscribe reindex my-app

# Reindex specific repo only
hermes autoscribe reindex my-app backend
```

## Example 5: Removing a Repo

```bash
hermes autoscribe remove-repo my-app backend
```

This removes the repo from the project and deletes its indexed vectors.

## Example 6: Delete Project

```bash
hermes autoscribe delete my-app
```

This removes all hooks, unregisters MCP server, and deletes vector data.
