"""
tune.py — Entry point for hyperparameter tuning.
Currently a placeholder for Epic 4.1.2.
"""

import argparse


def main():
    parser = argparse.ArgumentParser(
        description="Tune hyperparameters for Opmed optimization (placeholder)."
    )
    parser.add_argument(
        "--config", type=str, default="configs/config.yaml", help="Base config file."
    )
    parser.add_argument(
        "--grid", type=str, default="configs/tune_grid.yaml", help="Grid search config."
    )
    parser.add_argument(
        "--outdir",
        type=str,
        default="data/output/tune",
        help="Directory for tuning results.",
    )

    args = parser.parse_args()
    print("tune placeholder")
    print(f"Config: {args.config}")
    print(f"Grid: {args.grid}")
    print(f"Output dir: {args.outdir}")


if __name__ == "__main__":
    main()
