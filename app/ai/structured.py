"""
Generic LLM-based structured data generator.

StructuredGenerator[T] takes a Pydantic model class, builds an LLM prompt
that embeds the model's JSON schema, calls the provider, and returns a fully
validated typed instance.  On parse / validation failure it optionally retries
with error context injected into the prompt, giving the LLM a chance to
self-correct.

Usage:

    from pydantic import BaseModel
    from app.ai.structured import StructuredGenerator
    from app.providers.factory import get_provider

    class CodeReview(BaseModel):
        summary: str
        issues: list[str]
        severity: str

    gen = StructuredGenerator(
        CodeReview,
        provider=get_provider(),
        instructions="You are a senior code reviewer.",
        max_retries=1,
    )
    result = gen.generate({"code": "def foo(): pass"}, request_id="req-1")
    # result is a CodeReview instance — fully typed, Pydantic-validated
"""
import json
from typing import Any, Generic, Type, TypeVar

from pydantic import BaseModel, ValidationError

from app.providers.base import Provider, ProviderError

T = TypeVar("T", bound=BaseModel)


class StructuredGenerationError(Exception):
    """Raised when generation fails after all retries are exhausted.

    Attributes:
        last_raw:  The last raw string returned by the provider (may be None).
        attempts:  Total number of provider calls made.
    """

    def __init__(self, message: str, *, last_raw: str | None = None, attempts: int = 1) -> None:
        super().__init__(message)
        self.last_raw = last_raw
        self.attempts = attempts


class StructuredGenerator(Generic[T]):
    """Generic LLM-based structured data generator.

    Given a Pydantic model class this generator:
    1. Extracts the model's JSON schema via model_json_schema().
    2. Builds an LLM prompt that embeds the schema + caller-supplied requirements.
    3. Calls provider.generate_raw() and parses the returned JSON.
    4. Validates the parsed data against the Pydantic model.
    5. On parse / validation failure, retries up to max_retries times,
       injecting a description of the previous error into the prompt so the
       LLM can self-correct.

    The generator is intentionally provider-agnostic: any Provider that
    implements generate_raw() works — including FallbackPipeline.

    Args:
        model_class:  Pydantic BaseModel subclass defining the output shape.
        provider:     Provider instance that implements generate_raw().
        instructions: Optional domain-specific text prepended after the
                      "JSON only" instruction (e.g. "You are a code reviewer.").
        max_retries:  Additional attempts after the first failure.
                      0 means one attempt total (no retries).
    """

    def __init__(
        self,
        model_class: Type[T],
        *,
        provider: Provider,
        instructions: str | None = None,
        max_retries: int = 1,
    ) -> None:
        self.model_class = model_class
        self.provider = provider
        self.instructions = instructions
        self.max_retries = max_retries

    def generate(self, requirements: dict[str, Any], *, request_id: str) -> T:
        """Generate a validated instance of model_class.

        Args:
            requirements: Free-form dict describing the task.  Serialized as
                          JSON and appended to the prompt.
            request_id:   Passed through to the provider for tracing.

        Returns:
            A fully validated instance of model_class.

        Raises:
            ProviderError:            If the provider itself fails (not retried).
            StructuredGenerationError: If all attempts fail due to parse /
                                       validation errors.
        """
        schema = self.model_class.model_json_schema()
        base_prompt = self._build_prompt(requirements, schema)

        last_raw: str | None = None
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            prompt = self._inject_error_hint(base_prompt, last_error)
            try:
                raw = self.provider.generate_raw(prompt, request_id=request_id)
                last_raw = raw
                data = json.loads(raw)
                return self.model_class.model_validate(data)
            except ProviderError:
                raise  # infrastructure failures are not retried
            except json.JSONDecodeError as exc:
                last_error = exc
            except ValidationError as exc:
                last_error = exc

        raise StructuredGenerationError(
            f"Failed to generate valid {self.model_class.__name__} after "
            f"{self.max_retries + 1} attempt(s). Last error: {last_error}",
            last_raw=last_raw,
            attempts=self.max_retries + 1,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_prompt(self, requirements: dict[str, Any], schema: dict[str, Any]) -> str:
        parts = ["Return ONLY valid JSON matching the schema below. No markdown, no explanation."]
        if self.instructions:
            parts.append(self.instructions)
        parts.append(f"schema={json.dumps(schema, ensure_ascii=False)}")
        parts.append(f"requirements={json.dumps(requirements, ensure_ascii=False)}")
        return "\n".join(parts)

    def _inject_error_hint(self, base_prompt: str, error: Exception | None) -> str:
        if error is None:
            return base_prompt
        if isinstance(error, json.JSONDecodeError):
            hint = (
                "Previous attempt failed: output was not valid JSON. "
                "Return ONLY a raw JSON object, no markdown fences or extra text."
            )
        elif isinstance(error, ValidationError):
            hint = (
                f"Previous attempt failed schema validation:\n{error}\n"
                "Correct these issues and return valid JSON."
            )
        else:
            hint = f"Previous attempt failed: {error}. Try again."
        return f"{base_prompt}\n\n{hint}"
