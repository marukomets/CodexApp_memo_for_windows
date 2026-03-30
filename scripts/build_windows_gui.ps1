param(
    [switch]$OneFile = $true,
    [string]$Name = "CodexHandoffSetup"
)

$ErrorActionPreference = "Stop"
$env:UV_CACHE_DIR = Join-Path $env:USERPROFILE '.uv-cache'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $env:USERPROFILE '.uv-python'

uv run python scripts\generate_build_assets.py --internal-name $Name --original-filename "$Name.exe"

$backgroundName = "CodexHandoffBackground"
$backgroundDistRoot = "build-assets\\background-dist"
$backgroundBuildRoot = "build-assets\\background-build"
$backgroundZip = "build-assets\\CodexHandoffBackground.zip"
$cliName = "codex-handoff"
$cliDistRoot = "build-assets\\cli-dist"
$cliBuildRoot = "build-assets\\cli-build"
$cliExe = "build-assets\\codex-handoff.exe"

if (Test-Path $backgroundDistRoot) {
    Remove-Item -Recurse -Force $backgroundDistRoot
}
if (Test-Path $backgroundBuildRoot) {
    Remove-Item -Recurse -Force $backgroundBuildRoot
}
if (Test-Path $backgroundZip) {
    Remove-Item -Force $backgroundZip
}
if (Test-Path $cliDistRoot) {
    Remove-Item -Recurse -Force $cliDistRoot
}
if (Test-Path $cliBuildRoot) {
    Remove-Item -Recurse -Force $cliBuildRoot
}
if (Test-Path $cliExe) {
    Remove-Item -Force $cliExe
}

$backgroundArgs = @(
    "--noconfirm",
    "--clean",
    "--windowed",
    "--name", $backgroundName,
    "--paths", "src",
    "--distpath", $backgroundDistRoot,
    "--workpath", $backgroundBuildRoot,
    "scripts\\launch_background.py"
)

uv run --group build pyinstaller @backgroundArgs

$backgroundOutputDir = Join-Path $backgroundDistRoot $backgroundName
Compress-Archive -Path (Join-Path $backgroundOutputDir "*") -DestinationPath $backgroundZip

$cliArgs = @(
    "--noconfirm",
    "--clean",
    "--name", $cliName,
    "--paths", "src",
    "--distpath", $cliDistRoot,
    "--workpath", $cliBuildRoot,
    "--onefile",
    "scripts\\launch_cli.py"
)

uv run --group build pyinstaller @cliArgs
Copy-Item (Join-Path $cliDistRoot "$cliName.exe") $cliExe -Force

$args = @(
    "--noconfirm",
    "--clean",
    "--windowed",
    "--name", $Name,
    "--paths", "src",
    "--icon", "build-assets\\codex-handoff.ico",
    "--version-file", "build-assets\\version_info.txt",
    "--add-data", "build-assets\\CodexHandoffBackground.zip;build-assets",
    "--add-data", "build-assets\\codex-handoff.exe;build-assets",
    "scripts\\launch_gui.py"
)

if ($OneFile) {
    $args += "--onefile"
}

uv run --group build pyinstaller @args

$primaryExe = Join-Path "dist" "$Name.exe"
if (Test-Path $primaryExe) {
    Get-ChildItem -Path (Join-Path "dist" "$Name-*.exe") -ErrorAction SilentlyContinue |
        Remove-Item -Force

    $versionedName = uv run python -c "from codex_handoff.build_assets import versioned_executable_name; print(versioned_executable_name('$Name'))"
    $versionedName = $versionedName.Trim()
    $versionedExe = Join-Path "dist" $versionedName
    Copy-Item $primaryExe $versionedExe -Force
    Write-Host "Built installer artifacts:"
    Write-Host "  $primaryExe"
    Write-Host "  $versionedExe"
}
