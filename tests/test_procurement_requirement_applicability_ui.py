"""Static Step8 browser contracts; no app, server, provider or stored data access."""
import json
from pathlib import Path
import re
import subprocess


HTML = (Path(__file__).resolve().parents[1] / "app/static/index.html").read_text(encoding="utf-8")


def function_source(name):
    start = re.search(rf"^  (?:async )?function {name}\(", HTML, re.M).start()
    end = re.search(r"^  }$", HTML[start:], re.M).end() + start
    return HTML[start:end]


def run_javascript(source):
    result = subprocess.run(["node", "-"], input=source, text=True, capture_output=True, check=True)
    return json.loads(result.stdout)


def procurement_memory_source():
    """Run production functions with in-memory DOM/network boundaries only."""
    constants = HTML[HTML.index("  const PROCUREMENT_REQUIREMENT_CATEGORIES"):HTML.index("  function invalidateProcurementRequirements")]
    functions = (
        "captureProcurementReviewRequestContext", "isProcurementReviewRequestCurrent",
        "isProcurementRequirementsCurrent", "canEditProcurementRequirements",
        "invalidateProcurementRequirements", "setProcurementRequirementsFailure",
        "renderProcurementRequirements", "procurementRequirementsBase", "procurementRequirementsQuery",
        "loadProcurementRequirements", "procurementScopeQuery", "refreshProcurementRequestView",
        "downloadProjectProcurementReviewPacket", "submitProcurementRequirement",
    )
    return constants + "\n".join(function_source(name) for name in functions) + """
let _authSessionRevision = 4, _currentTenantId = 'tenant-a', _projectDetailLoadId = 7;
let _currentUser = {sub: 'user-a', username: 'reviewer-a', role: 'admin'};
let _currentProjectDetail = {project: {project_id: 'project-a'}, procurementEnabled: true,
  procurementDecision: {decision_id: 'decision-a', opportunity: {}, recommendation: {value: 'GO'}},
  procurementDecisionRevision: 3, procurementSelection: {selection_revision: 2}};
let _procurementRequirementsState = null, _procurementReviewPacketPending = false;
const button = {disabled: false, textContent: '검토 패킷 ZIP'};
const reviewer = {value: 'explicit-reviewer', focus() {}};
const section = {hidden: true, innerHTML: '', querySelectorAll() {return [];},
  replaceChildren() {this.innerHTML = '';}};
const formStatus = {textContent: ''};
const form = {querySelectorAll() {return [button];}, querySelector() {return formStatus;}};
const document = {getElementById(id) {
  if (id === 'project-procurement-requirements') return section;
  if (id === 'project-procurement-reviewer-input') return reviewer;
  return button;
}};
const $id = id => document.getElementById(id);
const escapeHtml = String;
const localStorage = {getItem() {return 'test-token';}};
const readAccessTokenClaims = () => ({role: 'admin', session_id: 'a'.repeat(32)});
const getAuthHeaders = () => ({Authorization: 'test-session'});
const resolveApiErrorResponse = async () => ({code: 'denied', message: 'Denied'});
const getProcurementErrorMessage = (_code, message) => message;
const PROCUREMENT_REVIEW_DOWNLOAD_SCOPE = 'review';
const downloads = [], statuses = [], notifications = [], requests = [], revoked = [];
const _clearScopedExportDownloadUrls = scope => revoked.push(scope);
const _filenameFromContentDisposition = () => 'packet-a.zip';
const _triggerBrowserDownload = blob => downloads.push(blob.bytes);
const setProcurementActionStatus = (text, kind) => statuses.push({text, kind});
const showNotification = (text, kind) => notifications.push({text, kind});
function readyState() {
  return {context: captureProcurementReviewRequestContext(), revision: 3, status: 'ready',
    requirements: [], exportAvailable: true, pending: false, editor: null};
}
let readStatus = 404, postStatus = 200;
async function fetch(url, options) {
  requests.push({url, ...options});
  const status = options.method === 'POST' ? postStatus : readStatus;
  return {status, ok: status === 200,
    headers: {get: name => name === 'Content-Type' ? 'application/zip'
      : name === 'X-DecisionDoc-Operational-Approval' ? 'false' : ''},
    blob: async () => ({bytes: 'packet-a'})};
}
async function loadProjectDetail() {
  _projectDetailLoadId += 1;
  invalidateProcurementRequirements();
  _procurementRequirementsState = readyState();
}
"""


