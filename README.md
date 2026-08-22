# MAQ Intelligent Client Delivery Agent

An enterprise-style, multi-agent delivery intelligence solution built for MAQ Software using Microsoft Agent Framework (MAF), FastAPI, Azure DevOps MCP, SharePoint, D365 Project Operations timesheets, Hybrid RAG, and Microsoft Copilot Studio.

The solution helps delivery managers ask natural-language questions about project health, sprint delivery, utilization, risks, and recommended actions. A single retrieval agent gathers grounded evidence from up to three enterprise sources based on what the question actually needs, an orchestrator agent synthesizes a management-facing answer, and the backend deterministically generates supporting charts and a downloadable report.

---

## Solution Overview

```text
User / Copilot Studio
        |
        v
FastAPI Orchestrator
        |
        +--> PII Masking
        +--> Prompt Injection Guard
        +--> Authorization (email allowlist)
        |
        v
   MAQDataRetrievalAgent
        |
        +-------------+-------------+
        |             |             |
        v             v             v
  SharePoint     Azure DevOps   Timesheet
    Tool             Tool          Tool
  (project        (live sprint   (local D365
   register,        + work        CSV export)
   flow-supplied)    items)
        |             |             |
        +-------------+-------------+
                        |
                        v
                Evidence Validation
                 Retry / Fallback
                        |
                        v
              MAQDeliveryAnalystAgent  <---  Hybrid RAG
                        |                (Knowledge Base,
                        |                 called only if the
                        |                 question needs guidance)
                        v
               Grounded Final Answer
                        |
                        v
              Output Secret Redaction
                        |
                        v
        Deterministic Chart + Report
           Generation (matplotlib)
```

### Agent Responsibilities

**MAQDataRetrievalAgent**
- The only evidence-gathering agent. Chooses which of the three tools below a question needs - there is no deterministic pre-routing step; tool selection is the agent's own reasoning, guided by few-shot instructions.
- **SharePoint tool** - reads the project register rows the Copilot Studio flow already fetched from an Excel table in SharePoint and passed in with the request. Does not make a live SharePoint call itself.
- **Azure DevOps tool (MCP)** - live sprint summary, named-iteration lookup, active work items, project info, iteration dates. Includes effort hours (planned/completed/remaining) alongside work-item counts.
- **Timesheet tool** - reads a local D365 Project Operations timesheet export (CSV) for planned vs. actual vs. billable hours, approval status, and utilization.
- Can call more than one tool in the same turn when a question genuinely spans sources.
- Never generates the final answer or any recommendation - that's the Analyst's job.
- Transcribes deterministic Azure DevOps numbers (completion %, sprint-elapsed %, health status) exactly as returned - never recalculates them.

**MAQDeliveryAnalystAgent (Insight Orchestrator)**
- Receives validated evidence from the Data Retrieval Agent. Has no direct access to live data sources.
- Has its own tool: Hybrid RAG (`search_delivery_knowledge`) over curated delivery guidance - used only when the question asks for interpretation or recommendations, not for facts.
- Synthesizes the final management-facing answer: factual evidence, interpretation, and (only when supported) recommendations.
- Never overrides a deterministic classification supplied in the evidence.

---

## Key Capabilities

