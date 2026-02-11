import json
from pathlib import Path
from typing import Any


class FileRepository:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def save_record(self, record: dict[str, Any]) -> Path:
        request_id = record["request_id"]
        path = self.data_dir / f"{request_id}.json"
        with path.open("w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        return path

    def export_markdown_docs(self, request_id: str, docs: list[dict[str, Any]]) -> tuple[Path, list[dict[str, str]]]:
        export_dir = self.data_dir / request_id
        export_dir.mkdir(parents=True, exist_ok=True)
        files: list[dict[str, str]] = []

        for doc in docs:
            doc_type = doc["doc_type"]
            file_path = export_dir / f"{doc_type}.md"
            file_path.write_text(doc["markdown"], encoding="utf-8")
            files.append({"doc_type": doc_type, "path": str(file_path)})

        return export_dir, files
