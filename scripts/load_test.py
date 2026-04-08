"""Load test for DecisionDoc-AI.

Tests: concurrent users, throughput, auth endpoints.
Run: python scripts/load_test.py --host http://localhost:8000 --users 10
"""
from __future__ import annotations

import asyncio
import argparse
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx


@dataclass
class TestResult:
    endpoint: str
    method: str
    status_code: int
    duration_ms: float
    error: Optional[str] = None


@dataclass
class LoadTestReport:
    total_requests: int = 0
    success_count: int = 0
    error_count: int = 0
    results: list = field(default_factory=list)

    def add(self, result: TestResult) -> None:
        self.results.append(result)
        self.total_requests += 1
        if result.status_code < 400:
            self.success_count += 1
        else:
            self.error_count += 1

    def print_summary(self) -> None:
        if not self.results:
            print("No results")
            return

        durations = [r.duration_ms for r in self.results]
        avg = sum(durations) / len(durations)
        sorted_d = sorted(durations)
        p95 = sorted_d[int(len(sorted_d) * 0.95)]
        p99 = sorted_d[int(len(sorted_d) * 0.99)]

        print("\n" + "=" * 60)
        print("LOAD TEST RESULTS")
        print("=" * 60)
        print(f"Total requests:  {self.total_requests}")
        print(f"Success (2xx):   {self.success_count}")
        print(f"Errors (4xx+):   {self.error_count}")
        print(f"Success rate:    {self.success_count / self.total_requests * 100:.1f}%")
        print(f"\nLatency:")
        print(f"  Average: {avg:.1f}ms")
        print(f"  P95:     {p95:.1f}ms")
        print(f"  P99:     {p99:.1f}ms")
        print(f"  Min:     {min(durations):.1f}ms")
        print(f"  Max:     {max(durations):.1f}ms")

        print("\nPer-endpoint breakdown:")
        by_endpoint: dict[str, list[float]] = {}
        for r in self.results:
            key = f"{r.method} {r.endpoint}"
            by_endpoint.setdefault(key, []).append(r.duration_ms)
        for ep, durs in by_endpoint.items():
            print(f"  {ep}: avg={sum(durs)/len(durs):.1f}ms n={len(durs)}")

        print("\n" + "=" * 60)
        passed = (
            self.success_count / self.total_requests >= 0.99
            and p95 < 2000
            and avg < 500
        )
        print(f"RESULT: {'PASS' if passed else 'FAIL'}")
        if not passed:
            if self.success_count / self.total_requests < 0.99:
                print("  FAIL: Success rate < 99%")
            if p95 >= 2000:
                print(f"  FAIL: P95 {p95:.0f}ms >= 2000ms threshold")
            if avg >= 500:
                print(f"  FAIL: Avg {avg:.0f}ms >= 500ms threshold")


async def run_request(
    client: httpx.AsyncClient, method: str, url: str, **kwargs
) -> TestResult:
    start = time.monotonic()
    try:
        response = await getattr(client, method.lower())(url, **kwargs)
        duration = (time.monotonic() - start) * 1000
        return TestResult(
            endpoint=url.split("//")[-1].split("/", 1)[-1],
            method=method.upper(),
            status_code=response.status_code,
            duration_ms=duration,
        )
    except Exception as exc:
        duration = (time.monotonic() - start) * 1000
        return TestResult(
            endpoint=url,
            method=method.upper(),
            status_code=0,
            duration_ms=duration,
            error=str(exc),
        )


async def load_test(host: str, concurrent_users: int, token: str) -> LoadTestReport:
    report = LoadTestReport()
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    async with httpx.AsyncClient(
        base_url=host, headers=headers, timeout=30.0
    ) as client:
        print(f"Load test: {concurrent_users} concurrent users -> {host}")

        print("\n[1/4] Health endpoint (50 requests)...")
        results = await asyncio.gather(
            *[run_request(client, "GET", "/health") for _ in range(50)]
        )
        for r in results:
            report.add(r)

        print("[2/4] GET /bundles (concurrent)...")
        results = await asyncio.gather(
            *[run_request(client, "GET", "/bundles") for _ in range(concurrent_users * 3)]
        )
        for r in results:
            report.add(r)

        print("[3/4] GET /billing/plans (concurrent)...")
        results = await asyncio.gather(
            *[run_request(client, "GET", "/billing/plans") for _ in range(concurrent_users * 2)]
        )
        for r in results:
            report.add(r)

        print("[4/4] GET /notifications/unread-count (concurrent)...")
        results = await asyncio.gather(
            *[run_request(client, "GET", "/notifications/unread-count") for _ in range(concurrent_users * 2)]
        )
        for r in results:
            report.add(r)

    report.print_summary()
    return report


async def get_test_token(host: str, username: str, password: str) -> str:
    async with httpx.AsyncClient(base_url=host) as client:
        res = await client.post("/auth/login", json={"username": username, "password": password})
        if res.status_code == 200:
            return res.json().get("token") or res.json().get("access_token", "")
        print(f"Warning: Login failed ({res.status_code}) — testing without auth")
        return ""


def main() -> None:
    parser = argparse.ArgumentParser(description="DecisionDoc AI Load Test")
    parser.add_argument("--host", default="http://localhost:8000")
    parser.add_argument("--users", type=int, default=10)
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="")
    args = parser.parse_args()

    async def run() -> None:
        import sys
        token = ""
        if args.password:
            token = await get_test_token(args.host, args.username, args.password)
        report = await load_test(args.host, args.users, token)
        sys.exit(0 if report.error_count == 0 else 1)

    asyncio.run(run())


if __name__ == "__main__":
    main()
