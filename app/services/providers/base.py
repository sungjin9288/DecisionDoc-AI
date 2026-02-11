from abc import ABC, abstractmethod
from typing import Any

from app.schemas import DocType, GenerateRequest


class Provider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def build_context(self, doc_type: DocType, request: GenerateRequest) -> dict[str, Any]:
        raise NotImplementedError
