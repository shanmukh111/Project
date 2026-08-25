# Responsible AI Impact Assessment

**AI Impact Assessment — Release Gate**
MAQ Intelligent Client Delivery Agent — Prepared 2026-08-23
Companion document: `3_Security_Checklist.md` (STRIDE)

## 1. System Overview

See `3_Security_Checklist.md`, Section 1 — identical for both documents.

## 2. RAI Assessment

| RAI area | Risk | Mitigation | Evidence | Status |
|---|---|---|---|---|
| Groundedness / accuracy | Medium | Analyst agent instructions explicitly forbid introducing sprint, project-status, or timesheet facts not present in the supplied evidence, and forbid recommendations not grounded in either the evidence or curated guidance | `agents/analyst_instructions.py` | Pass |
| Reliability & safety | Low | `health_status`, `completion_percent`, and related numeric fields are computed deterministically server-side; the model is instructed never to override them, only narrate | `mcp_server/devops_server.py`; `3_Security_Checklist.md`, Tampering row | Pass |
| Consistency across identical evidence | Medium | Not yet enforced — repeated runs against the same underlying data can produce different field labels and different risk-severity framing, since the model has no fixed worked example for every evidence shape (confirmed for SharePoint-only answers specifically) | Observed directly in this review across three live runs of the same question | Partial — add a worked example per evidence shape (SharePoint-only, Timesheets-only, mixed) to the analyst instructions |
| Privacy & security | Medium | PII masked before reaching the model (`security/pii_filter.py`); prompt-injection guard on incoming questions (`security/prompt_guard.py`) | `3_Security_Checklist.md` | Pass |
| Transparency | Low | Every answer distinguishes factual evidence from assessment/interpretation from recommendations, per the analyst agent's formatting rules; a report link to the full detail is included when available | `agents/analyst_instructions.py` | Pass |
| Graceful degradation | Medium | If both retrieval attempts fail, the workflow returns explicit `unavailable` status text rather than fabricating an answer — however, a session left corrupted by a prior failure will fail *every* subsequent question until restarted, which is a real availability gap, not a groundedness one | `orchestration/evidence_validation.py`; the session-persistence bug in `3_Security_Checklist.md` | Partial — see the Denial of Service row in the security checklist |
| Human oversight | Low | Manual publish step required in Copilot Studio before any tool/flow change reaches users; this document's own sign-off | — | Pass |
| Accountability | Medium | Named engineering owner; server-side logging of tool calls, source usage, and retrieval/analyst status on every run (visible in the uvicorn console log) | Backend logs reviewed live during this session | Partial — logs are console-only today, not persisted or centrally aggregated |
| Monitoring | Low | No centralized monitoring/alerting configured yet — issues (rate limits, session corruption) were caught by manually reading console output, not by an alert | — | Gap — consider Application Insights or equivalent before relying on this for real operations beyond a demo |

## 3. Sign-Off

| Role | Name | Decision | Date | Comments |
|---|---|---|---|---|
| Engineering owner | Shanmukha Srinivas Regidi | Approve / Reject | | |
| RAI / Risk | | Approve / Reject | | |
