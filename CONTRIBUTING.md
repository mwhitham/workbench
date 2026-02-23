# Contributing to Workbench

Thanks for your interest in contributing! Here's how to get started.

## Development Setup

```bash
git clone https://github.com/mwhitham/workbench.git
cd workbench
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Making Changes

1. Fork the repo and create a feature branch
2. Make your changes in the `cli/` directory
3. Test locally by running `workbench` commands
4. Submit a pull request

## Project Structure

```
cli/
├── main.py              # App definition and command registration
├── commands/            # One module per CLI command
│   ├── init.py          # Scaffold new workbench or clone existing repos
│   ├── add.py           # Add a repo interactively
│   ├── up.py / down.py  # Start and stop services
│   ├── status.py        # Dashboard
│   ├── discover.py      # Auto-detect repo configurations
│   ├── feature.py       # Cross-repo feature workflow
│   └── ...
├── utils/               # Shared utilities
│   ├── config.py        # YAML config parser
│   ├── git.py           # Git operations
│   └── process.py       # Process management
└── scaffold/            # Templates for `workbench init`
```

## Guidelines

- Keep the CLI generic -- no project-specific assumptions
- New commands should work with any `workbench.yaml` configuration
- Use Rich for terminal output and Typer for command definitions
- Scaffold templates use `{project_name}` as the placeholder for user's project name

## Reporting Issues

Open an issue on GitHub with:
- What you expected to happen
- What actually happened
- Steps to reproduce
- Your OS and Python version
