"""
Performance regression tests.
These run in CI to catch performance regressions.
"""
import time
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

PERF_THRESHOLDS = {
    "/health": 100,              # 100ms
    "/bundles": 200,             # 200ms
    "/billing/plans": 200,       # 200ms
    "/dashboard/overview": 500,  # 500ms
}


@pytest.mark.parametrize("endpoint,max_ms", PERF_THRESHOLDS.items())
def test_endpoint_response_time(endpoint, max_ms):
    """Each endpoint must respond within threshold."""
    times = []
    for _ in range(5):
        start = time.monotonic()
        res = client.get(endpoint)
        elapsed = (time.monotonic() - start) * 1000
        assert res.status_code in (200, 401, 403), \
            f"{endpoint} returned {res.status_code}"
        times.append(elapsed)

    avg_ms = sum(times) / len(times)
    assert avg_ms < max_ms, \
        f"{endpoint} avg={avg_ms:.0f}ms > threshold={max_ms}ms"


def test_concurrent_health_checks():
    """100 health checks complete within 5 seconds."""
    import threading

    results = []

    def do_request():
        start = time.monotonic()
        res = client.get("/health")
        results.append((res.status_code, (time.monotonic() - start) * 1000))

    threads = [threading.Thread(target=do_request) for _ in range(100)]
    start = time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    total = time.monotonic() - start

    assert total < 5.0, f"100 requests took {total:.1f}s > 5s"
    assert all(s == 200 for s, _ in results), "Some health checks failed"


def test_no_memory_leak_on_repeated_requests():
    """Repeated requests don't significantly grow memory."""
    try:
        import psutil
        import os
        process = psutil.Process(os.getpid())
        mem_before = process.memory_info().rss / 1024 / 1024
    except ImportError:
        pytest.skip("psutil not installed")

    for _ in range(200):
        client.get("/health")
        client.get("/bundles")

    import gc
    gc.collect()
    mem_after = process.memory_info().rss / 1024 / 1024
    growth = mem_after - mem_before

    assert growth < 50, f"Memory grew {growth:.1f}MB > 50MB threshold"


def test_bundle_list_response_structure():
    """Bundle list returns correct structure within time limit."""
    start = time.monotonic()
    res = client.get("/bundles")
    elapsed = (time.monotonic() - start) * 1000

    # Performance
    assert elapsed < 500, f"Bundle list took {elapsed:.0f}ms"

    # Structure (if authenticated)
    if res.status_code == 200:
        data = res.json()
        assert "bundles" in data or isinstance(data, list)
