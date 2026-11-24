"""Campus Cleanliness Reporter - launcher.

    python main.py            # terminal menu
    python main.py --gui      # NiceGUI web interface
    python main.py --reset-sample   # restore the 48-record demo dataset first
"""
import argparse
import sys
from pathlib import Path

from ccr.logic import ReportStore
from ccr.storage import DATA_DIR, DEFAULT_PATH, save_reports


def main() -> int:
    p = argparse.ArgumentParser(description="Campus Cleanliness Reporter")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--cli", action="store_true", help="terminal interface (default)")
    mode.add_argument("--gui", action="store_true", help="NiceGUI web interface")
    p.add_argument("--data", default=str(DEFAULT_PATH), help="path to the JSON or CSV data file")
    p.add_argument("--reset-sample", action="store_true", help="overwrite data with the sample dataset")
    p.add_argument("--port", type=int, default=8080, help="GUI port (default 8080)")
    args = p.parse_args()

    if not 1 <= args.port <= 65535:
        p.error("--port must be between 1 and 65535")

    if args.reset_sample:
        sample_path = DATA_DIR / "sample_reports.json"
        if not sample_path.is_file():
            p.error(f"sample dataset not found: {sample_path}")
        sample_store = ReportStore(sample_path)
        if sample_store.notes:
            p.error("sample dataset could not be loaded cleanly: " + "; ".join(sample_store.notes))
        # Save through the storage layer so --data ending in .csv receives CSV,
        # and nested destination folders are created safely.
        save_reports(sample_store.reports, Path(args.data))
        print(f"Sample dataset restored to {args.data}")

    store = ReportStore(Path(args.data))
    if args.gui:
        try:
            from ccr.gui import run_gui
        except ImportError as exc:
            print(f"The GUI needs NiceGUI ({exc}).\nInstall it with:  pip install nicegui\n"
                  "Falling back to the terminal interface.\n")
        else:
            run_gui(store, port=args.port)
            return 0
    from ccr.cli import run_cli
    run_cli(store)
    return 0


if __name__ == "__main__":
    sys.exit(main())
