"""Read the existing explicit, decision-local override note format."""

import re


def extract_latest_procurement_override_reason(notes: str) -> str | None:
    text = str(notes or "").strip()
    matches = list(
        re.finditer(
            r"\[override_reason ts=(?P<timestamp>[^\s]+) actor=(?P<actor>[^\]]+)\]\n(?P<reason>.*?)\n\[/override_reason\]",
            text,
            flags=re.DOTALL,
        )
    )
    return (matches[-1].group("reason").strip() or None) if matches else None
