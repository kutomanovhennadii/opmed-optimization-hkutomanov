"""
run.py — Entry point for running the Opmed optimization.
Currently a placeholder for Epic 4.1.2.
"""

import argparse


def main():
    parser = argparse.ArgumentParser(
        description="Run Opmed optimization pipeline (placeholder)."
    )
    parser.add_argument(
        "--config", type=str, default="configs/config.yaml", help="Path to config file."
    )
    parser.add_argument(
        "--surgeries",
        type=str,
        default="data/input/surgeries.csv",
        help="Path to surgeries input file.",
    )
    parser.add_argument(
        "--outdir", type=str, default="data/output", help="Output directory."
    )

    args = parser.parse_args()
    print("run placeholder")
    print(f"Config: {args.config}")
    print(f"Surgeries: {args.surgeries}")
    print(f"Output dir: {args.outdir}")


if __name__ == "__main__":
    main()
