"""Shared connector plumbing: the dry-run switch and a retry wrapper."""

import os
import pathlib
import time

import requests
from dotenv import load_dotenv

# Anchored to the repo root, not the working directory — otherwise running from
# anywhere else finds no .env and surfaces as a bare KeyError on a missing key.
load_dotenv(pathlib.Path(__file__).resolve().parents[2] / ".env")


def owner_label(item: dict) -> str:
    """Display name for an owner. The extractor returns None when nobody
    claimed the task; only the apps need a human-readable stand-in."""
    return item.get("owner") or "Unassigned"


def dry_run() -> bool:
    """Read DRY_RUN at call time so tests and the eval harness can flip it."""
    return os.getenv("DRY_RUN", "true").lower() in ("1", "true", "yes")


def request_with_retry(method: str, url: str, attempts: int = 3, **kwargs):
    """POST/PATCH with backoff. Retries timeouts, 429s, and 5xx; raises otherwise."""
    delay = 1.0
    for attempt in range(1, attempts + 1):
        try:
            response = requests.request(method, url, timeout=15, **kwargs)
            if response.status_code < 400:
                return response
            retryable = response.status_code == 429 or response.status_code >= 500
            if not retryable or attempt == attempts:
                # The body is where the API says what's actually wrong (which
                # Notion property is misnamed, which scope the token lacks).
                # raise_for_status() alone throws that away.
                raise requests.HTTPError(
                    f"{response.status_code} from {url}: {response.text[:400]}",
                    response=response,
                )
        except requests.Timeout:
            if attempt == attempts:
                raise
        time.sleep(delay)
        delay *= 2
    raise RuntimeError(f"{method} {url} failed after {attempts} attempts")
