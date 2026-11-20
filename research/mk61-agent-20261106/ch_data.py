"""Prepare a fresh task panel for the single retry after a rejected formula."""

import argparse
from unittest.mock import patch

import cg_data


ROOT = cg_data.ROOT.parent / "spec-formula-retry-v1"
LITERALS = ["0.54783", "2.34783", "6.54783", "49.34783", "-0.54783"]
SEED = 261114653


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("stage", choices=("asts", "wording"))
    stage = cli.parse_args().stage
    with patch.multiple(cg_data, ROOT=ROOT, LITERALS=LITERALS, SEED=SEED):
        if stage == "asts":
            cg_data.build_asts()
        else:
            cg_data.build_wordings()
