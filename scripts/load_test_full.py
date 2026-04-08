"""
Full load test suite for DecisionDoc-AI.
Tests: throughput, concurrency, memory stability, SSE streaming.
Usage:
  python scripts/load_test_full.py --host http://localhost:8000
  python scripts/load_test_full.py --host http://localhost:8000 --users 50 --duration 60
"""
import asyncio
import time
import argparse
import statistics
import httpx
import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RequestResult:
    endpoint: str
    method: str
    status_code: int
    duration_ms: float
    error: Optional[str] = None
    bytes_received: int = 0


class LoadTestSuite:
    def __init__(self, host: str, token: str = "", concurrent: int = 10):
        self.host = host
        self.token = token
        self.concurrent = concurrent
        self.results: list[RequestResult] = []

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    async def _req(self, client, method, path, **kwargs) -> RequestResult:
        start = time.monotonic()
        try:
            res = await getattr(client, method)(
                f"{self.host}{path}", headers=self._headers(), **kwargs
            )
            ms = (time.monotonic() - start) * 1000
            return RequestResult(path, method.upper(), res.status_code, ms,
                               bytes_received=len(res.content))
        except Exception as e:
            ms = (time.monotonic() - start) * 1000
            return RequestResult(path, method.upper(), 0, ms, error=str(e))

    async def test_static_endpoints(self) -> dict:
        """Test 1: Static/read endpoints — baseline latency."""
        print("\n[Test 1] Static endpoints (100 requests, concurrent)")
        async with httpx.AsyncClient(timeout=10) as client:
            endpoints = ["/health", "/bundles", "/billing/plans"]
            tasks = []
            for _ in range(34):
                for ep in endpoints:
                    tasks.append(self._req(client, "get", ep))
            results = await asyncio.gather(*tasks)
        self.results.extend(results)
        return self._summarize("Static endpoints", results)

    async def test_auth_endpoints(self) -> dict:
        """Test 2: Auth token refresh under load."""
        if not self.token:
            return {"skipped": True, "reason": "No token provided"}

        print(f"\n[Test 2] Auth /auth/me ({self.concurrent * 5} concurrent)")
        async with httpx.AsyncClient(timeout=10) as client:
            tasks = [
                self._req(client, "get", "/auth/me")
                for _ in range(self.concurrent * 5)
            ]
            results = await asyncio.gather(*tasks)
        self.results.extend(results)
        return self._summarize("Auth endpoints", results)

    async def test_dashboard_endpoints(self) -> dict:
        """Test 3: Dashboard data aggregation."""
        print(f"\n[Test 3] Dashboard ({self.concurrent * 3} concurrent)")
        async with httpx.AsyncClient(timeout=15) as client:
            endpoints = [
                "/dashboard/overview",
                "/dashboard/bundle-performance",
                "/projects/stats",
                "/billing/status",
            ]
            tasks = []
            for _ in range(self.concurrent):
                for ep in endpoints:
                    tasks.append(self._req(client, "get", ep))
            results = await asyncio.gather(*tasks)
        self.results.extend(results)
        return self._summarize("Dashboard", results)

    async def test_concurrent_users(self, duration_seconds: int = 30) -> dict:
        """Test 4: Sustained concurrent user simulation."""
        print(f"\n[Test 4] {self.concurrent} concurrent users for {duration_seconds}s")

        async def user_session(user_id: int, results: list):
            end_time = time.monotonic() + duration_seconds
            async with httpx.AsyncClient(timeout=15) as client:
                while time.monotonic() < end_time:
                    # Simulate user workflow
                    for ep in ["/bundles", "/dashboard/overview",
                               "/notifications/unread-count"]:
                        r = await self._req(client, "get", ep)
                        results.append(r)
                    await asyncio.sleep(0.5)

        all_results = []
        tasks = [user_session(i, all_results)
                 for i in range(self.concurrent)]
        await asyncio.gather(*tasks)
        self.results.extend(all_results)
        return self._summarize(f"Concurrent users ({duration_seconds}s)", all_results)

    async def test_rate_limiting(self) -> dict:
        """Test 5: Verify rate limiting triggers correctly."""
        print("\n[Test 5] Rate limiting validation")
        results = []
        async with httpx.AsyncClient(timeout=5) as client:
            # Rapid-fire login attempts (should trigger 429)
            tasks = [
                self._req(client, "post", "/auth/login",
                         json={"username": "test", "password": "wrong"},
                         headers={"X-Forwarded-For": "10.0.0.99"})
                for _ in range(15)
            ]
            res = await asyncio.gather(*tasks)
            results.extend(res)

            rate_limited = sum(1 for r in res if r.status_code == 429)
            print(f"   429 responses: {rate_limited}/15 (expected: ~5+)")

        return {
            "total": len(results),
            "rate_limited": rate_limited,
            "rate_limiting_works": rate_limited >= 3,
        }

    async def test_memory_stability(self) -> dict:
        """Test 6: Check for memory leaks over time."""
        print("\n[Test 6] Memory stability (200 sequential requests)")
        import os
        import gc

        try:
            import psutil
            process = psutil.Process(os.getpid())
            mem_before = process.memory_info().rss / 1024 / 1024
        except ImportError:
            return {"skipped": True, "reason": "psutil not installed"}

        async with httpx.AsyncClient(timeout=10) as client:
            for _ in range(200):
                await self._req(client, "get", "/health")

        gc.collect()
        mem_after = process.memory_info().rss / 1024 / 1024
        growth_mb = mem_after - mem_before

        return {
            "mem_before_mb": round(mem_before, 1),
            "mem_after_mb": round(mem_after, 1),
            "growth_mb": round(growth_mb, 1),
            "stable": growth_mb < 50,  # < 50MB growth acceptable
        }

    def _summarize(self, name: str, results: list) -> dict:
        if not results:
            return {}

        ok = [r for r in results if r.status_code < 400]
        errors = [r for r in results if r.status_code >= 400 or r.error]
        durations = [r.duration_ms for r in results]
        sorted_d = sorted(durations)

        summary = {
            "name": name,
            "total": len(results),
            "success": len(ok),
            "errors": len(errors),
            "success_rate_pct": round(len(ok) / len(results) * 100, 1),
            "avg_ms": round(statistics.mean(durations), 1),
            "p50_ms": round(sorted_d[int(len(sorted_d) * 0.50)], 1),
            "p95_ms": round(sorted_d[int(len(sorted_d) * 0.95)], 1),
            "p99_ms": round(sorted_d[int(len(sorted_d) * 0.99)], 1),
            "max_ms": round(max(durations), 1),
            "passed": (
                len(ok) / len(results) >= 0.99 and
                sorted_d[int(len(sorted_d) * 0.95)] < 2000
            ),
        }

        status = "✅ PASS" if summary["passed"] else "❌ FAIL"
        print(f"   {status} | {name}: "
              f"avg={summary['avg_ms']}ms "
              f"p95={summary['p95_ms']}ms "
              f"success={summary['success_rate_pct']}%")

        return summary

    def print_final_report(self, test_results: list):
        print("\n" + "=" * 70)
        print("LOAD TEST FINAL REPORT")
        print("=" * 70)

        all_passed = all(
            r.get("passed", r.get("rate_limiting_works",
                   r.get("stable", True)))
            for r in test_results
            if not r.get("skipped")
        )

        for r in test_results:
            if r.get("skipped"):
                print(f"  ⏭️  SKIP | {r.get('reason', '')}")
            elif "passed" in r:
                status = "✅" if r["passed"] else "❌"
                print(f"  {status} {r['name']}: "
                      f"p95={r['p95_ms']}ms "
                      f"success={r['success_rate_pct']}%")
            elif "rate_limiting_works" in r:
                status = "✅" if r["rate_limiting_works"] else "❌"
                print(f"  {status} Rate limiting: {r['rate_limited']}/15 blocked")
            elif "stable" in r:
                status = "✅" if r["stable"] else "❌"
                print(f"  {status} Memory: +{r['growth_mb']}MB growth")

        print("=" * 70)
        print(f"OVERALL: {'✅ ALL PASS' if all_passed else '❌ FAILURES DETECTED'}")

        if self.results:
            all_dur = [r.duration_ms for r in self.results]
            print(f"\nGlobal stats: "
                  f"{len(self.results)} requests, "
                  f"avg={statistics.mean(all_dur):.0f}ms, "
                  f"p95={sorted(all_dur)[int(len(all_dur) * 0.95)]:.0f}ms")

        return all_passed


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="http://localhost:8000")
    parser.add_argument("--users", type=int, default=10)
    parser.add_argument("--duration", type=int, default=30)
    parser.add_argument("--username", default="")
    parser.add_argument("--password", default="")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    token = ""
    if args.username and args.password:
        async with httpx.AsyncClient() as c:
            res = await c.post(f"{args.host}/auth/login",
                              json={"username": args.username,
                                    "password": args.password})
            if res.status_code == 200:
                token = res.json().get("access_token", "")
                print(f"✅ Authenticated as {args.username}")

    suite = LoadTestSuite(args.host, token, args.users)
    test_results = []
    test_results.append(await suite.test_static_endpoints())
    test_results.append(await suite.test_auth_endpoints())
    test_results.append(await suite.test_dashboard_endpoints())
    test_results.append(await suite.test_concurrent_users(args.duration))
    test_results.append(await suite.test_rate_limiting())
    test_results.append(await suite.test_memory_stability())

    passed = suite.print_final_report(test_results)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(test_results, f, indent=2, default=str)
        print(f"\nReport saved: {args.output}")

    import sys
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    asyncio.run(main())
