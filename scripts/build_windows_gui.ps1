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

if (Test-Path $backgroundDistRoot) {
    Remove-Item -Recurse -Force $backgroundDistRoot
}
if (Test-Path $backgroundBuildRoot) {
    Remove-Item -Recurse -Force $backgroundBuildRoot
}
if (Test-Path $backgroundZip) {
    Remove-Item -Force $backgroundZip
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

$args = @(
    "--noconfirm",
    "--clean",
    "--windowed",
    "--name", $Name,
    "--paths", "src",
    "--icon", "build-assets\\codex-handoff.ico",
    "--version-file", "build-assets\\version_info.txt",
    "--add-data", "build-assets\\CodexHandoffBackground.zip;build-assets",
    "scripts\\launch_gui.py"
)

if ($OneFile) {
    $args += "--onefile"
}

uv run --group build pyinstaller @args
