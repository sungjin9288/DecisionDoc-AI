from abc import ABC, abstractmethod
from typing import Any


class StorageFailedError(Exception):
    pass


class Storage(ABC):
    @property
    @abstractmethod
    def kind(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def save_bundle(self, bundle_id: str, bundle: dict[str, Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    def load_bundle(self, bundle_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def save_export(self, bundle_id: str, doc_type: str, markdown: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_export_path(self, bundle_id: str, doc_type: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def get_export_dir(self, bundle_id: str) -> str:
        raise NotImplementedError
