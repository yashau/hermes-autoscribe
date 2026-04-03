# Using Hermes Autoscribe on Another Instance

This guide shows how to install and use the Hermes Autoscribe skill on any Hermes Agent instance.

## Prerequisites

- Hermes Agent installed and configured
- Python 3.9+
- Fireworks AI API key (for embeddings)

## Installation

### Method 1: Quick Install (Recommended)

```bash
# Clone directly to skills directory
git clone https://github.com/yashau/hermes-autoscribe.git ~/.hermes/skills/autoscribe

# Install dependencies
pip install qdrant-client openai mcp

# Enable in Hermes config
echo "enabled_skills:" >> ~/.hermes/config.yaml
echo "  - autoscribe" >> ~/.hermes/config.yaml
```

### Method 2: Using Install Script

```bash
# Clone anywhere
git clone https://github.com/yashau/hermes-autoscribe.git /tmp/hermes-autoscribe

# Run installer
cd /tmp/hermes-autoscribe
python3 install.py
```

### Method 3: Manual Setup

1. Clone to skills directory:
```bash
git clone https://github.com/yashau/hermes-autoscribe.git ~/.hermes/skills/autoscribe
```

2. Add `autoscribe` to `enabled_skills` in `~/.hermes/config.yaml`:
```yaml
enabled_skills:
  - autoscribe
```

3. Install dependencies:
```bash
pip install qdrant-client openai mcp
```

## Verification

Check installation:
```bash
python3 ~/.hermes/skills/autoscribe/install.py --check
```

Expected output:
```
Hermes Home: /root/.hermes
Skill Path: /root/.hermes/skills/autoscribe
Skill Installed: True
  server.py: OK
  cli.py: OK
  skill.yaml: OK
Dependencies: OK
FIREWORKS_API_KEY: SET
```

## First Use

```bash
# Set your API key if not already set
export FIREWORKS_API_KEY=your_key_here

# Create a project
hermes autoscribe init my-project

# Add a repo
hermes autoscribe add-repo my-project /path/to/your/repo --name main

# Check status
hermes autoscribe status my-project
```

## Troubleshooting

### "hermes: command not found"
Hermes CLI is not in your PATH. Either:
- Activate the virtual environment: `source ~/.hermes/hermes-agent/venv/bin/activate`
- Or use the full path: `~/.hermes/hermes-agent/venv/bin/hermes`

### "ImportError: No module named 'qdrant_client'"
Dependencies not installed. Run:
```bash
pip install qdrant-client openai mcp
```

### "FIREWORKS_API_KEY not set"
The skill requires a Fireworks AI API key. Get one at https://fireworks.ai and set it:
```bash
export FIREWORKS_API_KEY=your_key
```

### Skill not recognized by Hermes
Make sure `autoscribe` is in `enabled_skills` in `~/.hermes/config.yaml`:
```yaml
enabled_skills:
  - autoscribe
```

## Files Installed

After installation, you should have:

```
~/.hermes/skills/autoscribe/
├── server.py          # MCP server implementation
├── cli.py             # CLI commands
├── skill.yaml         # Skill metadata
├── SKILL.md           # Skill documentation
├── README.md          # This readme
├── install.py         # Installation script
└── examples/          # Usage examples
```

## Integration with Claude Code

Once the skill is set up and repos are added, Claude Code can use it via MCP:

1. MCP server auto-registers when you run `hermes autoscribe init`
2. Server starts on-demand when tools are called
3. Tools available:
   - `search_specs(query)` - Semantic search across specs
   - `get_spec(name)` - Get specific spec by name
   - `list_specs()` - List all specs
   - `trigger_reindex()` - Manual reindex

Claude Code will automatically:
- Search specs before implementing features
- Write missing specs (enforced by `.claude/rules/autodoc.md`)
- Update specs when implementation diverges

## Uninstall

```bash
# Remove skill directory
rm -rf ~/.hermes/skills/autoscribe

# Remove from config
grep -v "autoscribe" ~/.hermes/config.yaml > /tmp/config.yaml.tmp
mv /tmp/config.yaml.tmp ~/.hermes/config.yaml

# Clean up autoscribe projects (optional)
rm -rf ~/.hermes/autoscribe
```

## GitHub Repository

https://github.com/yashau/hermes-autoscribe

Clone and modify as needed for your own use.
