"""
run_demo.py — Demo runner for the Verdict Engine.

Loads a Russell RAG output from ``sample_russell_output.json``, passes it
through the Verdict Engine, and prints both a raw JSON dump and a
human-readable summary.

Usage:
    python run_demo.py
    python run_demo.py --file path/to/other_russell_output.json
"""

import argparse
import json
import sys
from pathlib import Path

from agents.verdict_engine import VerdictEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_russell_json(path: Path) -> dict:
    """Read and parse a Russell JSON file, with clear error messages."""
    if not path.exists():
        print(f"[ERROR] File not found: {path}")
        print(
            "  Make sure 'sample_russell_output.json' is in the same directory "
            "as run_demo.py, or pass a custom path with --file."
        )
        sys.exit(1)

    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        print(f"[ERROR] Could not parse JSON from {path}: {exc}")
        sys.exit(1)


def print_separator(char: str = "─", width: int = 60) -> None:
    print(char * width)


def print_human_summary(output: dict) -> None:
    """Print the human-readable verdict summary block."""
    verdict    = output["final_verdict"]
    confidence = output["confidence"]
    reason     = output["reason"]
    n_evidence = len(output["stance_breakdown"])

    # Colour-code the verdict for terminals that support ANSI codes.
    colour_map = {"TRUE": "\033[92m", "FALSE": "\033[91m", "UNVERIFIED": "\033[93m"}
    reset      = "\033[0m"
    colour     = colour_map.get(verdict, "")

    print_separator()
    print("  VERDICT ENGINE — HUMAN-READABLE SUMMARY")
    print_separator()
    print(f"  Verdict     : {colour}{verdict}{reset}")
    print(f"  Confidence  : {confidence * 100:.1f}%")
    print(f"  Evidence    : {n_evidence} proposition(s) checked via NLI")
    print(f"  Reason      : {reason}")
    print_separator()


def print_json_output(output: dict) -> None:
    """Pretty-print the raw FinalOutput dict."""
    print_separator()
    print("  VERDICT ENGINE — RAW JSON OUTPUT")
    print_separator()
    print(json.dumps(output, ensure_ascii=False, indent=2))
    print_separator()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the Verdict Engine on a Russell JSON file."
    )
    parser.add_argument(
        "--file",
        type=Path,
        default=Path("sample_russell_output.json"),
        help="Path to the Russell JSON input file (default: sample_russell_output.json)",
    )
    args = parser.parse_args()

    # 1. Load Russell JSON
    print(f"\n[INFO] Loading Russell output from: {args.file}")
    russell_json = load_russell_json(args.file)

    claim  = russell_json.get("claim", "<unknown>")
    signal = russell_json.get("verdict_signal", "<unknown>")
    print(f"[INFO] Claim        : {claim}")
    print(f"[INFO] Signal       : {signal}")
    print(f"[INFO] Bucket A hits: {len(russell_json.get('bucket_a', []))}")
    print(f"[INFO] Bucket B hits: {len(russell_json.get('bucket_b', []))}\n")

    # 2. Run the engine
    print("[INFO] Initialising Verdict Engine...")
    engine = VerdictEngine()

    print("[INFO] Running decide()...\n")
    output = engine.decide(russell_json)

    # 3. Pretty-print raw JSON
    print_json_output(output)

    # 4. Human-readable summary
    print_human_summary(output)
    print()


if __name__ == "__main__":
    main()
