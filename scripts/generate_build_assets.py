import argparse
from pathlib import Path

from codex_handoff.build_assets import write_build_assets


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--internal-name", default="CodexHandoffSetup")
    parser.add_argument("--original-filename", default="CodexHandoffSetup.exe")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    write_build_assets(
        root / "build-assets",
        internal_name=args.internal_name,
        original_filename=args.original_filename,
    )
