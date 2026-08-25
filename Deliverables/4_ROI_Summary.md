# ROI Summary

**Illustrative Return-on-Investment Model**
MAQ Intelligent Client Delivery Agent — Prepared 2026-08-23

Illustrative model for a capstone demonstration, not measured production data. Models gross labor capacity released and one-time build cost — not guaranteed cash savings. Fields marked `[FILL IN]` are specific to your build and can't be estimated from outside — everything else is a generic, publicly-sourced reference assumption.

## 1. Assumptions

| # | Assumption | Value | Basis |
|---|---|---|---|
| 1 | Delivery manager hourly cost (base salary) | $50 / hour | [Glassdoor](https://www.glassdoor.com/Salaries/project-manager-salary-SRCH_KO0,15.htm), [ZipRecruiter](https://www.ziprecruiter.com/Salaries/Project-Manager-Salary), U.S. BLS OEWS 13-1082 |
| 2 | Time a manager spends on status reporting today | 3.7 hrs / week | [Lucen Timeline survey](https://www.lucensoftware.com/blog/study-how-to-save-time-and-money-in-project-reporting), Sept 2022, n=375 |
| 3 | Time to get the same status via this system | `[FILL IN — time yourself asking a real question end-to-end]` | Measure this directly; don't assume it matches any other project's number |
| 4 | Reporting frequency | Weekly, per manager | Assumption, adjust if different |
| 5 | Demo scope | 1 delivery manager (current setup: 1 flow, 1 tool) | As built |
| 6 | Illustrative scale-up scope | `[FILL IN — how many managers would realistically use this]` | Hypothetical |
| 7 | Software engineer hourly cost (base salary) | $65 / hour | [ZipRecruiter](https://www.ziprecruiter.com/Salaries/Software-Engineer-Salary), [Glassdoor](https://www.glassdoor.com/Salaries/software-engineer-salary-SRCH_KO0,17.htm) |
| 8 | Engineering effort to build this system | `[FILL IN — no time tracking exists; give your best honest range]` | Internal estimate |

## 2. Time and Cost Savings — Demo Scope (1 Manager)

Once Assumption 3 is filled in, this section computes itself:

| | Manual (today) | With this system | Reduction |
|---|---|---|---|
| Time per week | 222 min (3.7 hrs) | `[FILL IN]` | `[FILL IN]` |
| Cost per week | $185.00 | `[FILL IN]` | `[FILL IN]` |
| Cost per year (52 weeks) | $9,620.00 | `[FILL IN]` | `[FILL IN]` |

## 3. Illustrative Scale-Up

Once Assumption 6 is filled in: multiply Section 2's per-manager weekly figures by the scale-up count. This is an arithmetic extrapolation, not a validated projection — the per-manager time saving may not hold identically at scale (shared infrastructure contention, more varied questions, etc.).

## 4. Incremental Software/API Cost — Current Demo Stack

| Component | Cost | Notes |
|---|---|---|
| OpenAI API (`OPENAI_MODEL`) | `[FILL IN — depends on model tier and actual usage volume; check platform.openai.com/usage]` | Token cost varies by model — this was a live discussion point tonight (gpt-4o hit a 429 rate limit) |
| Azure DevOps (Pipelines, Boards, Repos) | $0 — free tier | [Azure DevOps pricing](https://azure.microsoft.com/en-us/pricing/details/devops/azure-devops-services/) |
| devtunnel | $0 | Preview, no SLA — not suitable for anything beyond a temporary demo |
| Copilot Studio / Power Automate licensing | `[FILL IN — depends on your organization's existing Microsoft 365/Power Platform licensing]` | Not evaluated in this review |

Excludes, none of which are $0 at real scale: developer hardware, engineering labor (Section 5), hosting beyond a temporary devtunnel, ongoing maintenance, and monitoring.

## 5. One-Time Development Cost

Once Assumption 8 is filled in:

| Engineering hours | Development cost (at $65/hr) |
|---|---|
| `[FILL IN]` | `[hours × $65]` |

## 6. Non-Financial Benefits (Not Yet Measured)

- Always-current data — each report pulls live Azure DevOps data at request time, rather than a stale weekly export
- Reduced manager context-switching — one Teams question replaces manually checking SharePoint, Azure DevOps, and timesheets separately
- Health status computed deterministically, not estimated by a person reading a dashboard

## 7. Sources

- [Glassdoor — Project Manager salary](https://www.glassdoor.com/Salaries/project-manager-salary-SRCH_KO0,15.htm)
- [ZipRecruiter — Project Manager salary](https://www.ziprecruiter.com/Salaries/Project-Manager-Salary)
- U.S. Bureau of Labor Statistics OEWS, SOC 13-1082 "Project Management Specialists"
- [Lucen Timeline — "Study: How to save time and money in project reporting"](https://www.lucensoftware.com/blog/study-how-to-save-time-and-money-in-project-reporting) (Sept 2022, n=375)
- [ZipRecruiter — Software Engineer salary](https://www.ziprecruiter.com/Salaries/Software-Engineer-Salary)
- [Glassdoor — Software Engineer salary](https://www.glassdoor.com/Salaries/software-engineer-salary-SRCH_KO0,17.htm)
- [Microsoft Azure — Azure DevOps Services pricing](https://azure.microsoft.com/en-us/pricing/details/devops/azure-devops-services/)

---

**Reviewed by:** ________________________________
**Role:** ________________________________
**Date:** ________________________________
