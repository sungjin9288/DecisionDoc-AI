"""app/services/notification_service.py — In-app + email + Slack notifications.

Responsibilities:
- Save in-app notifications via NotificationStore
- Fire email notifications via SMTP (async via executor)
- Fire Slack webhook notifications (async via httpx)
"""
from __future__ import annotations

import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

_log = logging.getLogger("decisiondoc.notification")

# Slack emoji map per event_type
_SLACK_EMOJI: dict[str, str] = {
    "approval_requested": "📋",
    "approval_review_done": "🔍",
    "approval_changes_requested": "✏️",
    "approval_approved": "✅",
    "approval_rejected": "❌",
    "mention": "💬",
    "project_doc_added": "📄",
    "system": "🔔",
}


def _email_configured() -> bool:
    """Return True when SMTP credentials are fully configured."""
    from app.config import get_smtp_host, get_smtp_user, get_smtp_password
    return bool(get_smtp_host() and get_smtp_user() and get_smtp_password())


def _get_slack_webhook() -> str:
    """Return the Slack webhook URL, or empty string if not configured."""
    from app.config import get_slack_webhook
    return get_slack_webhook()


# ── Email ──────────────────────────────────────────────────────────────────────


def _send_email_sync(
    to_address: str,
    subject: str,
    body_text: str,
    body_html: str,
) -> None:
    """Blocking SMTP send. Intended to run in a thread-pool executor."""
    from app.config import get_smtp_host, get_smtp_port, get_smtp_user, get_smtp_password

    host = get_smtp_host()
    port = get_smtp_port()
    user = get_smtp_user()
    password = get_smtp_password()

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to_address
    msg.attach(MIMEText(body_text, "plain", "utf-8"))
    msg.attach(MIMEText(body_html, "html", "utf-8"))

    with smtplib.SMTP(host, port) as server:
        server.ehlo()
        if port != 465:
            server.starttls()
        if password:
            server.login(user, password)
        server.sendmail(user, [to_address], msg.as_string())


def _build_email_html(title: str, body: str, action_url: str | None = None) -> tuple[str, str]:
    """Return (plain_text, html) for a notification email."""
    plain = f"{title}\n\n{body}"
    if action_url:
        plain += f"\n\n바로가기: {action_url}"

    action_btn = ""
    if action_url:
        action_btn = (
            f'<p style="margin-top:24px;">'
            f'<a href="{action_url}" style="background:#6366f1;color:#fff;padding:10px 20px;'
            f'border-radius:6px;text-decoration:none;font-weight:600;">바로가기</a></p>'
        )

    html = f"""<!DOCTYPE html>
<html>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
             background:#f9fafb;margin:0;padding:32px;">
  <div style="max-width:480px;margin:0 auto;background:#fff;border-radius:12px;
              padding:32px;box-shadow:0 2px 8px rgba(0,0,0,.08);">
    <h2 style="margin-top:0;color:#111827;font-size:18px;">{title}</h2>
    <p style="color:#374151;line-height:1.6;">{body}</p>
    {action_btn}
    <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0;">
    <p style="color:#9ca3af;font-size:12px;margin:0;">DecisionDoc AI 알림</p>
  </div>
</body>
</html>"""
    return plain, html


# ── Slack ──────────────────────────────────────────────────────────────────────


def _build_slack_payload(
    event_type: str,
    title: str,
    body: str,
    action_url: str | None = None,
) -> dict:
    emoji = _SLACK_EMOJI.get(event_type, "🔔")
    blocks: list[dict] = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*{emoji} {title}*\n{body}"},
        }
    ]
    if action_url:
        blocks.append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "바로가기"},
                    "url": action_url,
                    "style": "primary",
                }
            ],
        })
    return {"blocks": blocks}


# ── NotificationService ────────────────────────────────────────────────────────


