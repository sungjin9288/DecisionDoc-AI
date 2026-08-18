from __future__ import annotations

import hashlib


def _stub_export_response(
    page, *, content: bytes, headers: dict[str, str], status: int = 200
) -> None:
    page.evaluate(
        """({ content, headers, status }) => {
            window.fetch = async () => new Response(new Uint8Array(content), {
                status,
                headers,
            });
        }""",
        {"content": list(content), "headers": headers, "status": status},
    )


def _packet_headers(packet_sha256: str) -> dict[str, str]:
    return {
        "Content-Type": "application/zip",
        "X-DecisionDoc-Export-Packet-SHA256": packet_sha256,
        "X-DecisionDoc-Export-Manifest-SHA256": "a" * 64,
        "X-DecisionDoc-Export-Verified": "true",
        "X-DecisionDoc-Operational-Approval": "false",
    }


def _render_project_export_action(page, request_id: str = "project-packet-source") -> None:
    page.evaluate(
        """requestId => {
            renderProjectDetail({
                project_id: 'project-export',
                name: 'Export Project',
                fiscal_year: 2026,
                documents: [
                    {
                        doc_id: 'project-document-export',
                        request_id: requestId,
                        bundle_id: 'tech_decision',
                        title: 'Ignored client title',
                        generated_at: '2026-08-17T00:00:00Z',
                    },
                    {
                        doc_id: 'project-document-without-request',
                        request_id: '',
                        bundle_id: 'tech_decision',
                        title: 'No review ZIP',
                        generated_at: '2026-08-17T00:00:00Z',
                    },
                ],
            });
        }""",
        request_id,
    )


def _defer_export_response(page) -> None:
    page.evaluate(
        """() => {
            window.__generationExportFetchCalls = 0;
            window.__generationExportUrls = [];
            window.fetch = url => {
                window.__generationExportFetchCalls += 1;
                window.__generationExportUrls.push(String(url));
                return new Promise(resolve => { window.__resolveGenerationExport = resolve; });
            };
        }"""
    )


def _resolve_deferred_export(page, *, content: bytes, headers: dict[str, str], status: int = 200) -> None:
    page.evaluate(
        """({ content, headers, status }) => {
            window.__resolveGenerationExport(new Response(new Uint8Array(content), { status, headers }));
        }""",
        {"content": list(content), "headers": headers, "status": status},
    )


def test_generation_export_packet_result_action_uses_exact_five_format_query_and_downloads_after_verification(page):
    packet = b"browser-verified-export-packet"
    packet_sha256 = hashlib.sha256(packet).hexdigest()
    page.evaluate(
        """({ content, headers }) => {
            window.__generationExportUrls = [];
            window.fetch = async url => {
                window.__generationExportUrls.push(String(url));
                return new Response(new Uint8Array(content), { status: 200, headers });
            };
        }""",
        {"content": list(packet), "headers": _packet_headers(packet_sha256)},
    )
    page.evaluate("renderDownloadButtons('browser-packet-source', 'Ignored client title')")
    downloads = []
    page.on("download", lambda download: downloads.append(download))

    with page.expect_download() as download_info:
        page.locator("[data-result-export-zip]").dispatch_event("click")

    download = download_info.value
    assert downloads == [download]
    assert download.suggested_filename == f"decisiondoc-export-{packet_sha256}.zip"
    assert page.evaluate("window.__generationExportUrls") == [
        "/generate/export-zip?request_id=browser-packet-source&formats=docx,pdf,pptx,hwp,excel"
    ]


