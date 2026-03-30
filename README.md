# codex-handoff

`codex-handoff` is a local CLI that prepares the next Codex thread before you switch context. It collects the current project context, decisions, tasks, live Git status, and recent session history into a handoff that is easy to reuse in the next thread.

The source of truth lives in `~/.codex-handoff/projects/<project-id>/`. Each repository gets a readable sync mirror in `.codex-handoff/`, and Codex integration is added once through `~/.codex/AGENTS.md`.

English is the default. Set `CODEX_HANDOFF_LANG=ja` for Japanese or `CODEX_HANDOFF_LANG=auto` to follow the system locale.

v2.1 added `codex-handoff-ui` for people who do not want to use a shell. The GUI ships as a standalone `exe` and can self-install into `%LOCALAPPDATA%\CodexHandoff` on first launch.

v2.2 added background sync so the active workspace handoff stays up to date even when the GUI is closed.

v0.6 added `memory.json` as the structured memory source of truth, separating user preferences, specs, constraints, and decisions from progress, verification, commits, changed files, current focus, important paths, and next actions. Thin user-wide settings live in `~/.codex-handoff/user-memory.json`.

## Supported environment

- Windows 11
- CodexWindowsApp
- PowerShell
- A Python environment with `uv`, or the Windows `setup.exe` from GitHub Releases

## Purpose

- Reduce the need to rewrite project context every time you switch threads
- Move to a new thread safely before context compression hurts quality
- Avoid dependence on hidden Codex UI hooks or internal databases
- Work from a GitHub install without per-project manual setup

## Language

- English is the default
- Set `CODEX_HANDOFF_LANG=en` to force English
- Set `CODEX_HANDOFF_LANG=ja` to force Japanese
- Set `CODEX_HANDOFF_LANG=auto` to follow the system locale

## Choose a path

### CLI

- Install the CLI with `uv tool install codex-handoff`
- Run `codex-handoff setup --install-global-agents` once
- Then call `codex-handoff prepare --stdout` in each project

### GUI / installer

- Download `CodexHandoffSetup.exe` or `CodexHandoffSetup-<version>.exe` from GitHub Releases
- Run `setup.exe` to self-install into `%LOCALAPPDATA%\CodexHandoff`
- The installer also places `codex-handoff.exe` in `%LOCALAPPDATA%\CodexHandoff` and adds that directory to the user `PATH`
- Use Step 2 and `Apply setup` to enable global setup and background sync
- If Codex or the terminal was already open during installation, restart it once before testing the command

## Install

```powershell
$env:UV_CACHE_DIR = Join-Path $env:USERPROFILE '.uv-cache'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $env:USERPROFILE '.uv-python'
uv tool install codex-handoff
codex-handoff setup
```

If you want the next thread to be ready immediately:

```powershell
codex-handoff setup --install-global-agents
codex-handoff prepare --stdout
```

To try a local checkout during development:

```powershell
$env:UV_CACHE_DIR = Join-Path $env:USERPROFILE '.uv-cache'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $env:USERPROFILE '.uv-python'
uv tool install .
codex-handoff setup
```

While developing this repository itself, prefer the source in the checkout over an installed CLI:

```powershell
$env:UV_CACHE_DIR = Join-Path $env:USERPROFILE '.uv-cache'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $env:USERPROFILE '.uv-python'
uv run codex-handoff prepare --stdout
```

## Verify installation

After installation, these three checks should work:

```powershell
codex-handoff where
codex-handoff doctor
codex-handoff prepare --stdout
```

- `where` shows both `~/.codex-handoff/projects/<project-id>/` and `.codex-handoff/`
- `doctor` reports no problems with global setup or the project store
- `prepare --stdout` prints the body that belongs in `.codex-handoff/next-thread.md`
- If `codex-handoff` is still not found, restart Codex once or run `%LOCALAPPDATA%\CodexHandoff\codex-handoff.exe prepare --stdout` directly

## Usage

In normal use, running `setup` once is enough. It creates the global store and the AGENTS snippet, but it does not modify `~/.codex/AGENTS.md` unless you ask it to.

```powershell
codex-handoff setup
codex-handoff setup --install-global-agents
codex-handoff uninstall-global-agents
codex-handoff prepare --stdout
codex-handoff capture --note "Continue investigating the API error"
codex-handoff where
codex-handoff doctor
```

### GUI

To launch the GUI from a development checkout:

```powershell
$env:UV_CACHE_DIR = Join-Path $env:USERPROFILE '.uv-cache'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $env:USERPROFILE '.uv-python'
uv run codex-handoff-ui
```

The GUI is a two-step setup wizard:

- Step 1: install the standalone executable into `%LOCALAPPDATA%\CodexHandoff`
- Step 2: apply the selected automation settings
- Done: the active workspace handoff keeps updating in the background
- You can also copy the current workspace handoff from the GUI

### `setup`

This is the machine-level first-time setup.

- Creates `~/.codex-handoff/`
- Creates `~/.codex-handoff/global-agents-snippet.md`
- Creates `~/.codex-handoff/user-memory.json`

By default it does not touch `~/.codex/AGENTS.md`.

If you want automatic loading, run:

```powershell
codex-handoff setup --install-global-agents
```

