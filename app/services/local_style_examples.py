"""Extract bounded verbatim examples without model analysis or OCR."""
from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from app.services.attachment_service import (
    AttachmentError,
    MAX_CHARS_PER_FILE,
    MAX_FILE_SIZE_BYTES,
    extract_text,
)

ALLOWED_FORMATS = frozenset({".txt", ".md", ".docx", ".hwpx", ".pdf"})
MAX_FILES = 8
MAX_EXAMPLES = 8
MAX_EXAMPLE_CHARS = 1000


def extract_local_examples(filename: str, raw: bytes) -> list[str]:
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_FORMATS:
        raise AttachmentError("TXT, MD, DOCX, HWPX, 텍스트 PDF만 가져올 수 있습니다.")
    if not filename or any(ord(c) < 32 or ord(c) == 127 for c in filename):
        raise AttachmentError("올바른 파일명이 필요합니다.")
    if len(raw) > MAX_FILE_SIZE_BYTES:
        raise AttachmentError("파일당 최대 20 MB까지 가져올 수 있습니다.")
    if extension in {".docx", ".hwpx"}:
        _validate_package(raw)
    text = extract_text(filename, raw)[:MAX_CHARS_PER_FILE]
    if any(ord(char) < 32 and char not in "\n\r\t" for char in text):
        raise AttachmentError("읽을 수 있는 문서 텍스트가 아닙니다.")
    examples: list[str] = []
    for line in text.splitlines():
        for offset in range(0, len(line), MAX_EXAMPLE_CHARS):
            excerpt = line[offset:offset + MAX_EXAMPLE_CHARS].strip()
            if excerpt and excerpt not in examples:
                examples.append(excerpt)
                if len(examples) == MAX_EXAMPLES:
                    return examples
    if not examples:
        raise AttachmentError("가져올 수 있는 예문이 없습니다.")
    return examples


def _validate_package(raw: bytes) -> None:
    # Office containers can expand far beyond their uploaded byte count.
    try:
        with ZipFile(BytesIO(raw)) as archive:
            members = archive.infolist()
            if len(members) > 1000 or sum(item.file_size for item in members) > MAX_FILE_SIZE_BYTES:
                raise AttachmentError("압축 해제 크기가 문서 처리 제한을 초과합니다.")
            for item in members:
                if item.filename.endswith('.xml'):
                    ElementTree.fromstring(archive.read(item))
    except (BadZipFile, ElementTree.ParseError, DefusedXmlException, RuntimeError, ValueError) as exc:
        raise AttachmentError("올바른 문서 패키지가 아닙니다.") from exc
