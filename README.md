# Workbench

A CLI framework for orchestrating multi-repo projects. Workbench gives you a single command to clone, configure, run, and manage multiple independent git repositories -- and scaffolds the documentation structure that lets AI agents work autonomously across your entire codebase.

## Why Workbench

Modern projects often span multiple repos: an API, a frontend, a mobile app, infrastructure-as-code, microservices. Developing across them means juggling git operations, start commands, ports, and context that lives in your head.

Workbench solves this by providing:

1. **A CLI orchestrator** -- clone, start, stop, sync, and push across all your repos with one command
2. **A documentation scaffold** -- architecture docs, decision records, and agent instructions that sit above any individual repo
3. **Cross-repo workflows** -- feature branches, coordinated PRs, and status dashboards that span repos

The documentation layer is what makes this especially powerful for AI-assisted development. Agents can read the architecture docs to understand how your repos relate, then work across boundaries with full context.

## Install

```bash
pip install git+https://github.com/mwhitham/workbench.git
```

Or clone and install locally:

```bash
git clone https://github.com/mwhitham/workbench.git
cd workbench
pip install -e .
```

## Quick Start

### New project

```bash
mkdir my-project && cd my-project
workbench init
```

This scaffolds a complete workbench structure:

```
my-project/
├── workbench.yaml          # central config for all repos
├── CLAUDE.md               # AI agent instructions
├── docs/
│   ├── INDEX.md            # documentation map
│   ├── architecture/       # system design docs
│   ├── decisions/          # architecture decision records
│   └── guides/             # development guides
└── repos/                  # cloned repos (gitignored)
```

Then add your repos:

```bash
workbench add git@github.com:my-org/api.git
workbench add git@github.com:my-org/frontend.git
workbench add git@github.com:my-org/mobile.git --name mobile
workbench add git@github.com:my-org/infra.git --infra    # reference only, never started
```

### Existing project

If your project already has a `workbench.yaml`, just run:

```bash
workbench init    # clones all repos and installs dependencies
workbench status  # see the dashboard
workbench up      # start all services
```

## Commands

| Command | Description |
|---|---|
| `workbench init` | Scaffold a new workbench or clone repos for an existing one |
| `workbench add <url>` | Add a new repo (clone + config + auto-discover) |
| `workbench discover` | Auto-detect repo configurations (language, ports, start commands) |
| `workbench up [service]` | Start all services or a specific one |
| `workbench down [service]` | Stop running services |
| `workbench status` | Show repo git status and service health dashboard |
| `workbench sync` | Pull latest changes for all repos |
| `workbench push [repo]` | Push changes for one or all repos |
| `workbench cd [target]` | Navigate to workbench root or a repo directory |
| `workbench docs [--serve]` | Open or serve the documentation |

### Cross-repo feature workflow

```bash
workbench feature start my-feature              # create feat/my-feature branch in all repos
workbench feature start my-feature --repos api,web  # only specific repos
workbench feature status                         # see feature progress across repos
workbench feature push                           # push all repos on the feature branch
workbench feature pr                             # create linked PRs across repos
workbench feature finish                         # switch back to default branches
```

### Global flags

| Flag | Description |
|---|---|
| `--quiet` / `-q` | Minimal output for scripts and CI |
| `--verbose` / `-v` | Show underlying commands and debug info |

### Navigation with `workbench cd`

Works from anywhere -- finds the workbench root by walking up from your current directory.

```bash
workbench cd              # go to workbench root
workbench cd api          # go to repos/api (resolves repo names)
workbench cd docs/guides  # go to any relative path from root
```

Requires shell integration. Run `./bin/setup` or add manually:

```bash
eval "$(workbench shell-init)"
```

## Configuration

All repo configuration lives in `workbench.yaml`:

```yaml
workbench:
  name: my-project
  version: 0.1.0

repos:
  api:
    url: git@github.com:my-org/api.git
    path: repos/api
    description: REST API backend
    start_command: npm run dev
    port: 3000
    language: TypeScript
    framework: Express
  frontend:
    url: git@github.com:my-org/frontend.git
    path: repos/frontend
    description: Web frontend
    start_command: npm run dev
    port: 5173
    language: TypeScript
    framework: React
```

Run `workbench discover` to auto-detect fields like language, framework, start command, port, and dependency files.

Repos with `type: infrastructure` are reference-only and never started by `workbench up`.

## For AI Agents

The scaffolded `CLAUDE.md` and `docs/` directory are designed to give AI agents the context they need to work across your entire project. Fill in:

- **`docs/architecture/system-overview.md`** -- how your repos relate, data flow, deployment
- **`docs/decisions/`** -- architecture decision records (use the template)
- **`CLAUDE.md`** -- agent-specific instructions, repo structure, key principles

When an agent reads these docs, it understands the full system -- not just the single file it's editing.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT -- see [LICENSE](LICENSE).