def test_requirement_denial_restores_explicit_selfprepare_but_not_unauthenticated_access():
    for read_status, post_status, recommended in ((403, 200, True), (404, 200, True),
                                                 (404, 404, True), (404, 401, True),
                                                 (401, 200, True), (404, 200, False)):
        source = procurement_memory_source()
        source += f"\nreadStatus = {read_status}; postStatus = {post_status};\n"
        if not recommended:
            source += "_currentProjectDetail.procurementDecision.recommendation = null;\n"
        source += """
(async () => {
  await loadProcurementRequirements();
  const afterRead = {disabled: button.disabled, hidden: section.hidden,
    state: _procurementRequirementsState, label: button.textContent};
  const beforeClick = requests.length;
  await Promise.all([downloadProjectProcurementReviewPacket('project-a'),
    downloadProjectProcurementReviewPacket('project-a')]);
  console.log(JSON.stringify({afterRead, beforeClick, downloads,
    posts: requests.filter(item => item.method === 'POST'), disabled: button.disabled}));
})().catch(error => {console.error(error); process.exitCode = 1;});
"""
        result = run_javascript(source)
        allowed = read_status != 401 and recommended
        assert result["afterRead"] == {"disabled": not allowed, "hidden": True,
                                       "state": None, "label": "검토 패킷 ZIP"}
        assert result["beforeClick"] == 1  # Reading never automatically prepares a packet.
        assert len(result["posts"]) == int(allowed)  # Double click stays single-flight.
        assert result["downloads"] == (["packet-a"] if allowed and post_status == 200 else [])
        if allowed:
            assert json.loads(result["posts"][0]["body"]) == {"reviewer": "explicit-reviewer"}
            assert "/procurement/review-packet?decision_id=decision-a&expected_decision_revision=3" in result["posts"][0]["url"]
            assert result["disabled"] is (post_status == 401)


def test_refresh_return_race_cannot_download_or_announce_write_in_another_context():
    mutations = {
        "unchanged": "",
        "auth": "_authSessionRevision += 1;",
        "tenant": "_currentTenantId = 'tenant-b';",
        "user": "_currentUser = {..._currentUser, sub: 'user-b'};",
        "project": "_currentProjectDetail.project.project_id = 'project-b';",
        "decision": "_currentProjectDetail.procurementDecision.decision_id = 'decision-b';",
        "selection": "_currentProjectDetail.procurementSelection.selection_revision += 1;",
        "load": "_projectDetailLoadId += 1;",
    }
    for operation in ("export", "write"):
        for mutation in mutations.values():
            source = procurement_memory_source() + """
_procurementRequirementsState = readyState();
const state = _procurementRequirementsState;
const editor = {requirement: null};
const originalGuard = isProcurementReviewRequestCurrent;
let injected = false;
isProcurementReviewRequestCurrent = context => {
  const current = originalGuard(context);
  // Enqueue drift after the helper computes true, before its awaiting caller resumes.
  if (current && context.projectDetailLoadId === 8 && !injected) {
    injected = true;
    queueMicrotask(() => {
""" + mutation + """
      _procurementRequirementsState = readyState();
    });
  }
  return current;
};
(async () => {
"""
            if operation == "export":
                source += "await downloadProjectProcurementReviewPacket('project-a');\n"
            else:
                source += "state.editor = editor; await submitProcurementRequirement(state, editor, {}, form);\n"
            source += """
  console.log(JSON.stringify({injected, downloads, posts: requests.length,
    successes: statuses.filter(item => item.kind === 'success').length,
    notifications: notifications.filter(item => item.kind === 'success').length}));
})().catch(error => {console.error(error); process.exitCode = 1;});
"""
            result = run_javascript(source)
            assert result["injected"] is True
            assert result["posts"] == 1
            assert result["downloads"] == (["packet-a"] if not mutation and operation == "export" else [])
            assert result["successes"] == int(not mutation)
            assert result["notifications"] == int(not mutation and operation == "export")


