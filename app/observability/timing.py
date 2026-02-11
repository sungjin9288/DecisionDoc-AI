import time
from contextlib import contextmanager


class Timer:
    def __init__(self) -> None:
        self.durations_ms: dict[str, int] = {}

    @contextmanager
    def measure(self, key: str):
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed = (time.perf_counter() - start) * 1000
            self.durations_ms[key] = int(round(elapsed))
