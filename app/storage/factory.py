import os
from pathlib import Path

from app.storage.base import Storage, StorageFailedError
from app.storage.local import LocalStorage
from app.storage.s3 import s3_from_env


def get_storage() -> Storage:
    storage_kind = os.getenv("DECISIONDOC_STORAGE", "local").lower()
    if storage_kind == "local":
        data_dir = Path(os.getenv("DATA_DIR", "./data"))
        exports_dir = Path(os.getenv("EXPORT_DIR", str(data_dir)))
        return LocalStorage(data_dir=data_dir, exports_dir=exports_dir)
    if storage_kind == "s3":
        return s3_from_env()
    raise StorageFailedError("Storage operation failed.")
