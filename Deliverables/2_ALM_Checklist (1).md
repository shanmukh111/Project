# ALM Checklist

**Dev / Test / Manual Attestation / Release Pipeline in Azure DevOps**
MAQ Intelligent Client Delivery Agent — Prepared 2026-08-23, updated 2026-08-23 (post pipeline restructure)

Pipeline defined as code in `azure-pipelines.yml`, version-controlled with the application, repo `shanmukh111/Project` (GitHub, connected as the pipeline's source).

## 1. Pipeline Stages

| Stage | Trigger | Purpose | Status |
|---|---|---|---|
| Dev | Push to any branch, or PR opened | Compile/import sanity check (`python -m compileall`) | In place — confirmed passing (build 20260823.6) |
| Test | After Dev succeeds | Automated test suite (`pytest -v`) | In place — confirmed passing |
| Manual attestation gate | After merge to `main` | Human verifies Teams/Copilot Studio end-to-end behavior, which can't run on the shared build agent | In place — approval check confirmed firing (`1 checks passed`) |
| Release | After manual gate approved | Tags the release version in git (`release-<build number>`) against the GitHub-hosted repo. No persistent production environment is provisioned — this is release governance, not a deployment | In place — confirmed passing after fixing the push target |

Confirmed end-to-end on build `20260823.6`, commit `d9cbd9d2` — all four stages green in a single run, 9m 36s total.

## 2. ALM Practices

| Practice | Evidence | Status |
|---|---|---|
| Pipeline as code | `azure-pipelines.yml`, tracked in git | In place |
| Dependencies pinned to a manifest | `requirements.txt` | In place |
| Syntax validation before test run | `python -m compileall agents apps connectors mcp_server orchestration retrieval security reporting` | In place |
| Tests run automatically on every push/PR | `Dev`/`Test` stages triggered on `branches: include: '*'` and `pr: branches: include: '*'` | In place |
| Human sign-off before release | Environment `MAQ-Delivery-ManualGate` with an approval check, confirmed firing on a real run | In place |
| Every release tagged | `git tag release-<build number>`, pushed via `git push origin`, on every Release stage run | In place |
| No secrets in the codebase | `.env` gitignored, confirmed no `.env` history in this repo | In place |
| PAT scope separation | Considered but not adopted — a single full-access PAT is currently in use for both the live app's Azure DevOps calls and (where applicable) pipeline operations, a deliberate scope tradeoff made under time pressure, not an oversight | Known gap, accepted |
| One change, one commit, reviewable diff | Standard git workflow | In place |
| CI runner disk/dependency footprint managed | — | Open — `Install dependencies` has logged disk-space warnings (95%+ used) on every run so far, from the size of the hybrid-RAG dependency stack (chromadb, llama-index, sentence-transformers) |
| Rollback process | — | Gap — no documented rollback; would currently be a manual git revert |
| Real deployment automation | — | Deliberately out of scope — Release is release governance (a git tag), not a deployment, matching the model this pipeline was based on |

## 3. Known Issues Found and Fixed (this build-out)

| Issue | Fix |
|---|---|
| `python -m compileall` step omitted the `reporting/` package | Added `reporting` to the compileall argument list |
| Release stage's `git push` targeted a nonexistent Azure Repos URL (`dev.azure.com/.../_git/Project`) — the actual repo is GitHub-hosted, not Azure Repos, so every push failed with `TF401019: repository not found` | Corrected to `git push origin release-$(Build.BuildNumber)`, relying on the credentials already persisted by `checkout: self` + `persistCredentials: true` against the correct GitHub remote |
| A stale, previously-opened Azure DevOps web YAML editor tab was saved after the restructure was already complete, silently reverting `azure-pipelines.yml` on `main` back to the original `Validate/Dev/Test/Prod` placeholder structure | Restored the correct file content from a known-good local copy, committed and pushed directly from the local machine going forward — the web editor is no longer used for this file to avoid a repeat |
| A transient OpenAI `429` rate-limit mid-conversation left the persisted `SessionStore` session holding a dangling, unresolved tool call — every subsequent question from that user failed identically until the process restarted | Root-caused to `_save_agent_session` being called unconditionally in `delivery_workflow.py` regardless of retrieval success; fix identified — only persist the session on a successful run (code change drafted, not yet confirmed merged) |
| Azure DevOps effort-hours bar chart (`reporting/charts.py`) implied Planned = Completed + Remaining, which Azure DevOps does not guarantee (three independently-maintained fields) | Relabeled bars away from a whole/parts framing, added an explanatory caption — shipped, verified green in the Dev stage |
| Copilot Studio's orchestrator calling the backend multiple times for one user question, worsened by the flow being synchronous against a slow pipeline | Enabled `Asynchronous response` on the flow's `Respond to the agent` action |
| `statusChart`/`effortChart` in the flow's `Respond to the agent` action were bound to a flat path (`Body status_pie`) instead of the actual nested schema path (`Body chart_urls status_pie`) | Re-picked both outputs from the dynamic content picker after `Parse Delivery Response JSON`, resolving the correct nested path |

## 4. Sign-Off

| Role | Name | Decision | Date | Comments |
|---|---|---|---|---|
| Engineering owner | Shanmukha Srinivas Regidi | Approve / Reject | | |