def test_generation_export_packet_project_action_is_request_bound_single_flight_and_ignores_missing_request_id(page):
    packet = b"browser-project-verified-export-packet"
    packet_sha256 = hashlib.sha256(packet).hexdigest()
    _render_project_export_action(page)
    assert page.locator('[data-project-detail-action="doc-verified-review-export"]').count() == 1
    assert page.locator('[data-project-doc-id="project-document-without-request"] [data-project-detail-action="doc-verified-review-export"]').count() == 0

    _defer_export_response(page)
    button = page.locator('[data-project-detail-action="doc-verified-review-export"]')
    page.evaluate(
        """() => {
            const action = document.querySelector(
                '[data-project-detail-action="doc-verified-review-export"]'
            );
            action.click();
            action.dispatchEvent(new MouseEvent('click', { bubbles: true }));
        }"""
    )
    assert page.evaluate("window.__generationExportFetchCalls") == 1
    assert page.evaluate("window.__generationExportUrls") == [
        "/generate/export-zip?request_id=project-packet-source&formats=docx,pdf,pptx,hwp,excel"
    ]
    assert button.is_disabled()

    downloads = []
    page.on("download", lambda download: downloads.append(download))
    with page.expect_download() as download_info:
        _resolve_deferred_export(page, content=packet, headers=_packet_headers(packet_sha256))

    download = download_info.value
    assert downloads == [download]
    assert download.suggested_filename == f"decisiondoc-export-{packet_sha256}.zip"
    assert not button.is_disabled()


def test_generation_export_packet_project_context_drift_discards_response_before_blob_or_download(page):
    packet = b"browser-project-stale-export-packet"
    packet_sha256 = hashlib.sha256(packet).hexdigest()
    _render_project_export_action(page)
    _defer_export_response(page)
    page.evaluate(
        """() => {
            window.__generationExportObjectUrlCalls = 0;
            window.__generationExportOriginalCreateObjectURL = URL.createObjectURL;
            URL.createObjectURL = value => {
                window.__generationExportObjectUrlCalls += 1;
                return window.__generationExportOriginalCreateObjectURL.call(URL, value);
            };
        }"""
    )
    downloads = []
    page.on("download", lambda download: downloads.append(download))
    page.locator('[data-project-detail-action="doc-verified-review-export"]').dispatch_event("click")
    page.evaluate("window.hideProjectDetail()")
    _resolve_deferred_export(page, content=packet, headers=_packet_headers(packet_sha256))
    page.wait_for_timeout(100)

    assert downloads == []
    assert page.evaluate("window.__generationExportObjectUrlCalls") == 0
    page.evaluate(
        """() => {
            URL.createObjectURL = window.__generationExportOriginalCreateObjectURL;
            delete window.__generationExportOriginalCreateObjectURL;
        }"""
    )


def test_generation_export_packet_project_source_failure_guidance_is_non_disclosing(page):
    _render_project_export_action(page)
    downloads = []
    page.on("download", lambda download: downloads.append(download))
    source_missing = {"Content-Type": "application/json"}
    _stub_export_response(
        page,
        content=b'{"code":"EXPORT_SOURCE_NOT_FOUND","message":"secret source"}',
        headers=source_missing,
        status=404,
    )
    page.locator('[data-project-detail-action="doc-verified-review-export"]').dispatch_event("click")
    page.wait_for_timeout(100)
    assert downloads == []
    assert page.evaluate("document.body.textContent.includes('문서를 다시 생성한 뒤 검토 ZIP을 요청하세요.')")
    assert not page.evaluate("document.body.textContent.includes('secret source')")

    _stub_export_response(
        page,
        content=b'{"code":"EXPORT_SOURCE_UNAVAILABLE","message":"secret unavailable"}',
        headers=source_missing,
        status=503,
    )
    page.locator('[data-project-detail-action="doc-verified-review-export"]').dispatch_event("click")
    page.wait_for_timeout(100)
    assert downloads == []
    assert not page.evaluate("document.body.textContent.includes('secret unavailable')")

    page.evaluate(
        "() => { window.fetch = async () => { throw new Error('secret fetch failure'); }; }"
    )
    page.locator('[data-project-detail-action="doc-verified-review-export"]').dispatch_event("click")
    page.wait_for_timeout(100)
    assert downloads == []
    assert not page.evaluate("document.body.textContent.includes('secret fetch failure')")


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
        (packet, {**_packet_headers(packet_sha256), "X-DecisionDoc-Export-Manifest-SHA256": "invalid"}),
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