When that option is enabled, `codex-handoff` backs up any existing `~/.codex/AGENTS.md` file and only adds or updates the managed block. It never replaces the whole file.

### `uninstall-global-agents`

Removes only the managed `codex-handoff` block from `~/.codex/AGENTS.md`. It also creates a backup and preserves any other existing rules.

### `prepare`

Automatically detects the current project, reuses or creates the matching global project store, and regenerates:

- `project.md`
- `decisions.md`
- `tasks.md`
- `memory.json`
- `next-thread.md`

It also updates the repository-local `.codex-handoff/` mirror. Use `--stdout` to print the body that can be pasted directly into a new thread.

### `capture`

Stores the current Git state in `state.json` and regenerates `project.md`, `decisions.md`, `tasks.md`, `memory.json`, and `next-thread.md`. Use `--note` to turn the note into a high-priority task in the regenerated output.

### `where`

Shows the global store for the current project and the local mirror path in the repository.

### `doctor`

Checks the global setup, the current project store, UTF-8 handling for the global store, and Git availability.

### `init`

Compatibility command. Use it only if you want to create the project store before running anything else. In normal use, `prepare` and `capture` create the store automatically.

## Flow

When you start a new thread, the system usually works like this:

1. `setup` prepares the global store and the AGENTS snippet.
2. `prepare` resolves the current workspace into a `project-id`.
3. Any existing project store is reused.
4. If none exists, a new project store is created.
5. The handoff files are regenerated.
6. The repository-local `.codex-handoff/` mirror is written.
7. The next thread can start from `prepare --stdout`.

## Storage

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

`project.md`, `decisions.md`, `tasks.md`, `memory.json`, and `next-thread.md` are all generated from README, AGENTS, Git state, and recent Codex sessions.

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

The thin user-global memory file at `~/.codex-handoff/user-memory.json` stores only stable cross-project preferences such as language, environment assumptions, and safety rules.

## What is stored where

| Type | Example | Location |
| --- | --- | --- |
| project memory | specs, decisions, focus paths, next actions, recent progress | `~/.codex-handoff/projects/<project-id>/memory.json` |
| user-global memory | response language, confirmation before risky operations, persistent environment assumptions | `~/.codex-handoff/user-memory.json` |
| sync mirror | `project.md`, `decisions.md`, `tasks.md`, `next-thread.md` | repository-local `.codex-handoff/` |
| not stored | diff bodies, environment variables, secrets, long chain-of-thought text | not stored |

## Design principles

- Global store artifacts are written without a UTF-8 BOM
- The global store is the source of truth, and the repository-local `.codex-handoff/` directory is only a sync mirror
- Secrets such as diff bodies and environment variable values are not collected
- Git-less directories still work as path-based project stores
- If a local `.codex-handoff/` already exists, it is imported into the global store and then reused as the sync mirror

### Windows PowerShell compatibility

The global store is written without a UTF-8 BOM. The repository-local `.codex-handoff/` mirror is written with a UTF-8 BOM so Windows PowerShell 5.1 can read it with `Get-Content` without extra flags.

## Windows distribution

The end-user package ships as a standalone GUI executable. On first launch it installs itself into `%LOCALAPPDATA%\CodexHandoff`, so you can keep using it without reopening the installer.

```powershell
$env:UV_CACHE_DIR = Join-Path $env:USERPROFILE '.uv-cache'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $env:USERPROFILE '.uv-python'
powershell -ExecutionPolicy Bypass -File .\scripts\build_windows_gui.ps1
```

Build outputs:

- `dist\CodexHandoffSetup.exe`
- `dist\CodexHandoffSetup-<version>.exe`

The fixed filename always points to the latest build. The versioned filename is easier to track in GitHub Releases and manual distribution. At this stage the project expects simple download-and-run distribution, so an external installer such as Inno Setup is not required.

User-facing behavior:

- `setup.exe` installs the app into `%LOCALAPPDATA%\CodexHandoff`
- The installed directory also contains `codex-handoff.exe` for command-line use
- The installer adds `%LOCALAPPDATA%\CodexHandoff` to the user `PATH`
- Re-running a newer `setup.exe` updates the existing installation
- background sync watches the active workspace and refreshes the handoff in the background
- if you no longer need it, you can delete `%LOCALAPPDATA%\CodexHandoff` and optionally run `codex-handoff uninstall-global-agents` to remove the AGENTS block

The build also generates:

- `build-assets/codex-handoff.ico`
- `build-assets/version_info.txt`

That means the packaged executable includes the app icon and Windows version information.

This development repository does not commit generated files under `.codex-handoff/`, `dist/`, `build/`, or `build-assets/`. Public distribution happens through GitHub Releases, not through Git history.

## GitHub Releases

The Windows release workflow is [release-windows.yml](.github/workflows/release-windows.yml).

- `workflow_dispatch` is supported for manual runs
- `v*` tag pushes run automatically
- The workflow saves `CodexHandoffSetup.exe` and `CodexHandoffSetup-<version>.exe` as artifacts
- Tag runs attach both files to the GitHub Release automatically

Example flow:

```powershell
git tag v0.6.10
git push origin v0.6.10
```

## License

MIT License. See `LICENSE` for details.