class NotificationService:
    """Dispatch in-app, email, and Slack notifications for a tenant."""

    def __init__(self, tenant_id: str) -> None:
        self._tenant_id = tenant_id

    def _store(self):
        from app.storage.notification_store import get_notification_store
        return get_notification_store(self._tenant_id)

    def _user_store(self):
        from app.storage.user_store import get_user_store
        return get_user_store(self._tenant_id)

    # ── core notify ───────────────────────────────────────────────────────

    async def notify(
        self,
        recipient_id: str,
        event_type: str,
        title: str,
        body: str,
        context_type: str,
        context_id: str,
        action_url: str | None = None,
    ) -> None:
        """Save in-app notification and fire email/Slack as background tasks."""
        # 1. In-app store (always)
        notif = self._store().create(
            tenant_id=self._tenant_id,
            recipient_id=recipient_id,
            event_type=event_type,
            title=title,
            body=body,
            context_type=context_type,
            context_id=context_id,
        )

        # 2. Email (fire-and-forget if configured)
        if _email_configured():
            user = self._user_store().get_by_id(recipient_id)
            if user and getattr(user, "email", None):
                asyncio.create_task(
                    self._send_email_task(notif.notification_id, user.email, title, body, action_url)
                )

        # 3. Slack (fire-and-forget if configured)
        if _get_slack_webhook():
            asyncio.create_task(
                self._send_slack_task(notif.notification_id, event_type, title, body, action_url)
            )

    async def _send_email_task(
        self,
        notification_id: str,
        to_address: str,
        title: str,
        body: str,
        action_url: str | None,
    ) -> None:
        try:
            plain, html = _build_email_html(title, body, action_url)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, _send_email_sync, to_address, title, plain, html
            )
            self._store().mark_email_sent(notification_id)
        except Exception as exc:
            _log.warning("[Notification] Email send failed: %s", exc)

    async def _send_slack_task(
        self,
        notification_id: str,
        event_type: str,
        title: str,
        body: str,
        action_url: str | None,
    ) -> None:
        try:
            import httpx
            webhook = _get_slack_webhook()
            payload = _build_slack_payload(event_type, title, body, action_url)
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(webhook, json=payload)
                resp.raise_for_status()
            self._store().mark_slack_sent(notification_id)
        except Exception as exc:
            _log.warning("[Notification] Slack send failed: %s", exc)

    # ── approval events ───────────────────────────────────────────────────

    async def notify_approval_event(
        self,
        approval,          # ApprovalRecord dataclass
        event_type: str,
        actor_name: str,
        comment: str = "",
    ) -> None:
        """Route approval lifecycle events to the right recipients."""
        approval_id = approval.approval_id
        doc_title = getattr(approval, "title", approval_id)
        context_id = approval_id

        comment_suffix = f"\n의견: {comment}" if comment else ""

        if event_type == "approval_requested":
            # Notify reviewer (ApprovalRecord.reviewer field)
            reviewer = getattr(approval, "reviewer", None)
            if reviewer:
                await self.notify(
                    recipient_id=reviewer,
                    event_type=event_type,
                    title="결재 요청",
                    body=f"{actor_name}님이 '{doc_title}' 문서의 결재를 요청했습니다.{comment_suffix}",
                    context_type="approval",
                    context_id=context_id,
                )

        elif event_type == "approval_review_done":
            # Notify drafter (ApprovalRecord.drafter field)
            drafter = getattr(approval, "drafter", None)
            if drafter:
                await self.notify(
                    recipient_id=drafter,
                    event_type=event_type,
                    title="검토 완료",
                    body=f"{actor_name}님이 '{doc_title}' 검토를 완료했습니다.{comment_suffix}",
                    context_type="approval",
                    context_id=context_id,
                )

        elif event_type == "approval_changes_requested":
            # Notify drafter
            drafter = getattr(approval, "drafter", None)
            if drafter:
                await self.notify(
                    recipient_id=drafter,
                    event_type=event_type,
                    title="수정 요청",
                    body=f"{actor_name}님이 '{doc_title}'의 수정을 요청했습니다.{comment_suffix}",
                    context_type="approval",
                    context_id=context_id,
                )

        elif event_type == "approval_approved":
            # Notify drafter
            drafter = getattr(approval, "drafter", None)
            if drafter:
                await self.notify(
                    recipient_id=drafter,
                    event_type=event_type,
                    title="승인 완료",
                    body=f"'{doc_title}' 문서가 {actor_name}님에 의해 승인되었습니다.{comment_suffix}",
                    context_type="approval",
                    context_id=context_id,
                )

        elif event_type == "approval_rejected":
            # Notify drafter
            drafter = getattr(approval, "drafter", None)
            if drafter:
                await self.notify(
                    recipient_id=drafter,
                    event_type=event_type,
                    title="반려",
                    body=f"'{doc_title}' 문서가 {actor_name}님에 의해 반려되었습니다.{comment_suffix}",
                    context_type="approval",
                    context_id=context_id,
                )

    # ── mention notifications ─────────────────────────────────────────────

    async def notify_mention(
        self,
        message,                   # Message dataclass
        mentioned_user_ids: list[str],
        author_name: str,
    ) -> None:
        """Notify each mentioned user about the mention."""
        message_id = getattr(message, "message_id", "")
        content = getattr(message, "content", "")
        preview = content[:80] + ("..." if len(content) > 80 else "")

        for user_id in mentioned_user_ids:
            await self.notify(
                recipient_id=user_id,
                event_type="mention",
                title="멘션",
                body=f"{author_name}님이 메시지에서 멘션했습니다: {preview}",
                context_type="message",
                context_id=message_id,
            )