def test_export_access_loss_clears_private_section_without_permanently_locking_selfprepare():
    for status in (401, 403, 404):
        source = procurement_memory_source() + f"\npostStatus = {status};\n" + """
_procurementRequirementsState = readyState();
section.hidden = false;
section.innerHTML = 'private requirement history';
(async () => {
  await downloadProjectProcurementReviewPacket('project-a');
  console.log(JSON.stringify({hidden: section.hidden, content: section.innerHTML,
    state: _procurementRequirementsState, disabled: button.disabled, downloads,
    pending: _procurementReviewPacketPending, count: requests.length, revoked: revoked.length}));
})().catch(error => {console.error(error); process.exitCode = 1;});
"""
        assert run_javascript(source) == {
            "hidden": True, "content": "", "state": None, "disabled": status == 401,
            "downloads": [], "pending": False, "count": 1, "revoked": 1,
        }


def test_requirement_reads_are_opt_in_scoped_and_revision_checked():
    load = function_source("loadProcurementRequirements")
    for guard in ("detail?.procurementEnabled", "!detail.procurementSelection", "['admin', 'member']",
                  "Number.isSafeInteger(detail.procurementDecisionRevision)"):
        assert guard in load
    assert "captureProcurementReviewRequestContext()" in load
    assert "cache: 'no-store'" in load
    assert load.count("if (!isProcurementRequirementsCurrent(state)) return;") >= 3
    for binding in ("payload.project_id !== state.context.projectId", "payload.decision_id !== state.context.decisionId",
                    "payload.decision_revision !== state.revision", "payload.operational_approval !== false",
                    "typeof payload.export_available !== 'boolean'", "payload.requirements.every(isProcurementRequirement)"):
        assert binding in load
    assert "/opportunities/${encodeURIComponent(state.context.decisionId)}/requirements" in function_source("procurementRequirementsBase")
    assert "expected_decision_revision: state.revision" in function_source("procurementRequirementsQuery")
    assert "await loadProcurementRequirements();" in function_source("loadProjectDetail")


def test_full_context_and_lifecycle_invalidate_sensitive_source_form():
    context = function_source("captureProcurementReviewRequestContext")
    guard = function_source("isProcurementReviewRequestCurrent")
    for key in ("authRevision", "tenantId", "userId", "projectDetailLoadId", "projectId", "decisionId", "selectionRevision"):
        assert key in context and key in guard
    assert "state === _procurementRequirementsState" in function_source("isProcurementRequirementsCurrent")
    assert "state.revision === _currentProjectDetail?.procurementDecisionRevision" in function_source("isProcurementRequirementsCurrent")
    for name in ("invalidateProcurementReviewViews", "selectProjectProcurementOpportunity", "loadProjectDetail"):
        assert "invalidateProcurementRequirements();" in function_source(name)
    for marker in ("window.switchPage =", "window.hideProjectDetail ="):
        start = HTML.index(marker)
        assert "invalidateProcurementRequirements();" in HTML[start:start + 400]
    invalidate = function_source("invalidateProcurementRequirements")
    assert "section.replaceChildren()" in invalidate
    assert "_procurementRequirementsState = null" in invalidate
    assert "_clearScopedExportDownloadUrls(PROCUREMENT_REVIEW_DOWNLOAD_SCOPE)" in invalidate


