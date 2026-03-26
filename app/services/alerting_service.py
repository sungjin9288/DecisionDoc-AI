"""
Service health alerting via Slack webhook.

Triggers: health check failure, high error rate,
          document generation failure, payment failure.

All functions are fire-and-forget async coroutines.
Fail silently (log only) when the Slack webhook is not configured.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime

_log = logging.getLogger("decisiondoc.alerting")

_EMOJI = {"info": "ℹ️", "warning": "⚠️", "critical": "🚨"}
_COLOR = {"info": "#2196F3", "warning": "#FF9800", "critical": "#F44336"}


async def send_alert(
    title: str,
    message: str,
    severity: str = "warning",
    details: dict | None = None,
) -> None:
    """Send a Slack block-kit alert.  Fails silently if no webhook is set."""
    webhook = os.getenv("SLACK_WEBHOOK_URL", "").strip()
    if not webhook:
        _log.warning("[Alert] %s: %s", title, message)
        return

    blocks: list[dict] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{_EMOJI.get(severity, '🔔')} {title}",
            },
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": message},
        },
    ]

    if details:
        fields = [
            {"type": "mrkdwn", "text": f"*{k}*\n{v}"}
            for k, v in list(details.items())[:10]
        ]
        blocks.append({"type": "section", "fields": fields})

    blocks.append({
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": (
                    f"DecisionDoc AI | "
                    f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                ),
            }
        ],
    })

    payload = {
        "username": "DecisionDoc Monitor",
        "icon_emoji": ":robot_face:",
        "attachments": [
            {
                "color": _COLOR.get(severity, "#757575"),
                "blocks": blocks,
            }
        ],
    }

    try:
        import httpx

        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.post(webhook, json=payload)
            if res.status_code != 200:
                _log.error("[Alert] Slack returned %s: %s", res.status_code, res.text[:200])
            else:
                _log.info("[Alert] Sent: %s", title)
    except ImportError:
        _log.warning("[Alert] httpx not available — cannot send Slack alert")
    except Exception as exc:
        _log.error("[Alert] Failed to send alert '%s': %s", title, exc)


# ── Convenience helpers ───────────────────────────────────────────────────────

async def alert_health_failure(check_name: str, error: str) -> None:
    """Fire when a health-check component transitions to degraded/failed."""
    await send_alert(
        title="서비스 헬스체크 실패",
        message=f"`{check_name}` 헬스체크 실패 — 즉시 확인 필요",
        severity="critical",
        details={"체크 항목": check_name, "오류": error[:200]},
    )


async def alert_high_error_rate(error_rate: float, endpoint: str) -> None:
    """Fire when an endpoint's 5xx rate exceeds threshold."""
    await send_alert(
        title="높은 오류율 감지",
        message=f"`{endpoint}` 오류율 {error_rate:.1f}% 임계값 초과",
        severity="warning",
        details={"엔드포인트": endpoint, "오류율": f"{error_rate:.1f}%"},
    )


async def alert_generation_failure(
    bundle_id: str,
    error: str,
    tenant_id: str,
) -> None:
    """Fire when a document generation fails after all retries."""
    await send_alert(
        title="문서 생성 실패",
        message=f"번들 `{bundle_id}` 생성 실패 (테넌트: {tenant_id})",
        severity="warning",
        details={
            "번들": bundle_id,
            "테넌트": tenant_id,
            "오류": error[:200],
        },
    )


async def alert_payment_failure(tenant_id: str, error: str) -> None:
    """Fire when a Stripe payment event indicates a failure."""
    await send_alert(
        title="결제 실패",
        message=f"테넌트 `{tenant_id}` 결제 실패",
        severity="critical",
        details={"테넌트": tenant_id, "오류": error[:200]},
    )
