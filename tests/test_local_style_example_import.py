"""Local document excerpts must remain source-grounded and provider-free."""
from io import BytesIO
from zipfile import ZipFile

import pytest

from tests.test_generation_style_selection import CapturingMockProvider, _client_style_store
from tests.test_style_system import _make_client


@pytest.fixture
def client(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)

    def forbidden(*args, **kwargs):
        pytest.fail("Local import must not resolve providers or AI fallback")

    monkeypatch.setattr("app.providers.factory.get_provider_for_bundle", forbidden)
    monkeypatch.setattr("app.providers.factory.get_provider_for_capability", forbidden)
    monkeypatch.setattr("app.services.attachment_service.extract_text_with_ai_fallback", forbidden)
    return client


def test_import_reload_and_generation(client):
    provider = CapturingMockProvider()
    client.app.state.service.provider_factory = lambda: provider
    profile_id = client.post("/styles", json={"name": "Source examples"}).json()["profile_id"]
    before = client.get(f"/styles/{profile_id}").json()
    payload = {"title": "Evidence", "goal": "Compare alternatives", "style_profile_id": profile_id}
    assert client.post("/generate", json=payload).status_code == 200
    old_version = provider.payloads[-1]["_style_snapshot"]["version"]
    marker = "SOURCE_EXAMPLE: distinguish facts from assumptions."
    response = client.post(f"/styles/{profile_id}/import-examples", files=[
        ("files", ("source.txt", (marker + "\n" + marker).encode(), "text/plain")),
        ("files", ("bad.zip", b"invalid", "application/zip")),
    ])
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["method"] == "local_text" and result["provider_calls"] == 0
    assert len(result["imported"]) == len(result["failed"]) == 1
    assert provider.calls == 1
    after = client.get(f"/styles/{profile_id}").json()
    assert after["tone_guide"] == before["tone_guide"]
    assert after["examples"][0]["sample_sentences"] == [marker]
    assert after["examples"][0]["extracted_patterns"] == []
    assert client.post("/generate", json=payload).status_code == 200
    assert marker in provider.prompts[-1]
    assert provider.payloads[-1]["_style_snapshot"]["version"] != old_version


def test_missing_foreign_and_batch_limits(client):
    foreign = _client_style_store(client, "foreign").create("Other", "", "other")
    files = [("files", ("a.txt", b"Evidence", "text/plain"))]
    for profile_id in ("missing", foreign.profile_id):
        assert client.post(f"/styles/{profile_id}/import-examples", files=files).status_code == 404
    profile_id = client.post("/styles", json={"name": "Limits"}).json()["profile_id"]
    assert client.post(f"/styles/{profile_id}/import-examples", files=files * 9).status_code == 422
    assert client.get(f"/styles/{profile_id}").json()["examples"] == []


def test_invalid_bundle_rejected_before_writes(client):
    profile_id = client.post("/styles", json={"name": "Validation"}).json()["profile_id"]
    response = client.post(f"/styles/{profile_id}/import-examples",
                           data={"bundle_id": " invalid "}, files={"files": ("source.txt", b"Evidence")})
    assert response.status_code == 422
    assert client.get(f"/styles/{profile_id}").json()["examples"] == []


def test_fake_s3_import_reloads(client):
    from tests.conditional_state_support import s3_backend
    from app.storage.style_store import StyleStore

    backend, _ = s3_backend()
    client.app.state.state_backend = backend
    profile_id = client.post("/styles", json={"name": "Stored examples"}).json()["profile_id"]
    profile = client.get(f"/styles/{profile_id}").json()
    response = client.post(f"/styles/{profile_id}/import-examples", files={"files": ("source.txt", b"Evidence")})
    assert response.status_code == 200, response.text
    restored = StyleStore(profile['tenant_id'], data_dir=client.app.state.data_dir, backend=backend).get(profile_id)
    assert restored.examples[0].sample_sentences == ["Evidence"]


def test_compressed_and_malformed_hwpx_rejected():
    from app.services.attachment_service import AttachmentError, MAX_FILE_SIZE_BYTES
    from app.services.local_style_examples import extract_local_examples
    from zipfile import ZIP_DEFLATED

    for content in ("<section><t>Evidence</t>", "a" * (MAX_FILE_SIZE_BYTES + 1)):
        buffer = BytesIO()
        with ZipFile(buffer, 'w', compression=ZIP_DEFLATED) as archive:
            archive.writestr('Contents/section0.xml', content)
        with pytest.raises(AttachmentError):
            extract_local_examples('source.hwpx', buffer.getvalue())


@pytest.mark.parametrize("filename,raw", [
    ("empty.txt", b" \n"), ("bad.docx", b"bad"), ("bad.pdf", b"bad"),
    ("image.png", b"image"), ("nested.zip", b"zip"), ("legacy.hwp", b"hwp"),
])
def test_invalid_input_has_no_examples(client, filename, raw):
    profile_id = client.post("/styles", json={"name": "Invalid"}).json()["profile_id"]
    response = client.post(f"/styles/{profile_id}/import-examples", files={"files": (filename, raw)})
    assert response.status_code == 200, response.text
    assert response.json()["imported"] == []
    assert len(response.json()["failed"]) == 1
    assert client.get(f"/styles/{profile_id}").json()["examples"] == []


def test_excerpt_bounds_and_source_order():
    from app.services.local_style_examples import extract_local_examples

    text = "\n".join(f"{i}:" + "a" * 1100 for i in range(12))
    samples = extract_local_examples("sample.md", text.encode())
    assert len(samples) == 8
    assert all(0 < len(sample) <= 1000 and sample in text for sample in samples)
    assert [text.index(sample) for sample in samples] == sorted(text.index(s) for s in samples)


@pytest.mark.parametrize("extension", ["docx", "hwpx", "pdf"])
def test_real_document_parsers(extension):
    from app.services.local_style_examples import extract_local_examples

    buffer = BytesIO()
    marker = "Source evidence before conclusions."
    if extension == "docx":
        from docx import Document
        document = Document()
        document.add_paragraph(marker)
        document.save(buffer)
    elif extension == "hwpx":
        with ZipFile(buffer, "w") as archive:
            archive.writestr("Contents/section0.xml", f'<section xmlns:hp="urn:paragraph"><hp:p><hp:t>{marker}</hp:t></hp:p></section>')
    else:
        buffer.write(_pdf_bytes(marker))
    assert marker in extract_local_examples(f"source.{extension}", buffer.getvalue())


def test_empty_pdf_and_file_size():
    from app.services.attachment_service import AttachmentError, MAX_FILE_SIZE_BYTES
    from app.services.local_style_examples import extract_local_examples
    with pytest.raises(AttachmentError):
        extract_local_examples("scan.pdf", _pdf_bytes(""))
    with pytest.raises(AttachmentError):
        extract_local_examples("big.txt", b"a" * (MAX_FILE_SIZE_BYTES + 1))


def _pdf_bytes(text):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.route("**/*", lambda route: route.abort())
        page.set_content("<p>" + text + "</p>")
        raw = page.pdf()
        browser.close()
        return raw
