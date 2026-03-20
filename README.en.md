# codex-handoff

`codex-handoff` is a local CLI for preparing the next Codex thread before you switch context. It collects the current project context, decisions, tasks, live Git status, and recent session history into a handoff that is easy to reuse in the next thread.

The source of truth lives in `~/.codex-handoff/projects/<project-id>/`. Each repository gets a readable sync mirror in `.codex-handoff/`, and Codex integration is added once through `~/.codex/AGENTS.md`.

For the Japanese guide, see [README.md](README.md).

## Supported environment

- Windows 11
- CodexWindowsApp
- PowerShell
- A Python environment with `uv`, or the Windows `setup.exe` from GitHub Releases

## Language selection

The GUI and generated handoff docs follow `CODEX_HANDOFF_LANG`.

- `ja` - force Japanese
- `en` - force English
- `auto` - detect from the system locale

If the variable is unset, `codex-handoff` uses locale detection.

## What it does

- Reduces the need to rewrite project context every time you start a new thread
- Keeps durable memory separate from live status such as branch, release, and workflow state
- Avoids depending on hidden Codex UI hooks or internal databases
- Works from a GitHub install without requiring per-project manual setup

## Quick start

### CLI

```powershell
$env:UV_CACHE_DIR = Join-Path $env:USERPROFILE '.uv-cache'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $env:USERPROFILE '.uv-python'
uv tool install codex-handoff
codex-handoff setup
```

To make the next thread ready immediately:

```powershell
codex-handoff setup --install-global-agents
codex-handoff prepare --stdout
```

### GUI / installer

- Download `CodexHandoffSetup.exe` or `CodexHandoffSetup-<version>.exe` from GitHub Releases
- Run the setup executable
- Use Step 2 to enable global setup and optional background sync

To launch the GUI from a development checkout:

```powershell
$env:UV_CACHE_DIR = Join-Path $env:USERPROFILE '.uv-cache'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $env:USERPROFILE '.uv-python'
uv run codex-handoff-ui
```

## Main commands

### `setup`

Creates the global store and the AGENTS snippet. By default it does not modify `~/.codex/AGENTS.md`.

```powershell
codex-handoff setup
codex-handoff setup --install-global-agents
```

### `prepare`

Automatically detects the current project, reuses or creates the project store, and regenerates:

- `project.md`
- `decisions.md`
- `tasks.md`
- `memory.json`
- `state.json`
- `next-thread.md`

```powershell
codex-handoff prepare --stdout
```

### `capture`

Captures the current Git state and refreshes the handoff files.

```powershell
codex-handoff capture --note "Continue investigating the API error"
```

### `where`

Shows the global store path and the repository-local mirror path.

### `doctor`

Checks the global setup, the project store, UTF-8 handling for the global store, and Git availability.

## How the flow works

1. `setup` creates the global store and the optional AGENTS integration.
2. `prepare` resolves the project from the current working directory.
3. An existing project store is reused when present.
4. Otherwise a new project store is created.
5. The handoff files are regenerated from README, AGENTS, Git state, and recent Codex session history.
6. The repository-local `.codex-handoff/` mirror is refreshed.

## Storage layout

- Global settings and all-project memory: `~/.codex-handoff/`
- Codex auto-load rules: `~/.codex/AGENTS.md`
- Project-specific source of truth: `~/.codex-handoff/projects/<project-id>/`
- Repository-local sync mirror: `.codex-handoff/`

Main generated files:

- `project.md`
- `decisions.md`
- `tasks.md`
- `memory.json`
- `state.json`
- `next-thread.md`

`memory.json` is the structured memory source of truth. It stores:

- semantic memory entries
- worklog entries
- current focus
- focus paths
- next actions

`state.json` stores live status such as:

- current Git branch
- ahead / behind counts
- latest pushed commit
- latest local tag
- GitHub release metadata
- GitHub workflow metadata

The thin user-global memory file at `~/.codex-handoff/user-memory.json` is only for stable cross-project preferences such as language, environment, and safety rules.

## What is stored where

| Type | Example | Location |
| --- | --- | --- |
| project memory | specs, decisions, focus paths, next actions, recent progress | `~/.codex-handoff/projects/<project-id>/memory.json` |
| user-global memory | response language, confirmation before risky operations, persistent environment assumptions | `~/.codex-handoff/user-memory.json` |
| sync mirror | `project.md`, `decisions.md`, `tasks.md`, `next-thread.md` | repository-local `.codex-handoff/` |
| not stored | diff bodies, environment variables, secrets, long chain-of-thought text | not stored |

## Windows release

The end-user distribution ships as a standalone GUI executable. It installs itself into `%LOCALAPPDATA%\CodexHandoff` on first run and can then keep the active workspace handoff updated in the background.

Build outputs:

- `dist\CodexHandoffSetup.exe`
- `dist\CodexHandoffSetup-<version>.exe`

GitHub Releases workflow:

- [release-windows.yml](.github/workflows/release-windows.yml)
- `workflow_dispatch` supported
- `v*` tag pushes publish the release assets automatically

## License

MIT License. See [LICENSE](LICENSE).
