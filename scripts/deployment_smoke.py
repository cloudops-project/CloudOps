"""Non-mutating post-deployment HTTP smoke test."""

from __future__ import annotations

import argparse
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


def _probe(base_url: str, path: str) -> None:
    url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    request = Request(url, headers={"User-Agent": "cloudops-deployment-smoke/1"})
    try:
        with urlopen(request, timeout=10) as response:
            if response.status != 200:
                raise RuntimeError(f"{path} returned HTTP {response.status}")
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"{path} deployment probe failed") from exc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    args = parser.parse_args()

    for path in ("/health", "/ready", "/healthz"):
        _probe(args.base_url, path)
        print(f"OK {path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        raise SystemExit(1) from None
