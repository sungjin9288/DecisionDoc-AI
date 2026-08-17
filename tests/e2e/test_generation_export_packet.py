from __future__ import annotations

import hashlib


def _stub_export_response(page, *, content: bytes, headers: dict[str, str]) -> None:
    page.evaluate(
        """({ content, headers }) => {
            window.fetch = async () => new Response(new Uint8Array(content), {
                status: 200,
                headers,
            });
        }""",
        {"content": list(content), "headers": headers},
    )


def _packet_headers(packet_sha256: str) -> dict[str, str]:
    return {
        "Content-Type": "application/zip",
        "X-DecisionDoc-Export-Packet-SHA256": packet_sha256,
        "X-DecisionDoc-Export-Manifest-SHA256": "a" * 64,
        "X-DecisionDoc-Export-Verified": "true",
        "X-DecisionDoc-Operational-Approval": "false",
    }


def test_generation_export_packet_downloads_only_after_browser_hash_verification(page):
    packet = b"browser-verified-export-packet"
    packet_sha256 = hashlib.sha256(packet).hexdigest()
    _stub_export_response(page, content=packet, headers=_packet_headers(packet_sha256))
    downloads = []
    page.on("download", lambda download: downloads.append(download))

    with page.expect_download() as download_info:
        page.evaluate("exportZip('browser-packet-source')")

    download = download_info.value
    assert downloads == [download]
    assert download.suggested_filename == f"decisiondoc-export-{packet_sha256}.zip"


def test_generation_export_packet_browser_fails_closed_before_download(page):
    packet = b"browser-fail-closed-packet"
    packet_sha256 = hashlib.sha256(packet).hexdigest()
    downloads = []
    page.on("download", lambda download: downloads.append(download))

    missing_evidence = _packet_headers(packet_sha256)
    missing_evidence.pop("X-DecisionDoc-Export-Verified")
    cases = [
        (packet, missing_evidence),
        (packet, {**_packet_headers(packet_sha256), "X-DecisionDoc-Operational-Approval": "true"}),
        (packet, _packet_headers("0" * 64)),
    ]
    for content, headers in cases:
        _stub_export_response(page, content=content, headers=headers)
        page.evaluate("exportZip('browser-packet-source')")
        page.wait_for_timeout(75)
        assert downloads == []

    _stub_export_response(page, content=packet, headers=_packet_headers(packet_sha256))
    page.evaluate(
        """() => {
            const subtle = crypto.subtle;
            window.__generationExportPacketDigestDescriptor =
                Object.getOwnPropertyDescriptor(subtle, 'digest') || null;
            Object.defineProperty(subtle, 'digest', {
                configurable: true,
                value: async () => { throw new Error('forced crypto failure'); },
            });
        }"""
    )
    try:
        page.evaluate("exportZip('browser-packet-source')")
        page.wait_for_timeout(75)
        assert downloads == []
    finally:
        page.evaluate(
            """() => {
                const subtle = crypto.subtle;
                const descriptor = window.__generationExportPacketDigestDescriptor;
                if (descriptor) Object.defineProperty(subtle, 'digest', descriptor);
                else delete subtle.digest;
                delete window.__generationExportPacketDigestDescriptor;
            }"""
        )
