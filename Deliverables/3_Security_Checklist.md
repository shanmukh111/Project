# Security Assessment

**STRIDE Threat Model — Release Gate**
MAQ Intelligent Client Delivery Agent — Prepared 2026-08-23

## 1. System Overview

| Field | Value |
|---|---|
| AI system / agent name | MAQ Intelligent Client Delivery Agent |
| Owner | Shanmukha Srinivas Regidi (shanmukha.regidi@maqsoftware.com) |
| Business purpose | Answers delivery-manager questions and generates delivery health reports over Microsoft Teams, sourced from Azure DevOps, SharePoint, and D365 timesheet data |
| Users | Internal delivery managers, identified by work email |
| Data accessed | Azure DevOps sprint/work-item data (live), SharePoint project register (passed in via the Copilot Studio flow), D365 timesheet data (local CSV export) |
| Tools/actions available | A single Copilot Studio tool (`Generate Delivery Health Report`) backed by one Power Automate flow calling `POST /delivery/query`, which internally runs a two-agent pipeline: a data retrieval agent (SharePoint/Timesheets direct, Azure DevOps via an MCP subprocess) and an insight agent (hybrid RAG over curated delivery guidance) |
| Deployment environment | FastAPI service on OpenAI (model configurable via `OPENAI_MODEL`), exposed via a temporary devtunnel for the Teams/Copilot Studio demo |
| Risk classification | **Low–Medium** — internal capstone demo, no external customer data, temporary tunnel exposure |

## 2. STRIDE Security Assessment

| Threat | STRIDE | Scenario | Impact | Likelihood | Mitigation | Status |
|---|---|---|---|---|---|---|
| User impersonation | Spoofing | Caller claims to be a different manager | Medium | Low | `userId` is bound to `User.Email`, a platform-resolved value from the Copilot Studio/Teams identity — not a free-text field the caller can type | Mitigated at the Copilot Studio layer; server-side re-verification not confirmed in this review |
| Health status manipulation | Tampering | A crafted question tries to get the model to report a different health status than the underlying sprint data supports | Medium | Low | `health_status`, `completion_percent`, and related fields are computed deterministically in `mcp_server/devops_server.py`; the analyst agent's instructions explicitly forbid overriding these — it may only narrate | Mitigated |
| PII exposure in requests or logs | Tampering / Information Disclosure | A question or response accidentally carries personally identifiable information | Medium | Low | `security/pii_filter.py` (Presidio) detects and masks PII before the request reaches the model | Mitigated |
| Prompt injection | Tampering | A crafted question tries to override system instructions or make the model ignore its authorization scope | High | Low | `security/prompt_guard.py` validates the incoming question before it's used; the analyst agent's own instructions forbid narrating anything not present in the supplied evidence | Mitigated |
| Response leaking implementation details | Information Disclosure | The model's answer reveals internal tool names, backend URLs, or raw exception traces | Medium | Low | `security/output_filter.py` (`redact_secrets`) strips secrets from output; the Copilot Studio system prompt separately forbids exposing tool names, backend URLs, or auth details | Mitigated |
| Answer referencing a source that was never actually queried | Information Disclosure / Groundedness | Analyst agent's narrative mentions a data source (e.g. Azure DevOps) that wasn't part of this question's evidence | Medium | Low | `security/output_filter.py`'s `filter_out_of_scope_sources` strips sentences referencing a source not in `sources_used` for this request | Mitigated |
| Report link accessed by someone other than the requester | Information Disclosure | Report HTML/PNG files are served from `/reports/{id}.html` as plain, clickable links (by design, for chat rendering) | Medium | Medium | Report IDs are UUIDs (not sequential/guessable); path traversal protection on the `report_id` path parameter was not verified in this review | Open — verify path resolution is constrained to the reports directory before wider exposure than the current temporary devtunnel |
| Session-state corruption from a transient upstream failure | Denial of Service (per-user) | A rate-limited or otherwise failed OpenAI call mid-conversation leaves the persisted agent session holding a dangling tool call | High | Medium | Found in this review — `_save_agent_session` in `delivery_workflow.py` currently persists the session unconditionally, even after a failed retrieval; every later question from that user then fails identically until the process restarts | Open — fix identified (only persist on success), not yet confirmed deployed |
| No request throttling | Denial of Service | One user's burst of requests degrades the backend for everyone else, or runs up API cost | Medium | Low | No rate limiting implemented; an in-flight request tracker (dedupe on requests already running, not just completed ones) was designed in this review to reduce duplicate-run waste from Copilot Studio's own retry behavior | Open |
| Unauthorized data access via the agent | Elevation of Privilege | The model is prompted to access or reveal a project/source outside the caller's authorization | High | Low | Retrieval tool access is scoped per source and gated through the retrieval agent's own tool-selection instructions; `userId` is bound server-side from the platform-resolved `User.Email`, not a model-fillable argument | Mitigated |

## 3. Sign-Off

| Role | Name | Decision | Date | Comments |
|---|---|---|---|---|
| Engineering owner | Shanmukha Srinivas Regidi | Approve / Reject | | |
| Security | | Approve / Reject | | |
