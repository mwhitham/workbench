# {project_name} -- Agent Instructions

## Before You Start
1. Read `docs/INDEX.md` for the full documentation map
2. Read `docs/architecture/system-overview.md` to understand the system architecture
3. Check any relevant ADRs in `docs/decisions/` before making architectural changes

## Repository Structure
This workbench orchestrates multiple independent repos under `repos/`.
Each repo has its own git history. The workbench tracks only docs, config, and tooling.

## CLI Quick Reference
- `workbench init` -- clone repos, install deps, run discovery
- `workbench discover` -- auto-detect repo configurations
- `workbench up [service]` -- start services
- `workbench down [service]` -- stop services
- `workbench status` -- dashboard of repo and service state
- `workbench sync` -- pull latest for all repos
- `workbench push [repo]` -- push changes
- `workbench docs` -- open documentation

## Cross-Repo Development
When a feature spans multiple repos:
1. Document the integration points in `docs/architecture/`
2. Build and test each repo's piece independently
3. Integration test via `workbench up`
4. Update docs if architectural decisions were made

## After Completing Work
- Update relevant documentation if you made architectural decisions
- Run `workbench status` to verify repo states before pushing
