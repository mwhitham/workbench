# Local Development

## Prerequisites

- Python 3.9+ (for the workbench CLI)
- Git

<!-- Add any project-specific prerequisites here (e.g. Node.js, Docker, database). -->

## Getting Started

```bash
# Clone the workbench
git clone <your-workbench-repo-url>
cd {project_name}

# Set up the CLI
./bin/setup

# Clone all repos and install dependencies
workbench init

# Check status
workbench status

# Start all services
workbench up
```

## Common Workflows

### Starting services

```bash
workbench up              # start all services
workbench up <service>    # start a specific service
workbench down            # stop all services
```

### Pulling latest changes

```bash
workbench sync            # git pull for all repos
```

### Adding a new repo

```bash
workbench add <git-url>   # clone, configure, and discover
```
