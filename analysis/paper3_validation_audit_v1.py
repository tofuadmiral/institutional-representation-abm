"""Offline audit summary codec fix, outside the immutable experiment sources.

The original audit code object performs ALL provenance, full-report comparison
and financial checks. Only its final read of the losslessly encoded report is
decoded, exactly like every other consumer of that codec. No inference, source
edit, outcome/threshold change, repair or write to experimental records.
"""
import argparse
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from experiments import paper3_independent_validation_v1 as r  # noqa: E402


def audit(root, protocol):
    report = (Path(root) / "report.json").resolve(strict=True)

    def checked_load(path):
        value = r.load(path)
        return r.journal.decode(value) if Path(path).resolve() == report else value

    exact = r.billing.bind(r.audit, load=checked_load)
    r.require(exact.__code__ is r.audit.__code__, "same production audit code object")
    return exact(root, protocol)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", action="store_true", required=True)
    parser.add_argument("--expected-protocol", required=True)
    args = parser.parse_args()
    print(json.dumps(r.journal.encode(audit(REPO/r.ROOT_NAME, args.expected_protocol))), flush=True)


if __name__ == "__main__":
    main()