def test_late_results_fail_every_context_dimension():
    source = """
let _authSessionRevision = 4, _currentTenantId = 'tenant-a', _projectDetailLoadId = 7;
let _currentUser = {sub: 'user-a'};
let _currentProjectDetail = {project: {project_id: 'project-a'},
  procurementDecision: {decision_id: 'decision-a'}, procurementDecisionRevision: 3,
  procurementSelection: {selection_revision: 2}};
let _procurementRequirementsState;
"""
    source += function_source("captureProcurementReviewRequestContext")
    source += function_source("isProcurementReviewRequestCurrent")
    source += function_source("isProcurementRequirementsCurrent")
    source += """
const context = captureProcurementReviewRequestContext();
const state = {context, revision: 3};
_procurementRequirementsState = state;
const result = [isProcurementRequirementsCurrent(state)];
for (const key of Object.keys(context)) {
  const original = context[key];
  context[key] = typeof original === 'number' ? original + 1 : original + '-changed';
  result.push(isProcurementRequirementsCurrent(state));
  context[key] = original;
}
state.revision += 1;
result.push(isProcurementRequirementsCurrent(state));
state.revision -= 1;
_procurementRequirementsState = {...state};
result.push(isProcurementRequirementsCurrent(state));
console.log(JSON.stringify(result));
"""
    assert run_javascript(source) == [True] + [False] * 9


def test_sources_are_lazy_admin_only_and_exact_revision_bound():
    guard = function_source("canEditProcurementRequirements")
    for text in ("state.exportAvailable === true", "_currentUser?.role === 'admin'", "claims?.role === 'admin'", "claims.session_id"):
        assert text in guard
    editor = function_source("openProcurementRequirementEditor")
    source_fetch = editor.index("const response = await fetch")
    assert editor.index("if (!requirement)") < source_fetch
    assert editor.index("if (!canEditProcurementRequirements(state)) return;") < source_fetch
    assert "'/sources' + procurementRequirementsQuery(state)" in editor
    assert "payload.decision_revision !== state.revision" in editor
    assert "state.editor !== editor" in editor
    assert "/sources" not in function_source("loadProcurementRequirements")
    assert 'id="procurement-requirement-raw-text" rows="8" readonly' in editor
    assert "rawInput.selectionStart, rawInput.selectionEnd" in editor
    assert 'id="procurement-requirement-use-selection"' in editor
    assert "snapshot_sha256" not in editor[editor.index("host.innerHTML = `<form"):editor.index("const form =")]


def test_quote_selection_maps_utf16_and_normalized_newlines_to_exact_codepoints():
    source = function_source("procurementRequirementSelectedQuote")
    cases = [
        ["A\U0001f600한글", 1, 4],
        ["A\U0001f600한글", 2, 4],  # A split surrogate must never become source evidence.
        ["A\U0001f600한글", 1, 2],
        ["가\r\n\U0001f600나\r끝", 2, 6],
        ["가\r\n\U0001f600나\r끝", 0, 2],
        ["e\u0301한", 0, 2],
        ["abc", 1, 1],
    ]
    actual = run_javascript(source + "\nconsole.log(JSON.stringify(" + json.dumps(cases) + ".map(args => procurementRequirementSelectedQuote(...args))));")
    assert actual == [
        {"quote_start": 1, "quote_end": 3, "quote": "\U0001f600한"}, None, None,
        {"quote_start": 3, "quote_end": 6, "quote": "\U0001f600나\r"},
        {"quote_start": 0, "quote_end": 3, "quote": "가\r\n"},
        {"quote_start": 0, "quote_end": 2, "quote": "e\u0301"}, None,
    ]


def test_requirement_contract_rejects_unknown_states_and_false_currentness():
    constants = HTML[HTML.index("  const PROCUREMENT_REQUIREMENT_CATEGORIES"):HTML.index("  function invalidateProcurementRequirements")]
    source = constants + function_source("isProcurementRequirementQuote") + function_source("isProcurementRequirement")
    item = dict(requirement_id="requirement-1", title="Requirement", category="eligibility_and_compliance",
                snapshot_id="source-1", snapshot_sha256="a" * 64, quote_start=0, quote_end=1,
                quote="한", applicability="unknown", stale=False, annotations=[])
    candidates = [item, {**item, "applicability": "ready"}, {**item, "stale": True, "applicability": "not_applicable"},
                  {**item, "stale": True}, {**item, "quote_end": 2}, {**item, "category": "unrecognized"}]
    actual = run_javascript(source + "\nconsole.log(JSON.stringify(" + json.dumps(candidates) + ".map(isProcurementRequirement)));")
    assert actual == [True, False, False, True, False, False]