- Two-agent orchestration with Microsoft Agent Framework
- Agent-driven (not deterministic) tool selection across three evidence sources, with multi-tool calls in a single turn where relevant
- Structured evidence with Pydantic models, including numeric fields the backend uses to render charts deterministically
- Azure DevOps integration through FastMCP, including per-work-item effort tracking (Original Estimate / Completed Work / Remaining Work)
- SharePoint project-register ingestion via the Copilot Studio flow (no live SharePoint call from the backend)
- D365 Project Operations timesheet analysis from a local CSV export
- Hybrid RAG using semantic search + BM25, available to the Analyst agent for guidance and recommendations
- Email-allowlist authorization (Teams SSO identity via Copilot Studio's `User.Email`, not a self-declared identity string)
- PII detection and masking with Microsoft Presidio
- Prompt-injection protection
- Output secret redaction
- Evidence validation with retry and graceful fallback
- Source tracking for grounded responses
- Deterministic chart generation (work-item status pie chart, effort bar chart) and a self-contained HTML report, served back to Copilot Studio as absolute URLs
- Per-user conversational memory (MAF `AgentSession`/`SessionStore`), keyed on the authorized email
- Copilot Studio integration for Microsoft Teams-facing interaction

---

## Technology Stack

| Area | Technology |
|---|---|
| Agent orchestration | Microsoft Agent Framework |
| API layer | FastAPI |
| Agent model client | OpenAI client through Agent Framework |
| MCP | FastMCP |
| Engineering data | Azure DevOps (live REST API via MCP) |
| Portfolio data | SharePoint (Excel table, fetched by the Copilot Studio flow) |
| Timesheet data | D365 Project Operations export (local CSV) |
| Retrieval | LlamaIndex + ChromaDB + BM25 |
| Embeddings | sentence-transformers/all-MiniLM-L6-v2 |
| Charts / reports | matplotlib |
| PII protection | Microsoft Presidio |
| Validation | Pydantic |
| Front-end / user interaction | Microsoft Copilot Studio |
| Source control | GitHub |
| ALM / CI-CD | Azure DevOps Pipelines |

---

## Repository Structure

```text
maq-client-delivery-agent/
├── agents/
│   ├── analyst_agent.py
│   ├── analyst_instructions.py
│   ├── analyst_tools.py          <- Hybrid RAG tool (Analyst's only tool)
│   ├── engineering_agent.py
│   ├── engineering_instructions.py
│   └── engineering_tools.py      <- SharePoint + Timesheet tools
│
├── apps/
│   └── api/
│       └── main.py
│
├── connectors/
│   └── d365_timesheet.py         <- local CSV reader, path via D365_TIMESHEETS_PATH
│
├── data/
│   ├── d365/                     <- fallback/sample timesheet CSV
│   ├── knowledge/                <- Hybrid RAG source documents
│   └── sharepoint/                <- fallback/sample project register CSV
│
├── mcp_server/
│   └── devops_server.py
│
├── orchestration/
│   ├── delivery_workflow.py
│   ├── evidence_models.py
│   ├── evidence_validation.py
│   ├── prompts.py
│   └── routing.py                <- currently unused; see note below
│
├── reporting/
│   └── charts.py                 <- deterministic chart + HTML report generation
│
├── retrieval/
│   └── hybrid_rag.py
│
├── security/
│   ├── authorization.py          <- flat email allowlist
│   ├── output_filter.py
│   ├── pii_filter.py
│   └── prompt_guard.py
│
├── reports/                       <- generated at runtime, gitignored
├── tests/
├── requirements.txt
├── .gitignore
└── README.md
```

> **Note on `orchestration/routing.py`:** an earlier version of this project used deterministic keyword routing to decide which evidence branch(es) ran. That has been replaced by the Data Retrieval Agent's own tool-selection reasoning (see Agent Responsibilities above). The file is left in place, unused, in case deterministic pre-filtering is reintroduced later as a cost/latency guardrail.

> **Note on `connectors/dataverse_timeentry.py` and `connectors/sharepoint_export.py`:** earlier versions of this project queried Dataverse live via an authenticated PowerShell session, and read a local SharePoint CSV directly. Both have been superseded - SharePoint data now arrives from the Copilot Studio flow already fetched, and timesheet data comes from a local D365 CSV export instead of live Dataverse. These connector files may still exist in the repository but are not part of the live request path.

---

## Prerequisites

- Python
- Git
- Azure DevOps access
- Azure DevOps Personal Access Token for local development
- Microsoft Copilot Studio access, with a SharePoint connector configured for the project register
- Microsoft Dev Tunnel for local Copilot Studio integration

> Secrets must never be committed to Git. Store local credentials only in `.env`.

---

## Installation

### 1. Clone the repository

```powershell
git clone <YOUR-REPOSITORY-URL>
cd maq-client-delivery-agent
```

### 2. Create a virtual environment

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a local `.env` file in the project root.

Example:

```text
AZDO_ORG=<azure-devops-organization>
AZDO_PROJECT=<azure-devops-project>
AZDO_PAT=<azure-devops-pat>

APP_ENV=dev

OPENAI_API_KEY=<openai-api-key>
OPENAI_CHAT_MODEL=<model-name>

D365_TIMESHEETS_PATH=<path-to-local-timesheets-csv>

PUBLIC_URL=<your-devtunnel-base-url>
```

Do not commit `.env`.

---

## Run the API

From the repository root:

```powershell
uvicorn apps.api.main:app --reload --host 0.0.0.0 --port 8000
```

Health endpoint:

```text
GET /health
```

Primary delivery endpoint:

```text
POST /delivery/query
```

Request body:

```json
{
  "user_question": "What is the current sprint status?",
  "user_id": "shanmukha.regidi@maqsoftware.com",
  "project_register": [ { "Project ID": "PBI-001", "...": "..." } ]
}
```

`user_id` is the caller's email, checked against the allowlist in `security/authorization.py` on every request - there is no separate login/session-issuance step. `project_register` is optional; omit it and the SharePoint tool will report no data was supplied for that request.

Report and chart retrieval:

```text
GET /reports/{report_id}.html
GET /reports/{filename}.png
```

---

## Example Questions

### Azure DevOps only

```text
How many bugs are there right now?
```

The Data Retrieval Agent calls `get_active_work_items` only - SharePoint and Timesheets have nothing relevant to add.

### SharePoint only

```text
What is the overall health of the finance project?
```

The Data Retrieval Agent calls `get_sharepoint_projects` only - this is project-level status, not sprint detail.

### Cross-source

```text
Give me the full picture on the finance project - budget, schedule,
and whether the team is over on planned hours.
```

The Data Retrieval Agent calls `get_sharepoint_projects` and `get_timesheets` together in the same turn.

### Guidance / recommendation

```text
What should we do about our delivery risks?
```

The Data Retrieval Agent gathers the relevant facts (e.g. `get_current_sprint_summary`). The Analyst Agent then calls its own `search_delivery_knowledge` tool to ground a recommendation in curated guidance, rather than generating advice from general knowledge.

---

## Deterministic Sprint Health

Sprint health is calculated deterministically inside `mcp_server/devops_server.py` from Azure DevOps evidence (completion % vs. sprint-elapsed %).

The LLM is not allowed to override the calculated classification - both agents' instructions explicitly forbid recalculating or overriding `healthStatus`, `completionPercent`, or `sprintElapsedPercent`.

Example categories:

- On Track
- At Risk
- Behind

This protects delivery-status decisions from model hallucination.

---

## Hybrid RAG

The knowledge layer combines:

- Semantic vector retrieval with ChromaDB
- BM25 keyword retrieval
- LlamaIndex orchestration
- Hugging Face sentence-transformer embeddings

Knowledge documents are stored under:

```text
data/knowledge/
```

Hybrid RAG is exposed as a tool to the **Analyst Agent**, not the Data Retrieval Agent - it returns guidance/interpretation content, not a live fact, so it belongs with the agent responsible for producing recommendations rather than the agent responsible for gathering facts.

---

## Chart and Report Generation

`reporting/charts.py` builds two charts and one HTML report **deterministically from the Data Retrieval Agent's structured numeric output** - never from the LLM's own generated text:

- A pie chart of work-item status (Completed / In Progress / New), when the evidence includes those counts.
- A bar chart of planned / completed / remaining effort hours, when the evidence includes those numbers.
- A self-contained HTML report combining the final answer text with both charts embedded as base64 images.

`apps/api/main.py` serves the generated files back and builds absolute URLs using the `PUBLIC_URL` environment variable, since the backend has no way to know its own public devtunnel address otherwise.

---

## Security Controls

### Authorization

`security/authorization.py` checks the caller's email against a flat allowlist (`AUTHORIZED_EMAILS`). There are no differentiated roles currently - any allowlisted email gets full access, since a single retrieval agent now covers all three evidence sources rather than a role-partitioned Portfolio/Engineering split.

The authorized email is also used as the key for conversational memory (MAF `AgentSession`), so a person who asks several questions in the same Teams conversation gets continuity between them without a separate login step.

### PII Protection

Microsoft Presidio detects and masks PII before user content is sent into the agent workflow.

### Prompt Injection Guard

High-confidence prompt-injection and policy-bypass patterns are blocked before agent execution.

### Output Secret Redaction

Final model output is scanned before being returned by FastAPI. Secret-like values such as API keys, bearer tokens, JWTs, passwords, and PAT-style assignments are redacted.

---

## Azure DevOps MCP

The MCP server is implemented in:

```text
mcp_server/devops_server.py
```

Available engineering functions:

```text
get_project_info
get_active_work_items
get_iterations
get_current_sprint_summary
get_sprint_summary_by_name
```

`get_current_sprint_summary` and `get_sprint_summary_by_name` also return per-work-item and aggregate effort hours (Original Estimate / Completed Work / Remaining Work), used for the effort bar chart. `get_sprint_summary_by_name` accepts flexible sprint references ("Sprint 3", "Iteration 3", "3") and falls back to a number-based match with an ambiguity guard rather than guessing.

The current implementation also prevents repeated use of the same Azure DevOps function during a single Data Retrieval Agent run.

> The current Agent Framework API used for progressive tool removal, and for `AgentSession`/`SessionStore`, is marked experimental. This should be reviewed when upgrading Agent Framework versions.

---

## SharePoint Integration

The project register lives in an Excel table (`MAQProjectRegister`) in a SharePoint document library. The Copilot Studio flow reads it directly via a "List rows present in a table" action and passes the rows to the backend as `project_register` on every `/delivery/query` call - the backend does not query SharePoint itself.

---

## D365 Timesheet Integration

`connectors/d365_timesheet.py` reads a local CSV export of D365 Project Operations timesheets: planned vs. actual vs. billable hours, approval status, and utilization percent, per employee per week. The file path is configured via `D365_TIMESHEETS_PATH` in `.env`, falling back to `data/d365/timesheets.csv` if unset.

---

## Copilot Studio Integration

Copilot Studio acts as the conversational entry point, with the flow calling this backend as a Tool with free (agent-decided) tool selection - there is no deterministic Topic-based routing.

Typical flow:

```text
User
  |
  v
Copilot Studio Agent
  |
  v
Power Automate / Agent Flow
  |
  +--> List rows present in a table (SharePoint project register)
  |
  +--> POST /delivery/query
  |       { user_question, user_id (= User.Email), project_register }
  |
  v
FastAPI Backend (Data Retrieval Agent + Insight Orchestrator)
  |
  v
Answer + sources + report/chart URLs returned to Copilot Studio
```

`user_id` is bound to the trigger's `User.Email` input, so it reflects real Teams identity rather than a value the user could self-declare.

---

## Testing

Install pytest if required:

```powershell
pip install pytest
```

Run:

```powershell
pytest -v
```

Current automated coverage includes:

- authorization (email allowlist, case-insensitivity, denial cases)
- prompt-injection detection
- output secret redaction
- `route_question` (kept as a unit-tested utility even though it's not currently wired into the live pipeline - see the note in Repository Structure)

---

## ALM / CI-CD

The target ALM process uses GitHub as source control and Azure DevOps Pipelines for promotion.

```text
Local Development
        |
        v
GitHub
        |
        v
Azure DevOps Pipeline
        |
        v
Build / Validate
        |
        v
Automated Tests
        |
        v
DEV
        |
        v
TEST
        |
        v
Manual Approval
        |
        v
PROD
```

Planned Azure DevOps environments:

```text
MAQ-Delivery-Dev
MAQ-Delivery-Test
MAQ-Delivery-Prod
```

Production promotion should require an Azure DevOps approval check.

---

## Responsible AI Principles

The solution is designed around:

- grounded enterprise evidence
- deterministic calculations for critical delivery classifications
- least-privilege access via an explicit allowlist
- PII protection
- output secret filtering
- source attribution
- human review for production decisions
- agent-selected (not hardcoded) evidence gathering, without ever inventing evidence a tool didn't return

---

## Current Status

Implemented:

- Two-agent MAF architecture (Data Retrieval Agent + Insight Orchestrator)
- Agent-driven tool selection across three evidence sources
- Azure DevOps MCP, including effort-hour tracking
- SharePoint evidence via the Copilot Studio flow
- D365 Timesheet evidence via local CSV
- Hybrid RAG (on the Analyst agent)
- Evidence validation with retry
- Email-allowlist authorization
- PII masking
- Prompt-injection protection
- Output secret redaction
- Deterministic chart + HTML report generation
- Per-user conversational memory
- Copilot Studio integration

Next ALM activities:

- Azure DevOps YAML pipeline
- Dev / Test / Prod environments
- Production approval gate
- observability and monitoring (Azure Application Insights)
- STRIDE threat model review against the current architecture
- final architecture and demo documentation

---

## Dependency Baseline

The working local environment currently uses major dependencies including:

```text
agent-framework==1.14.0
fastapi==0.138.0
uvicorn==0.52.3
httpx==0.28.1
pydantic==2.13.4
fastmcp==3.4.7
openpyxl==3.1.5
msal==1.37.0
presidio-analyzer==2.2.364
presidio-anonymizer==2.2.364
chromadb==1.5.9
sentence-transformers==5.7.0
llama-index==0.14.23
llama-index-retrievers-bm25==0.7.1
llama-index-vector-stores-chroma==0.5.5
llama-index-embeddings-huggingface==0.7.0
matplotlib
```

Pin the complete dependency set in `requirements.txt` before running the Azure DevOps CI/CD pipeline.

---

## Disclaimer

This repository is an implementation and capstone reference for an intelligent client-delivery workflow. Production deployment should use organization-approved identity, secret-management, monitoring, network, and governance controls.

## Security and STRIDE Threat Model

| STRIDE | Threat | Example | Mitigation |
|---|---|---|---|
| Spoofing | User impersonation | Claiming another user's identity | Real Teams identity via Copilot Studio `User.Email`, checked against an allowlist; Entra ID recommended for production |
| Tampering | Prompt or payload manipulation | "Ignore previous instructions" | Prompt-injection guard |
| Repudiation | Lack of request traceability | User denies making a request | Correlation IDs, user logging, timestamps (planned) |
| Information Disclosure | PII or secret leakage | Email, phone, API key in response | Presidio masking and output secret redaction |
| Denial of Service | Excessive agent/tool calls | Repeated MCP invocation | Single-use MCP tool controls and bounded retries |
| Elevation of Privilege | Access beyond allowlist | Non-allowlisted user requests data | Authorization before agent/tool execution |

## Responsible AI

The solution follows the following Responsible AI principles:

- **Fairness:** access decisions are a deterministic allowlist check rather than model-driven.
- **Reliability and Safety:** sprint health is calculated deterministically from Azure DevOps evidence and cannot be overridden by the LLM.
- **Privacy and Security:** PII is masked before agent execution and secret-like output is redacted before returning a response.
- **Transparency:** responses track the enterprise sources actually used for that answer.
- **Accountability:** Azure DevOps ALM stages and production approval checks provide governance and traceability.
- **Human Oversight:** agent recommendations support delivery decisions but do not replace management review.

## Observability

The solution includes lightweight observability to support troubleshooting, performance analysis, and auditability.

Current logging captures:

- request start and completion
- authorization results
- prompt-security decisions
- agent execution status
- source usage (which of SharePoint / Azure DevOps / Timesheets / MAQ Delivery Knowledge contributed)
- MCP tool usage
- evidence validation status
- report/chart generation
- final workflow success/failure

Recommended production enhancements:

- correlation ID for every request
- request duration measurement
- structured JSON logging
- centralized telemetry with Azure Application Insights
- distributed tracing across FastAPI, agents, MCP, and external data sources
- alerts for failures, high latency, repeated tool calls, and authorization denials

### Suggested Request Trace

```text
Correlation ID
     |
     v
FastAPI request
     |
     v
Security checks (PII, prompt guard, authorization)
     |
     v
Data Retrieval Agent (SharePoint / Azure DevOps / Timesheets)
     |
     v
Insight Orchestrator (+ Hybrid RAG when needed)
     |
     v
Chart + report generation
     |
     v
Final response
```

For a presentation, this can be summarized as:

> "The solution logs authorization, tool usage, evidence status, and workflow completion. In production, these logs would be centralized in Azure Application Insights with correlation IDs and latency/error monitoring."