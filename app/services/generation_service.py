import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from jinja2 import Environment, FileSystemLoader

from app.domain.schema import BUNDLE_JSON_SCHEMA_V1, SCHEMA_VERSION
from app.eval.lints import lint_docs
from app.observability.timing import Timer
from app.providers.base import Provider, ProviderError
from app.providers.stabilizer import stabilize_bundle, strip_internal_bundle_fields
from app.schemas import GenerateRequest
from app.storage.base import Storage
from app.services.validator import validate_docs


class ProviderFailedError(Exception):
    pass


class EvalLintFailedError(Exception):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("Eval lint failed.")
        self.errors = errors


class GenerationService:
    TEMPLATE_MAP = {
        "adr": "adr.md.j2",
        "onepager": "onepager.md.j2",
        "eval_plan": "eval_plan.md.j2",
        "ops_checklist": "ops_checklist.md.j2",
    }

    def __init__(
        self,
        provider_factory: Callable[[], Provider],
        template_dir: Path,
        data_dir: Path,
        storage: Storage | None = None,
    ) -> None:
        self.provider_factory = provider_factory
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir = self.data_dir / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.storage = storage
        self.env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def generate_documents(self, requirements: GenerateRequest, *, request_id: str) -> dict[str, Any]:
        bundle_id = str(uuid4())
        payload = requirements.model_dump(mode="json")
        provider = self._safe_get_provider()
        timer = Timer()
        cache_enabled = os.getenv("DECISIONDOC_CACHE_ENABLED", "0") == "1"
        cache_hit = False
        provider_called = False

        bundle: dict[str, Any]
        cache_path = self._cache_path(provider.name, SCHEMA_VERSION, payload)
        if cache_enabled and cache_path.exists():
            cached = self._try_read_cache(cache_path)
            if cached is not None:
                bundle = cached
                cache_hit = True
            else:
                with timer.measure("provider_ms"):
                    bundle = self._call_provider_once(provider, payload, request_id)
                provider_called = True
                bundle = stabilize_bundle(bundle)
                bundle = strip_internal_bundle_fields(bundle)
                self._validate_bundle_schema(bundle)
                self._write_cache_atomic(cache_path, bundle)
        else:
            with timer.measure("provider_ms"):
                bundle = self._call_provider_once(provider, payload, request_id)
            provider_called = True
            bundle = stabilize_bundle(bundle)
            bundle = strip_internal_bundle_fields(bundle)
            self._validate_bundle_schema(bundle)
            if cache_enabled:
                self._write_cache_atomic(cache_path, bundle)

        self._validate_bundle_schema(bundle)
        if self.storage is not None:
            self.storage.save_bundle(bundle_id, bundle)
        with timer.measure("render_ms"):
            docs = self._render_docs(payload, bundle)
        with timer.measure("lints_ms"):
            lint_errors = lint_docs({doc["doc_type"]: doc["markdown"] for doc in docs})
        if lint_errors:
            raise EvalLintFailedError(lint_errors)
        with timer.measure("validator_ms"):
            validate_docs(docs)
        usage_tokens = provider.consume_usage_tokens() if provider_called else None
        return {
            "docs": docs,
            "raw_bundle": bundle,
            "metadata": {
                "provider": provider.name,
                "schema_version": SCHEMA_VERSION,
                "cache_hit": cache_hit if cache_enabled else None,
                "request_id": request_id,
                "bundle_id": bundle_id,
                "timings_ms": timer.durations_ms,
                "llm_prompt_tokens": (usage_tokens or {}).get("prompt_tokens"),
                "llm_output_tokens": (usage_tokens or {}).get("output_tokens"),
                "llm_total_tokens": (usage_tokens or {}).get("total_tokens"),
            },
        }

    def _render_docs(self, payload: dict[str, Any], bundle: dict[str, Any]) -> list[dict[str, str]]:
        docs: list[dict[str, str]] = []
        for doc_type in payload["doc_types"]:
            doc_key = doc_type if isinstance(doc_type, str) else doc_type.value
            template_name = self.TEMPLATE_MAP[doc_key]
            context = {
                "title": payload["title"],
                "goal": payload["goal"],
                "context": payload.get("context", ""),
                "constraints": payload.get("constraints", ""),
                "priority": payload.get("priority", ""),
                "audience": payload.get("audience", ""),
                **bundle[doc_key],
            }
            markdown = self.env.get_template(template_name).render(**context).strip() + "\n"
            docs.append({"doc_type": doc_key, "markdown": markdown})
        return docs

    def _validate_bundle_schema(self, bundle: Any) -> None:
        if not isinstance(bundle, dict):
            raise ProviderFailedError("Provider failed.")

        required_top = BUNDLE_JSON_SCHEMA_V1["required"]
        properties = BUNDLE_JSON_SCHEMA_V1["properties"]
        for key in required_top:
            if key not in bundle:
                raise ProviderFailedError("Provider failed.")
            if not isinstance(bundle[key], dict):
                raise ProviderFailedError("Provider failed.")
            required_fields = properties[key]["required"]
            for field in required_fields:
                if field not in bundle[key]:
                    raise ProviderFailedError("Provider failed.")
                value = bundle[key][field]
                expected_type = properties[key]["properties"][field]["type"]
                if expected_type == "string" and not isinstance(value, str):
                    raise ProviderFailedError("Provider failed.")
                if expected_type == "array":
                    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                        raise ProviderFailedError("Provider failed.")

    def _cache_path(self, provider_name: str, schema_version: str, payload: dict[str, Any]) -> Path:
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        key = f"{provider_name}:{schema_version}:{canonical}"
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.json"

    def _call_provider_once(self, provider: Provider, payload: dict[str, Any], request_id: str) -> dict[str, Any]:
        max_calls_per_request = 1
        calls_made = 0
        try:
            calls_made += 1
            if calls_made > max_calls_per_request:
                raise ProviderFailedError("Provider failed.")
            return provider.generate_bundle(payload, schema_version=SCHEMA_VERSION, request_id=request_id)
        except ProviderError as exc:
            raise ProviderFailedError("Provider failed.") from exc
        except Exception as exc:
            raise ProviderFailedError("Provider failed.") from exc

    def _try_read_cache(self, cache_path: Path) -> dict[str, Any] | None:
        try:
            text = cache_path.read_text(encoding="utf-8")
            parsed = json.loads(text)
            if not isinstance(parsed, dict):
                return None
            return parsed
        except (OSError, ValueError, json.JSONDecodeError):
            return None

    def _write_cache_atomic(self, cache_path: Path, bundle: dict[str, Any]) -> None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(bundle, ensure_ascii=False, indent=2)
        tmp_path = cache_path.with_name(f"{cache_path.name}.tmp.{uuid4().hex}")
        try:
            with tmp_path.open("w", encoding="utf-8") as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, cache_path)
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

    def _safe_get_provider(self) -> Provider:
        try:
            return self.provider_factory()
        except ProviderError as exc:
            raise ProviderFailedError("Provider failed.") from exc
        except Exception as exc:
            raise ProviderFailedError("Provider failed.") from exc
