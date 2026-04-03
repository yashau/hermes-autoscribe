#!/usr/bin/env python3
"""
Hermes Autoscribe Skill - Automated Installer

Usage:
    python3 install.py                    # Install to default location
    python3 install.py --path /custom/dir   # Install to custom location
    python3 install.py --check             # Check if already installed
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

SKILL_NAME = "autoscribe"
DEFAULT_HERMES_HOME = Path.home() / ".hermes"

REQUIRED_PACKAGES = [
    "qdrant-client",
    "openai>=1.0.0",
    "mcp>=1.0.0",
]


def get_hermes_home():
    """Get HERMES_HOME from env or default."""
    hermes_home = os.environ.get("HERMES_HOME")
    if hermes_home:
        return Path(hermes_home)
    return DEFAULT_HERMES_HOME


def check_dependencies():
    """Check if required packages are installed."""
    missing = []
    for pkg in REQUIRED_PACKAGES:
        pkg_name = pkg.split(">=")[0].split("==")[0]
        try:
            __import__(pkg_name.replace("-", "_"))
        except ImportError:
            missing.append(pkg)
    return missing


def install_dependencies(missing):
    """Install missing dependencies."""
    print(f"Installing {len(missing)} package(s)...")
    cmd = [sys.executable, "-m", "pip", "install"] + missing
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error installing packages: {result.stderr}")
        return False
    print("Dependencies installed successfully.")
    return True


def check_fireworks_key():
    """Check if Fireworks API key is set."""
    return os.environ.get("FIREWORKS_API_KEY") is not None


def install_skill(install_path=None):
    """Install the skill to the Hermes skills directory."""
    hermes_home = get_hermes_home()
    
    if install_path:
        target = Path(install_path)
    else:
        target = hermes_home / "skills" / SKILL_NAME
    
    # Create target directory
    target.mkdir(parents=True, exist_ok=True)
    
    # Copy files
    source = Path(__file__).parent
    files_to_copy = ["server.py", "cli.py", "SKILL.md", "skill.yaml", "README.md"]
    
    for file in files_to_copy:
        src = source / file
        if src.exists():
            dst = target / file
            dst.write_bytes(src.read_bytes())
            print(f"  Copied {file}")
    
    # Make scripts executable
    (target / "server.py").chmod(0o755)
    (target / "cli.py").chmod(0o755)
    
    print(f"\nInstalled to: {target}")
    return True


def enable_skill_in_config():
    """Enable the skill in Hermes config."""
    hermes_home = get_hermes_home()
    config_path = hermes_home / "config.yaml"
    
    if not config_path.exists():
        print(f"Warning: Hermes config not found at {config_path}")
        print("Please manually add 'autoscribe' to enabled_skills in config.yaml")
        return False
    
    try:
        import yaml
        
        with open(config_path) as f:
            config = yaml.safe_load(f) or {}
        
        if "enabled_skills" not in config:
            config["enabled_skills"] = []
        
        if SKILL_NAME not in config["enabled_skills"]:
            config["enabled_skills"].append(SKILL_NAME)
            
            with open(config_path, 'w') as f:
                yaml.dump(config, f, default_flow_style=False)
            
            print(f"Enabled '{SKILL_NAME}' in Hermes config")
        else:
            print(f"'{SKILL_NAME}' already enabled in config")
        
        return True
        
    except ImportError:
        print("PyYAML not installed, please manually edit config.yaml")
        return False
    except Exception as e:
        print(f"Could not update config: {e}")
        return False


def check_status():
    """Check installation status."""
    hermes_home = get_hermes_home()
    skill_path = hermes_home / "skills" / SKILL_NAME
    
    print(f"Hermes Home: {hermes_home}")
    print(f"Skill Path: {skill_path}")
    print(f"Skill Installed: {skill_path.exists()}")
    
    # Check files
    if skill_path.exists():
        required = ["server.py", "cli.py", "skill.yaml"]
        for file in required:
            exists = (skill_path / file).exists()
            print(f"  {file}: {'OK' if exists else 'MISSING'}")
    
    # Check dependencies
    missing = check_dependencies()
    print(f"Dependencies: {'OK' if not missing else f'{len(missing)} missing'}")
    if missing:
        for m in missing:
            print(f"  - {m}")
    
    # Check API key
    has_key = check_fireworks_key()
    print(f"FIREWORKS_API_KEY: {'SET' if has_key else 'NOT SET'}")
    
    return skill_path.exists() and not missing


def main():
    parser = argparse.ArgumentParser(description="Install Hermes Autoscribe Skill")
    parser.add_argument("--path", help="Custom installation path")
    parser.add_argument("--check", action="store_true", help="Check installation status only")
    parser.add_argument("--skip-deps", action="store_true", help="Skip dependency installation")
    args = parser.parse_args()
    
    if args.check:
        installed = check_status()
        sys.exit(0 if installed else 1)
    
    print("=" * 60)
    print("Hermes Autoscribe Skill - Installation")
    print("=" * 60)
    print()
    
    # Check dependencies
    missing = check_dependencies()
    if missing and not args.skip_deps:
        print(f"Missing dependencies: {', '.join(missing)}")
        if not install_dependencies(missing):
            print("Failed to install dependencies. Please install manually:")
            print(f"  pip install {' '.join(missing)}")
            sys.exit(1)
    elif missing:
        print(f"Warning: Missing dependencies: {', '.join(missing)}")
    print()
    
    # Check Fireworks key
    if not check_fireworks_key():
        print("⚠️  WARNING: FIREWORKS_API_KEY not set!")
        print("The skill will not work without this API key.")
        print("Set it with: export FIREWORKS_API_KEY=your_key_here")
        print()
    
    # Install skill
    print("Installing skill files...")
    if not install_skill(args.path):
        print("Installation failed.")
        sys.exit(1)
    print()
    
    # Enable in config
    enable_skill_in_config()
    print()
    
    # Done
    print("=" * 60)
    print("Installation Complete!")
    print("=" * 60)
    print()
    print("Quick start:")
    print("  hermes autoscribe init my-project")
    print("  hermes autoscribe add-repo my-project /path/to/repo --name backend")
    print()


if __name__ == "__main__":
    main()
