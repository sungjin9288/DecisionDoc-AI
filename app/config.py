import logging
import os

_cfg_log = logging.getLogger("decisiondoc.config")
APP_VERSION = "1.1.11"


def is_enabled(value: str) -> bool:
    """Return True if value represents a truthy env-var flag."""
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_is_enabled(name: str, default: str = "0") -> bool:
    return is_enabled(os.getenv(name, default))


# ── Safe numeric helpers ───────────────────────────────────────────────────────

def _get_int(name: str, default: int) -> int:
    """Read an integer env var with a safe fallback on invalid values."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        _cfg_log.warning(
            "Env var %s=%r is not a valid integer; using default %s", name, raw, default
        )
        return default


def _get_float(name: str, default: float) -> float:
    """Read a float env var with a safe fallback on invalid values."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        _cfg_log.warning(
            "Env var %s=%r is not a valid float; using default %s", name, raw, default
        )
        return default


# ── Feature config ─────────────────────────────────────────────────────────────

def is_procurement_copilot_enabled() -> bool:
    """Whether the project-scoped procurement copilot is enabled."""
    return env_is_enabled("DECISIONDOC_PROCUREMENT_COPILOT_ENABLED", "0")


def is_realtime_events_enabled() -> bool:
    """Whether the browser should attempt SSE real-time event streaming."""
    default = "0" if os.getenv("AWS_LAMBDA_FUNCTION_NAME") else "1"
    return env_is_enabled("DECISIONDOC_REALTIME_EVENTS_ENABLED", default)


def get_auto_expand_threshold() -> int:
    """Minimum number of unmatched requests before auto bundle expansion triggers.

    Configurable via AUTO_EXPAND_THRESHOLD env var (default: 5).
    """
    return _get_int("AUTO_EXPAND_THRESHOLD", 5)


def get_finetune_min_rating() -> int:
    """Minimum user rating (1-5) to collect a fine-tune record.

    Configurable via FINETUNE_MIN_RATING env var (default: 4).
    """
    return _get_int("FINETUNE_MIN_RATING", 4)


def get_finetune_min_score() -> float:
    """Minimum heuristic eval score (0-1) to collect a fine-tune record.

    Configurable via FINETUNE_MIN_SCORE env var (default: 0.85).
    """
    return _get_float("FINETUNE_MIN_SCORE", 0.85)


def get_llm_retry_attempts() -> int:
    """Number of LLM call attempts before giving up (first attempt + retries).

    Configurable via LLM_RETRY_ATTEMPTS env var (default: 3).
    """
    return _get_int("LLM_RETRY_ATTEMPTS", 3)


def get_llm_retry_backoff_seconds() -> list[int]:
    """Per-retry wait times in seconds (e.g. '1,3,7').

    Configurable via LLM_RETRY_BACKOFF_SECONDS env var (default: 1,3,7).
    """
    raw = os.getenv("LLM_RETRY_BACKOFF_SECONDS", "1,3,7")
    try:
        return [int(x.strip()) for x in raw.split(",") if x.strip()]
    except ValueError:
        _cfg_log.warning(
            "LLM_RETRY_BACKOFF_SECONDS=%r is invalid; using default [1, 3, 7]", raw
        )
        return [1, 3, 7]


def get_finetune_auto_threshold() -> int:
    """Minimum number of fine-tune records before auto-training triggers.

    Configurable via FINETUNE_AUTO_THRESHOLD env var (default: 50).
    """
    return _get_int("FINETUNE_AUTO_THRESHOLD", 50)


def get_finetune_base_model() -> str:
    """Base model to use for fine-tuning.

    Configurable via FINETUNE_BASE_MODEL env var (default: 'gpt-4o-mini').
    """
    return os.getenv("FINETUNE_BASE_MODEL", "gpt-4o-mini")


def get_finetune_promotion_threshold() -> float:
    """Minimum score improvement required to promote a fine-tuned model.

    Configurable via FINETUNE_PROMOTION_THRESHOLD env var (default: 0.05).
    """
    return _get_float("FINETUNE_PROMOTION_THRESHOLD", 0.05)


# ── Local LLM config ───────────────────────────────────────────────────────────

def get_local_llm_base_url() -> str:
    """Base URL for the local LLM OpenAI-compatible API.

    Configurable via LOCAL_LLM_BASE_URL env var
    (default: 'http://localhost:11434/v1').
    """
    return os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:11434/v1")


def get_local_llm_model() -> str:
    """Model name to use with the local LLM server.

    Configurable via LOCAL_LLM_MODEL env var (default: 'llama3.1:8b').
    """
    return os.getenv("LOCAL_LLM_MODEL", "llama3.1:8b")


def get_local_llm_timeout() -> int:
    """Request timeout in seconds for local LLM calls.

    Local models are slower than cloud APIs.
    Configurable via LOCAL_LLM_TIMEOUT env var (default: 300).
    """
    return _get_int("LOCAL_LLM_TIMEOUT", 300)


def get_local_llm_api_key() -> str:
    """API key sent to local LLM server (most servers ignore this).

    Configurable via LOCAL_LLM_API_KEY env var (default: 'local').
    """
    return os.getenv("LOCAL_LLM_API_KEY", "local")


# ── Voice Brief integration config ────────────────────────────────────────────

def get_voice_brief_api_base_url() -> str:
    """Base URL for Voice Brief pull import requests.

    Configurable via VOICE_BRIEF_API_BASE_URL.
    Empty string means the integration is disabled.
    """
    return os.getenv("VOICE_BRIEF_API_BASE_URL", "").strip()


def get_voice_brief_api_bearer_token() -> str | None:
    """Optional bearer token for Voice Brief API requests."""
    token = os.getenv("VOICE_BRIEF_API_BEARER_TOKEN", "").strip()
    return token or None


