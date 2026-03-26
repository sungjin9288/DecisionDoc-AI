from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

T = TypeVar("T")


def run_async(awaitable) -> T:
    """Run an awaitable from sync tests even if the current thread already has a loop."""
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(asyncio.run, awaitable)
        return future.result()
