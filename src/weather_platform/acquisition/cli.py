import argparse
import sys

EX_CONFIG = 78


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="weather-platform-acquisition",
        description=(
            "Validate the weather acquisition deployment contract. Live provider transport is "
            "disabled until its trust and integration gates are implemented."
        ),
    )
    parser.add_argument(
        "--require-live-transport",
        action="store_true",
        help="fail unless the separately gated live acquisition transport is available",
    )
    return parser


def run() -> int:
    args = build_parser().parse_args()
    if args.require_live_transport:
        print(
            "live weather acquisition transport is not enabled in this release; "
            "the deployment remains intentionally scaled to zero",
            file=sys.stderr,
        )
        return EX_CONFIG
    print("weather acquisition contracts are installed; live provider transport is disabled")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