def test_history_counts_and_parent_assessments_remain_separate():
    render = function_source("renderProcurementRequirements")
    for state in ("unknown", "stale", "not_applicable"):
        assert f'data-requirement-count="{state}"' in render
    for text in ("item.annotations.map", "escapeHtml(event.rationale)", "escapeHtml(event.created_at)",
                 "escapeHtml(item.quote)", "escapeHtml(item.title)", "item.stale || state.pending || state.editor"):
        assert text in render
    assert "actor_id" not in render
    assert "created_by_actor_id" not in render
    assert "상위 체크리스트와 추천은 별도로 유지됩니다." in render
    assert "${renderProcurementSummary(procurementDecision)}" in HTML
    assert '.procurement-requirement-fields { grid-template-columns: minmax(0, 1fr); }' in HTML
    assert '<section id="project-procurement-requirements"' in HTML


def test_writes_reuse_original_quote_and_are_single_flight_without_retries():
    editor = function_source("openProcurementRequirementEditor")
    submit = function_source("submitProcurementRequirement")
    assert "const source = requirement || editor.quote;" in editor
    for field in ("snapshot_id", "snapshot_sha256", "quote_start", "quote_end", "quote"):
        assert f"{field}: source.{field}" in editor
    assert "expected_decision_revision: state.revision, operation_id: crypto.randomUUID()" in editor
    assert "state.pending || editor.requirement?.stale" in submit
    assert submit.index("state.pending = true") < submit.index("await fetch")
    assert "method: 'POST'" in submit
    assert submit.count("await fetch") == 1
    assert "/${encodeURIComponent(editor.requirement.requirement_id)}/applicability" in submit
    assert "if (!await refreshProcurementRequestView(state.context.projectId, state.context)) return;" in submit
    assert submit.index("refreshProcurementRequestView") < submit.index("setProcurementActionStatus")


def test_access_denial_hides_section_and_errors_require_explicit_refresh():
    failure = function_source("setProcurementRequirementsFailure")
    assert "[401, 403, 404].includes(status)" in failure
    assert "invalidateProcurementRequirements();" in failure
    assert "state.status = 'error'" in failure
    assert "state.editor = null" in failure
    assert "state.exportAvailable = false" in failure
    assert "status === 409" in failure
    assert "새로고침" in failure
    assert "fetch(" not in failure
    assert "loadProjectDetail(" not in failure
    assert 'data-requirement-action="refresh"' in function_source("renderProcurementRequirements")


def test_export_reuses_explicit_reviewer_post_and_rechecks_before_download():
    export = function_source("downloadProjectProcurementReviewPacket")
    assert "/procurement/review-packet${procurementScopeQuery()}" in export
    assert "const reviewer = reviewerInput.value.trim();" in export
    assert "body: JSON.stringify({ reviewer })" in export
    assert "method: 'POST'" in export
    assert "_procurementReviewPacketPending" in export
    assert "requirements.exportAvailable" in export
    assert "setProcurementRequirementsFailure(requirements, res.status, true)" in export
    assert "application/zip" in export
    assert "X-DecisionDoc-Operational-Approval" in export
    assert export.index("await res.blob()") < export.index("await refreshProcurementRequestView") < export.index("_triggerBrowserDownload")
    assert "decisionRevision !== _currentProjectDetail?.procurementDecisionRevision" in export
    assert "scope: PROCUREMENT_REVIEW_DOWNLOAD_SCOPE" in export
    assert "요구사항 포함 검토 패키지" in function_source("renderProcurementRequirements")
    assert "/requirements/export" not in HTML
    assert "'/export'" not in function_source("loadProcurementRequirements")
    assert "URL.revokeObjectURL(entry.url)" in function_source("_clearScopedExportDownloadUrls")


def test_inline_javascript_parses_without_running_app():
    scripts = re.findall(r"<script(?:\s[^>]*)?>(.*?)</script>", HTML, re.S)
    result = run_javascript("const vm = require('node:vm'); const scripts = " + json.dumps(scripts)
                            + "; for (const script of scripts) new vm.Script(script); console.log(JSON.stringify(scripts.length));")
    assert result > 0
