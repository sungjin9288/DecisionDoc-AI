from abc import ABC, abstractmethod
from typing import Any


class ProviderError(Exception):
    pass


class Provider(ABC):
    name: str

    @abstractmethod
    def generate_bundle(
        self,
        requirements: dict[str, Any],
        *,
        schema_version: str,
        request_id: str,
    ) -> dict[str, Any]:
        raise NotImplementedError
