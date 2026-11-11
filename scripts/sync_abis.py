"""Check or refresh canonical backend/frontend ABIs from compiled Foundry artifacts."""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAMES = (
    "CommunityRegistry",
    "CommunitySettlement",
    "NativeSettlementVault",
    "SUNToken",
    "TimelockController",
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    for name in NAMES:
        abi = json.loads(
            (ROOT / "contracts/out" / f"{name}.sol" / f"{name}.json").read_text()
        )["abi"]
        normalized = sorted(json.dumps(entry, sort_keys=True) for entry in abi)
        for directory in (
            "apps/backend/src/blockchain/abis",
            "apps/frontend/src/shared/blockchain",
        ):
            path = ROOT / directory / f"{name}.json"
            if args.write:
                path.write_text(json.dumps(abi, separators=(",", ":")) + "\n")
            if (
                sorted(
                    json.dumps(entry, sort_keys=True)
                    for entry in json.loads(path.read_text())
                )
                != normalized
            ):
                raise SystemExit(
                    f"ABI drift: {path.relative_to(ROOT)}; review then run --write"
                )
    print(
        "Canonical backend/frontend native protocol ABIs match the compiled contracts."
    )


if __name__ == "__main__":
    main()
