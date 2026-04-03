#!/usr/bin/env python3
"""
Autoscribe Skill
Hermes skill for managing per-project semantic search across multiple repos.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

# Hermes constants
HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
SKILL_DIR = HERMES_HOME / "skills" / "autoscribe"
PROJECTS_DIR = HERMES_HOME / "autoscribe" / "projects"

# Templates
AUTODOC_TEMPLATE = '''---
priority: high
---
# Auto-Documentation & Gap-Filling Rule

## 1. The Gap-Check
Before implementing anything:
- Search `.claude/specs/` using `search_specs` MCP tool
- If no matching spec exists → STOP and write it first

## 2. The Documentation Format
When creating a spec in `.claude/specs/[feature-name].md`:
```yaml
---
status: draft | approved | deprecated
---
# Feature Name

## Purpose
What this feature does

## Interface
APIs, inputs, outputs

## Logic
Business rules and constraints

## Dependencies
Related specs (cross-repo links)
```

## 3. Self-Healing
If answering a question reveals the spec is wrong or missing information,
update the spec immediately after answering.
'''

ITERATE_TEMPLATE = '''# Iterate Skill

For any feature implementation:

1. **Discover**: `search_specs(query="[feature name]")`
2. **Ground**: Read the spec if found
3. **Gap**: If no spec, write it first (see autodoc rule)
4. **Draft**: Propose changes
5. **Execute**: Implement
6. **Sync**: Update spec if the implementation diverged

## Cross-Repo Search
To find related specs across repos:
- `search_specs(query="payment flow")` - searches all repos
- `search_specs(query="payment", repo="backend")` - specific repo
'''


def ensure_dirs():
    """Ensure required directories exist."""
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)


def get_project_path(project_name: str) -> Path:
    """Get project configuration path."""
    return PROJECTS_DIR / project_name


def get_project_config_path(project_name: str) -> Path:
    """Get project config.json path."""
    return get_project_path(project_name) / "config.json"


def load_project_config(project_name: str) -> Optional[dict]:
    """Load project configuration."""
    config_path = get_project_config_path(project_name)
    if config_path.exists():
        with open(config_path) as f:
            return json.load(f)
    return None


def save_project_config(project_name: str, config: dict):
    """Save project configuration."""
    project_path = get_project_path(project_name)
    project_path.mkdir(parents=True, exist_ok=True)
    
    config_path = project_path / "config.json"
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)


def init_project(project_name: str, fireworks_api_key: Optional[str] = None):
    """Initialize a new context-bridge project."""
    ensure_dirs()
    
    project_path = get_project_path(project_name)
    if project_path.exists():
        print(f"Project '{project_name}' already exists.")
        return False
    
    # Create project structure
    project_path.mkdir(parents=True, exist_ok=True)
    (project_path / "qdrant_data").mkdir(exist_ok=True)
    
    # Get API key
    if not fireworks_api_key:
        fireworks_api_key = os.environ.get("FIREWORKS_API_KEY")
        if not fireworks_api_key:
            print("Error: FIREWORKS_API_KEY not set in environment.")
            print("Please set it or pass --fireworks-api-key")
            return False
    
    # Create config
    config = {
        "project_name": project_name,
        "repos": {},
        "embedding": {
            "provider": "fireworks",
            "model": "nomic-ai/nomic-embed-text-v1",
            "base_url": "https://api.fireworks.ai/inference/v1",
            "api_key": fireworks_api_key
        }
    }
    
    save_project_config(project_name, config)
    
    # Register MCP server in Hermes config
    register_mcp_server(project_name)
    
    print(f"Initialized autoscribe project: {project_name}")
    print(f"Config: {project_path / 'config.json'}")
    print(f"\nNext steps:")
    print(f"  hermes autoscribe add-repo {project_name} /path/to/repo --name my-repo")
    return True


def register_mcp_server(project_name: str):
    """Register the MCP server in Hermes config."""
    from hermes_cli.config import load_config, save_config
    
    hermes_config = load_config()
    if "mcp_servers" not in hermes_config:
        hermes_config["mcp_servers"] = {}
    
    server_id = f"autoscribe-{project_name}"
    config_path = get_project_config_path(project_name)
    server_script = SKILL_DIR / "server.py"
    
    hermes_config["mcp_servers"][server_id] = {
        "command": "python",
        "args": [str(server_script), "--config", str(config_path)],
        "transport": "stdio"
    }
    
    save_config(hermes_config)
    print(f"Registered MCP server: {server_id}")


def unregister_mcp_server(project_name: str):
    """Unregister the MCP server from Hermes config."""
    from hermes_cli.config import load_config, save_config
    
    hermes_config = load_config()
    server_id = f"autoscribe-{project_name}"
    
    if "mcp_servers" in hermes_config and server_id in hermes_config["mcp_servers"]:
        del hermes_config["mcp_servers"][server_id]
        save_config(hermes_config)
        print(f"Unregistered MCP server: {server_id}")


def add_repo(project_name: str, repo_path: str, repo_name: str):
    """Add a repo to a project."""
    config = load_project_config(project_name)
    if not config:
        print(f"Project '{project_name}' not found.")
        return False
    
    repo_path = Path(repo_path).resolve()
    if not repo_path.exists():
        print(f"Repo path does not exist: {repo_path}")
        return False
    
    if not (repo_path / ".git").exists():
        print(f"Warning: {repo_path} does not appear to be a git repository")
        response = input("Continue anyway? [y/N]: ")
        if response.lower() != 'y':
            return False
    
    # Add to config
    config["repos"][repo_name] = {
        "path": str(repo_path),
        "include": [
            ".claude/specs/**/*.md",
            ".claude/skills/**/*.md",
            "docs/**/*.md",
            "README.md",
            "CHANGELOG.md"
        ]
    }
    
    save_project_config(project_name, config)
    
    # Create .claude structure in repo
    claude_dir = repo_path / ".claude"
    claude_dir.mkdir(exist_ok=True)
    (claude_dir / "specs").mkdir(exist_ok=True)
    (claude_dir / "skills").mkdir(exist_ok=True)
    (claude_dir / "rules").mkdir(exist_ok=True)
    
    # Write templates
    (claude_dir / "rules" / "autodoc.md").write_text(AUTODOC_TEMPLATE)
    (claude_dir / "skills" / "iterate.md").write_text(ITERATE_TEMPLATE)
    
    # Install git hook
    install_git_hook(project_name, repo_name, repo_path)
    
    # Trigger initial index
    print(f"Triggering initial index for {repo_name}...")
    trigger_index(project_name, repo_name)
    
    print(f"Added repo '{repo_name}' to project '{project_name}'")
    print(f"Claude Code templates installed in {repo_path / '.claude/'}")
    return True


def install_git_hook(project_name: str, repo_name: str, repo_path: Path):
    """Install pre-commit hook in a repo."""
    hooks_dir = repo_path / ".git" / "hooks"
    if not hooks_dir.exists():
        print(f"Warning: No .git/hooks directory found at {repo_path}")
        return
    
    hook_path = hooks_dir / "pre-commit"
    
    # Create hook script
    hook_script = f'''#!/bin/bash
# Context Bridge pre-commit hook for {repo_name} in project {project_name}
# Auto-generated - do not modify manually

REPO_NAME="{repo_name}"
PROJECT_NAME="{project_name}"
CONFIG_PATH="{get_project_config_path(project_name)}"
SERVER_SCRIPT="{SKILL_DIR / 'server.py'}"

# Get staged files in .claude/
STAGED_SPECS=$(git diff --cached --name-only | grep -E "^\\.claude/|^docs/|^README\\.md$|^CHANGELOG\\.md$" || true)

if [ -n "$STAGED_SPECS" ]; then
    echo "Updating autoscribe index..."
    
    # Call indexer via Python
    echo "$STAGED_SPECS" | python3 "{SKILL_DIR / 'cli.py'}" _index-stdin {project_name} {repo_name} 2>/dev/null || echo "Warning: Index update may have failed"
fi

exit 0
'''
    
    # Check if hook already exists
    if hook_path.exists():
        existing = hook_path.read_text()
        if "Autoscribe" in existing:
            print(f"Updating existing autoscribe hook at {hook_path}")
        else:
            print(f"Backing up existing pre-commit hook to {hook_path}.backup")
            hook_path.rename(hook_path.with_suffix('.backup'))
    
    hook_path.write_text(hook_script)
    hook_path.chmod(0o755)
    
    print(f"Installed pre-commit hook at {hook_path}")


def index_stdin(project_name: str, repo_name: str):
    """Index files passed via stdin (for git hook)."""
    import sys
    files = [f.strip() for f in sys.stdin if f.strip()]
    if files:
        trigger_index(project_name, repo_name, files)


def trigger_index(project_name: str, repo_name: str, files: Optional[list] = None):
    """Trigger indexing of a repo."""
    try:
        from server import AutoscribeServer
        
        config_path = get_project_config_path(project_name)
        server = AutoscribeServer(config_path)
        
        result = server.index_repo(repo_name, files)
        print(f"Indexed {result['indexed']} chunks from {repo_name}")
        if result.get('errors'):
            for error in result['errors'][:5]:  # Show first 5
                print(f"  Error: {error}")
    except Exception as e:
        print(f"Failed to index {repo_name}: {e}")


def remove_repo(project_name: str, repo_name: str):
    """Remove a repo from a project."""
    config = load_project_config(project_name)
    if not config:
        print(f"Project '{project_name}' not found.")
        return False
    
    if repo_name not in config["repos"]:
        print(f"Repo '{repo_name}' not found in project '{project_name}'")
        return False
    
    repo_path = Path(config["repos"][repo_name]["path"])
    
    # Remove from config
    del config["repos"][repo_name]
    save_project_config(project_name, config)
    
    # Remove git hook
    hook_path = repo_path / ".git" / "hooks" / "pre-commit"
    if hook_path.exists() and "Autoscribe" in hook_path.read_text():
        hook_path.unlink()
        print(f"Removed pre-commit hook from {repo_path}")
    
    # Delete vectors for this repo
    try:
        from server import AutoscribeServer
        server = AutoscribeServer(get_project_config_path(project_name))
        server._delete_repo_from_index(repo_name)
        print(f"Deleted indexed vectors for {repo_name}")
    except Exception as e:
        print(f"Warning: Could not delete vectors: {e}")
    
    print(f"Removed repo '{repo_name}' from project '{project_name}'")
    return True


def status(project_name: str):
    """Show project status."""
    config = load_project_config(project_name)
    if not config:
        print(f"Project '{project_name}' not found.")
        return False
    
    print(f"\nProject: {project_name}")
    print(f"Config: {get_project_config_path(project_name)}")
    print(f"\nRepos ({len(config['repos'])}):")
    
    for name, info in config["repos"].items():
        print(f"  - {name}: {info['path']}")
        # Check if indexed
        hook_path = Path(info["path"]) / ".git" / "hooks" / "pre-commit"
        if hook_path.exists() and "Autoscribe" in hook_path.read_text():
            print(f"    Hook: installed")
        else:
            print(f"    Hook: NOT installed")
    
    # Get vector counts
    try:
        from server import AutoscribeServer
        server = AutoscribeServer(get_project_config_path(project_name))
        status_result = server.status()
        status_data = json.loads(status_result)
        
        print(f"\nVector Stats:")
        print(f"  Total vectors: {status_data.get('total_vectors', 0)}")
        for repo, count in status_data.get('repos', {}).items():
            print(f"  - {repo}: {count} chunks")
    except Exception as e:
        print(f"\nCould not get vector stats: {e}")
    
    return True


def reindex(project_name: str, repo_name: Optional[str] = None):
    """Manually trigger reindex."""
    config = load_project_config(project_name)
    if not config:
        print(f"Project '{project_name}' not found.")
        return False
    
    if repo_name:
        if repo_name not in config["repos"]:
            print(f"Repo '{repo_name}' not found in project '{project_name}'")
            return False
        print(f"Reindexing {repo_name}...")
        trigger_index(project_name, repo_name)
    else:
        print(f"Reindexing all repos in project '{project_name}'...")
        for name in config["repos"].keys():
            print(f"\nReindexing {name}...")
            trigger_index(project_name, name)
    
    return True


def delete_project(project_name: str):
    """Delete a project entirely."""
    config = load_project_config(project_name)
    if not config:
        print(f"Project '{project_name}' not found.")
        return False
    
    # Remove all git hooks first
    for repo_name, repo_info in config.get("repos", {}).items():
        repo_path = Path(repo_info["path"])
        hook_path = repo_path / ".git" / "hooks" / "pre-commit"
        if hook_path.exists() and "Context Bridge" in hook_path.read_text():
            hook_path.unlink()
            print(f"Removed hook from {repo_name}")
    
    # Unregister MCP server
    unregister_mcp_server(project_name)
    
    # Delete project directory
    project_path = get_project_path(project_name)
    import shutil
    shutil.rmtree(project_path)
    
    print(f"Deleted project '{project_name}'")
    return True


def main():
    parser = argparse.ArgumentParser(description="Autoscribe - Semantic search for project specs")
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # init
    init_parser = subparsers.add_parser("init", help="Initialize a new autoscribe project")
    init_parser.add_argument("project", help="Project name")
    init_parser.add_argument("--fireworks-api-key", help="Fireworks API key (or set FIREWORKS_API_KEY env)")
    
    # add-repo
    add_parser = subparsers.add_parser("add-repo", help="Add a repo to a project")
    add_parser.add_argument("project", help="Project name")
    add_parser.add_argument("path", help="Path to repo")
    add_parser.add_argument("--name", required=True, help="Repo name (unique within project)")
    
    # remove-repo
    remove_parser = subparsers.add_parser("remove-repo", help="Remove a repo from a project")
    remove_parser.add_argument("project", help="Project name")
    remove_parser.add_argument("name", help="Repo name")
    
    # status
    status_parser = subparsers.add_parser("status", help="Show project status")
    status_parser.add_argument("project", help="Project name")
    
    # reindex
    reindex_parser = subparsers.add_parser("reindex", help="Manually trigger reindex")
    reindex_parser.add_argument("project", help="Project name")
    reindex_parser.add_argument("repo", nargs="?", help="Specific repo to reindex (optional)")
    
    # delete
    delete_parser = subparsers.add_parser("delete", help="Delete a project entirely")
    delete_parser.add_argument("project", help="Project name")
    
    # _index-stdin (internal use by git hook)
    index_stdin_parser = subparsers.add_parser("_index-stdin", help=argparse.SUPPRESS)
    index_stdin_parser.add_argument("project", help="Project name")
    index_stdin_parser.add_argument("repo", help="Repo name")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    if args.command == "init":
        init_project(args.project, args.fireworks_api_key)
    elif args.command == "add-repo":
        add_repo(args.project, args.path, args.name)
    elif args.command == "remove-repo":
        remove_repo(args.project, args.name)
    elif args.command == "status":
        status(args.project)
    elif args.command == "reindex":
        reindex(args.project, args.repo)
    elif args.command == "delete":
        confirm = input(f"Are you sure you want to delete project '{args.project}'? [yes/N]: ")
        if confirm == "yes":
            delete_project(args.project)
        else:
            print("Cancelled.")
    elif args.command == "_index-stdin":
        index_stdin(args.project, args.repo)


if __name__ == "__main__":
    main()