def get_voice_brief_timeout_seconds() -> float:
    """Timeout in seconds for Voice Brief API requests."""
    return _get_float("VOICE_BRIEF_TIMEOUT_SECONDS", 10.0)


# ── Meeting recording / transcription config ────────────────────────────────

def get_openai_api_base_url() -> str:
    """Base URL for OpenAI REST API calls used outside the SDK."""
    return (os.getenv("OPENAI_API_BASE_URL", "").strip() or "https://api.openai.com/v1").rstrip("/")


def get_meeting_recording_max_upload_bytes() -> int:
    """Maximum upload size for native meeting recordings."""
    return _get_int("MEETING_RECORDING_MAX_UPLOAD_BYTES", 25 * 1024 * 1024)


def get_meeting_recording_transcription_model() -> str:
    """Default OpenAI transcription model for native meeting recordings."""
    return os.getenv("MEETING_RECORDING_TRANSCRIPTION_MODEL", "gpt-4o-mini-transcribe").strip()


def get_meeting_recording_context_char_limit() -> int:
    """Maximum transcript chars injected into generation context."""
    return _get_int("MEETING_RECORDING_CONTEXT_CHAR_LIMIT", 12_000)


# ── 나라장터 (G2B) config ───────────────────────────────────────────────────────

def get_g2b_api_key() -> str:
    """API key for 공공데이터포털 나라장터 입찰공고정보서비스.

    Issue at: https://www.data.go.kr/data/15129394/openapi.do
    Configurable via G2B_API_KEY env var (default: '').

    The portal issues a plain-text Decoding key; the API requires the
    URL-encoded (Encoding key) form.  If the stored value contains no
    percent signs it is assumed to be the decoded form and is encoded here.
    """
    import urllib.parse
    api_key = os.getenv("G2B_API_KEY", "")
    if api_key and "%" not in api_key:
        # Decoding key → encode it
        api_key = urllib.parse.quote(api_key, safe="")
    return api_key


def get_g2b_search_days() -> int:
    """Default lookback window in days for G2B keyword search.

    Configurable via G2B_SEARCH_DAYS env var (default: 7).
    """
    return _get_int("G2B_SEARCH_DAYS", 7)


def get_g2b_max_results() -> int:
    """Maximum number of G2B search results to return per query.

    Configurable via G2B_MAX_RESULTS env var (default: 20).
    """
    return _get_int("G2B_MAX_RESULTS", 20)


# ── JWT / Auth config ───────────────────────────────────────────────────────────

def get_jwt_secret_key() -> str:
    """Return the JWT signing secret key.

    Reads JWT_SECRET_KEY env var.
    - Production (ENVIRONMENT=production): raises RuntimeError if unset or < 32 chars.
    - Development: logs a CRITICAL warning and returns a dev-only default.
    Generate a strong key with: openssl rand -hex 32
    """
    key = os.getenv("JWT_SECRET_KEY", "")
    is_production = os.getenv("ENVIRONMENT", "development").lower() == "production"
    if not key:
        if is_production:
            raise RuntimeError(
                "FATAL: JWT_SECRET_KEY must be set in production. "
                "Generate with: openssl rand -hex 32"
            )
        _cfg_log.critical(
            "⚠️  JWT_SECRET_KEY not set — using insecure development default. "
            "NEVER deploy this to production!"
        )
        return "dev-insecure-default-never-use-in-production-32chars!!"
    if len(key) < 32:
        if is_production:
            raise RuntimeError(
                f"JWT_SECRET_KEY too short ({len(key)} chars). Minimum 32 required. "
                "Generate with: openssl rand -hex 32"
            )
        _cfg_log.warning(
            "JWT_SECRET_KEY too short (%d chars). Minimum 32 required in production. "
            "Generate with: openssl rand -hex 32",
            len(key),
        )
    return key


def get_sso_encryption_key() -> str:
    """Return the key used for SSO secret encryption (Fernet/AES-256).

    Derived from JWT_SECRET_KEY by default. In production, set a separate
    SSO_ENCRYPTION_KEY env var for key rotation independence.
    """
    key = os.getenv("SSO_ENCRYPTION_KEY", "")
    if key:
        return key
    # Fall back to JWT secret (same key, different purpose — acceptable for most deployments)
    return get_jwt_secret_key()


# ── SMTP / Email config ────────────────────────────────────────────────────────

def get_smtp_host() -> str:
    """SMTP server host (e.g. smtp.gmail.com)."""
    return os.getenv("SMTP_HOST", "")


def get_smtp_port() -> int:
    """SMTP server port (default 587 for STARTTLS)."""
    return _get_int("SMTP_PORT", 587)


def get_smtp_user() -> str:
    """SMTP login username / sender address."""
    return os.getenv("SMTP_USER", "")


def get_smtp_password() -> str:
    """SMTP login password or app password."""
    return os.getenv("SMTP_PASSWORD", "")


# ── Slack config ───────────────────────────────────────────────────────────────

def get_slack_webhook() -> str:
    """Slack incoming webhook URL (e.g. https://hooks.slack.com/services/...)."""
    return os.getenv("SLACK_WEBHOOK_URL", "")


# ── Stripe config ───────────────────────────────────────────────────────────────

def get_stripe_secret_key() -> str:
    """Stripe secret API key (sk_test_... or sk_live_...)."""
    return os.getenv("STRIPE_SECRET_KEY", "")


def get_stripe_webhook_secret() -> str:
    """Stripe webhook signing secret (whsec_...)."""
    return os.getenv("STRIPE_WEBHOOK_SECRET", "")


def get_stripe_publishable_key() -> str:
    """Stripe publishable key (pk_test_... or pk_live_...)."""
    return os.getenv("STRIPE_PUBLISHABLE_KEY", "")
