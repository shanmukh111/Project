# Test Log

**Functional & Behavioral Test Matrix — Template**
MAQ Intelligent Client Delivery Agent

This is a template, not a completed log. Every response, HTTP code, and timing below must come from actually running these questions against your live agent and recording what really happens — none of it is filled in here, because a Claude-authored transcript would be fabricated, not measured, evidence.

## 1. Purpose and Test Categories

Run a deliberate pass across five categories against the live system: happy path, failure handling, edge cases, security/adversarial, and out-of-scope questions.

## 2. Summary — fill in as you run each case

| ID | Category | Description | HTTP | Time (s) | Result |
|---|---|---|---|---|---|
| H1 | Happy path | Broad "how is the project doing" question, SharePoint-only | | | |
| H2 | Happy path | Sprint status question, Azure DevOps-only | | | |
| H3 | Happy path | Question needing more than one source in the same answer | | | |
| H4 | Happy path | Recommendation-seeking question that should trigger the hybrid RAG tool | | | |
| F1 | Failure | Question about a project the caller isn't authorized for | | | |
| F2 | Failure | Question about a project name that doesn't exist at all | | | |
| F3 | Failure | Force a retrieval failure (e.g. temporarily break the API key) and confirm the agent says evidence is unavailable rather than fabricating an answer | | | |
| E1 | Edge case | Very short/vague input with no named project | | | |
| E2 | Edge case | Same question asked twice in quick succession — confirm no duplicate/diverging answers | | | |
| E3 | Edge case | Question where the relevant chart data is legitimately empty (e.g. asking about hours on a SharePoint-only project) | | | |
| S1 | Security | Prompt-injection attempt trying to get the agent to act as, or reveal data for, a different user | | | |
| S2 | Security | Attempt to get the agent to reveal internal tool names, backend URLs, or raw errors | | | |
| U1 | Unrelated | Obviously off-topic question | | | |
| U2 | Unrelated | Plausible-sounding but still out-of-scope question (the kind that tempts a model into fabricating from general knowledge) | | | |

## 3. Findings — fill in after running the matrix

Document anything that surprised you here — a wrong answer, an unexpectedly slow response, a case where the "STOP after tool responds" rule was violated, or a case that exposed the session-corruption bug found in `3_Security_Checklist.md`. Include what you changed and how you re-verified the fix, the same way each bug in tonight's session was root-caused and then re-tested.

## 4. Detailed Results — fill in per case

For each ID above, capture: the exact question asked, the caller's identity, the full response text, HTTP status, and response time. Real transcripts, not paraphrases — that's what makes this evidence rather than a description.

## 5. Sign-Off

| Role | Name | Decision | Date | Comments |
|---|---|---|---|---|
| Engineering owner | Shanmukha Srinivas Regidi | Approve / Reject | | |
