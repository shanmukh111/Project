"""
seed_full_dataset.py

One self-contained script that seeds Azure DevOps with realistic
delivery data for the MAQ Intelligent Client Delivery Agent demo,
including the new Jarvis project.

Unlike the older scripts/azure_devops/seed_azure_devops.py +
assign_iterations.py combo, this script:

  - Creates Iteration 1/2/3 as classification nodes WITH real
    start/finish dates (via the classification-nodes API), so
    Azure DevOps' own "Current" timeframe logic resolves
    correctly instead of always pointing at Iteration 1.
  - Adds each iteration to the team's iteration list (a separate
    API call from creating the classification node itself).
  - Creates Epic -> Feature -> User Story -> Task(s) [-> Bug] for
    every project, including the new Jarvis project, with real
    descriptions, story points, effort hours, and assigns each
    item directly to its iteration and target state in one pass.

Requires the same .env as the rest of the repo:
    AZDO_ORG, AZDO_PROJECT, AZDO_PAT

Run from the repository root:
    python scripts/azure_devops/seed_full_dataset.py

Safe to re-run: iteration creation is upsert-style (falls back to
PATCH if the iteration already exists). Work items are always
created fresh, so re-running will create duplicates of the work
items — this is meant to be run once against a clean project.
"""

import os
from urllib.parse import quote

import requests
from dotenv import load_dotenv

load_dotenv()

AZDO_ORG = os.getenv("AZDO_ORG")
AZDO_PROJECT = os.getenv("AZDO_PROJECT")
AZDO_PAT = os.getenv("AZDO_PAT")

if not all([AZDO_ORG, AZDO_PROJECT, AZDO_PAT]):
    raise ValueError("Missing AZDO_ORG, AZDO_PROJECT, or AZDO_PAT in .env")

from base64 import b64encode

_token = b64encode(f":{AZDO_PAT}".encode()).decode()

HEADERS_PATCH = {
    "Authorization": f"Basic {_token}",
    "Content-Type": "application/json-patch+json",
}

HEADERS_JSON = {
    "Authorization": f"Basic {_token}",
    "Content-Type": "application/json",
}

BASE_URL = f"https://dev.azure.com/{AZDO_ORG}/{AZDO_PROJECT}/_apis"


# ---------------------------------------------------------------
# Iteration setup (dates + team assignment)
# ---------------------------------------------------------------

def create_or_update_iteration(name: str, start_date: str, finish_date: str) -> str:
    """
    Creates an iteration classification node with real dates, or
    updates its dates if it already exists.

    Returns the iteration's identifier (needed to add it to the
    team's iteration list).
    """

    attributes = {
        "startDate": f"{start_date}T00:00:00Z",
        "finishDate": f"{finish_date}T00:00:00Z",
    }

    create_url = f"{BASE_URL}/wit/classificationnodes/Iterations?api-version=7.1"

    response = requests.post(
        create_url,
        headers=HEADERS_JSON,
        json={"name": name, "attributes": attributes},
    )

    if response.status_code in (200, 201):
        print(f"Created iteration '{name}' ({start_date} to {finish_date}).")
        return response.json()["identifier"]

    # Already exists -> patch its dates instead.
    patch_url = (
        f"{BASE_URL}/wit/classificationnodes/Iterations/"
        f"{quote(name)}?api-version=7.1"
    )

    patch_response = requests.patch(
        patch_url,
        headers=HEADERS_JSON,
        json={"attributes": attributes},
    )

    if not patch_response.ok:
        print("Azure DevOps Error (iteration patch):")
        print(patch_response.text)

    patch_response.raise_for_status()

    print(f"Updated iteration '{name}' dates ({start_date} to {finish_date}).")
    return patch_response.json()["identifier"]


def add_team_iteration(iteration_identifier: str, name: str) -> None:
    """Adds an iteration to the (default) team's selected iterations."""

    url = f"{BASE_URL}/work/teamsettings/iterations?api-version=7.1"

    response = requests.post(
        url,
        headers=HEADERS_JSON,
        json={"id": iteration_identifier},
    )

    if response.status_code in (200, 201):
        print(f"Added '{name}' to team iterations.")
        return

    if response.status_code == 409:
        # Already on the team's iteration list - fine.
        print(f"'{name}' is already on the team's iteration list.")
        return

    print("Azure DevOps Error (add team iteration):")
    print(response.text)
    response.raise_for_status()


# ---------------------------------------------------------------
# Work item creation
# ---------------------------------------------------------------

# ---------------------------------------------------------------
# Task "Activity" inference
#
# Microsoft.VSTS.Common.Activity is a Task-only picklist field
# (Deployment / Design / Development / Documentation /
# Requirements / Testing / Other). All tasks in this dataset
# follow one of three canonical titles, so it's inferred from
# the title rather than passed in separately.
# ---------------------------------------------------------------

ACTIVITY_BY_TITLE_KEYWORD = [
    ("Development implementation", "Development"),
    ("Data validation", "Testing"),
    ("Testing and verification", "Testing"),
]


def infer_activity(title: str) -> str | None:
    for keyword, activity in ACTIVITY_BY_TITLE_KEYWORD:
        if keyword in title:
            return activity
    return None


def split_effort(original_estimate: float, state: str) -> tuple[float, float]:
    """
    Splits an original estimate into (completed_work, remaining_work)
    based on the item's target state, so Closed items show fully
    burned-down effort, Active items show partial progress, and New
    items show zero completed work - matching what the state and
    percent_complete values already imply.
    """

    if state == "Closed":
        return original_estimate, 0.0

    if state == "Active":
        completed = round(original_estimate * 0.6, 1)
        remaining = round(original_estimate - completed, 1)
        return completed, remaining

    # New / anything else - no work started yet.
    return 0.0, original_estimate


def create_work_item(
    work_item_type: str,
    title: str,
    description: str = "",
    iteration_path: str | None = None,
    story_points: float | None = None,
    original_estimate: float | None = None,
    state: str | None = None,
) -> dict:

    encoded_type = quote(work_item_type)
    url = f"{BASE_URL}/wit/workitems/${encoded_type}?api-version=7.0"

    body = [
        {"op": "add", "path": "/fields/System.Title", "value": title},
        {"op": "add", "path": "/fields/System.Description", "value": description},
    ]

    if iteration_path:
        body.append({
            "op": "add",
            "path": "/fields/System.IterationPath",
            "value": f"{AZDO_PROJECT}\\{iteration_path}",
        })

    if story_points is not None:
        body.append({
            "op": "add",
            "path": "/fields/Microsoft.VSTS.Scheduling.StoryPoints",
            "value": story_points,
        })

    if original_estimate is not None:
        body.append({
            "op": "add",
            "path": "/fields/Microsoft.VSTS.Scheduling.OriginalEstimate",
            "value": original_estimate,
        })

        completed_work, remaining_work = split_effort(
            original_estimate,
            state or "New",
        )

        body.append({
            "op": "add",
            "path": "/fields/Microsoft.VSTS.Scheduling.CompletedWork",
            "value": completed_work,
        })

        body.append({
            "op": "add",
            "path": "/fields/Microsoft.VSTS.Scheduling.RemainingWork",
            "value": remaining_work,
        })

    if work_item_type == "Task":
        activity = infer_activity(title)

        if activity:
            body.append({
                "op": "add",
                "path": "/fields/Microsoft.VSTS.Common.Activity",
                "value": activity,
            })

    response = requests.post(url, headers=HEADERS_PATCH, json=body)

    if not response.ok:
        print("Azure DevOps Error (create work item):")
        print(response.text)

    response.raise_for_status()
    created = response.json()

    # State is set as a follow-up PATCH: work items are created in
    # their type's default state (usually "New"), so anything other
    # than "New" needs an explicit state transition after creation.
    if state and state != "New":
        set_work_item_state(created["id"], state)

    return created


def set_work_item_state(work_item_id: int, state: str) -> None:

    url = f"{BASE_URL}/wit/workitems/{work_item_id}?api-version=7.0"

    body = [{"op": "add", "path": "/fields/System.State", "value": state}]

    response = requests.patch(url, headers=HEADERS_PATCH, json=body)

    if not response.ok:
        print("Azure DevOps Error (set state):")
        print(response.text)

    response.raise_for_status()


def link_child_to_parent(child_id: int, parent_id: int) -> None:

    url = f"{BASE_URL}/wit/workitems/{child_id}?api-version=7.0"

    parent_url = f"https://dev.azure.com/{AZDO_ORG}/{AZDO_PROJECT}/_apis/wit/workItems/{parent_id}"

    body = [{
        "op": "add",
        "path": "/relations/-",
        "value": {
            "rel": "System.LinkTypes.Hierarchy-Reverse",
            "url": parent_url,
        },
    }]

    response = requests.patch(url, headers=HEADERS_PATCH, json=body)

    if not response.ok:
        print("Azure DevOps Error (link):")
        print(response.text)

    response.raise_for_status()


# ---------------------------------------------------------------
# Iteration plan (dates staggered around "today" so Iteration 2
# is genuinely current - adjust ITERATIONS if you run this on a
# different date than originally designed for)
# ---------------------------------------------------------------

ITERATIONS = {
    "Iteration 1": ("2026-08-03", "2026-08-16"),
    "Iteration 2": ("2026-08-17", "2026-08-30"),
    "Iteration 3": ("2026-08-31", "2026-09-13"),
}


# ---------------------------------------------------------------
# Full work item dataset (project_id, iteration, type, title,
# description, story_points, hours, state)
# ---------------------------------------------------------------

WORK_ITEMS = [
    # --- PBI-002: Finance Reporting Modernization (At Risk) - Iteration 1 ---
    ("PBI-002", "Iteration 1", "Epic", "PBI-002 - Finance Reporting Modernization",
     "Modernize Fabrikam Finance's monthly reporting suite from legacy Excel workbooks to a governed Power BI semantic model.",
     None, None, "Active"),
    ("PBI-002", "Iteration 1", "Feature", "PBI-002 Delivery Implementation",
     "Build and validate the finance semantic model, row-level security, and refreshed report pack.",
     None, None, "Active"),
    ("PBI-002", "Iteration 1", "User Story", "PBI-002 Complete delivery milestone",
     "As a finance controller, I need the modernized monthly close report so I can sign off faster.",
     13, None, "Active"),
    ("PBI-002", "Iteration 1", "Task", "PBI-002 - Development implementation",
     "Build DAX measures for the consolidated P&L and variance views.",
     None, 16, "Closed"),
    ("PBI-002", "Iteration 1", "Task", "PBI-002 - Data validation",
     "Reconcile semantic model output against the legacy ERP export for the last 3 closes.",
     None, 12, "Closed"),
    ("PBI-002", "Iteration 1", "Task", "PBI-002 - Testing and verification",
     "UAT with finance controllers; blocked pending the delayed ERP integration handoff.",
     None, 12, "Active"),
    ("PBI-002", "Iteration 1", "Bug", "PBI-002 Delivery Risk Issue",
     "ERP integration dependency is slipping the reporting-layer handoff by roughly one sprint.",
     None, 8, "Active"),

    # --- PBI-005: Legacy BI Decommission (Completed) - Iteration 1 ---
    ("PBI-005", "Iteration 1", "Epic", "PBI-005 - Legacy BI Decommission",
     "Decommission Northwind Logistics' legacy BI stack now that the replacement dashboards are live.",
     None, None, "Closed"),
    ("PBI-005", "Iteration 1", "Feature", "PBI-005 Delivery Implementation",
     "Archive legacy reports, redirect users, and formally retire the old reporting server.",
     None, None, "Closed"),
    ("PBI-005", "Iteration 1", "User Story", "PBI-005 Complete delivery milestone",
     "As an IT operations lead, I need the legacy BI server retired so we stop paying for redundant licensing.",
     8, 24, "Closed"),
    ("PBI-005", "Iteration 1", "Task", "PBI-005 - Development implementation",
     "Export and archive final legacy report snapshots for compliance retention.",
     None, 8, "Closed"),
    ("PBI-005", "Iteration 1", "Task", "PBI-005 - Data validation",
     "Confirm all consumers have migrated to the new dashboards before shutdown.",
     None, 6, "Closed"),
    ("PBI-005", "Iteration 1", "Task", "PBI-005 - Testing and verification",
     "Final sign-off from Northwind IT to decommission the legacy server.",
     None, 4, "Closed"),

    # --- PBI-001: Executive Sales Analytics (On Track, 72%) - Iteration 2 (current) ---
    ("PBI-001", "Iteration 2", "Epic", "PBI-001 - Executive Sales Analytics",
     "Deliver an executive-facing sales analytics workspace for Contoso Retail leadership.",
     None, None, "Active"),
    ("PBI-001", "Iteration 2", "Feature", "PBI-001 Delivery Implementation",
     "Finalize the sales semantic model and executive summary report page.",
     None, None, "Active"),
    ("PBI-001", "Iteration 2", "User Story", "PBI-001 Complete delivery milestone",
     "As a VP of Sales, I need a single executive view of pipeline and closed-won trends.",
     13, 36, "Active"),
    ("PBI-001", "Iteration 2", "Task", "PBI-001 - Development implementation",
     "Build the executive summary page with drill-through to regional detail.",
     None, 14, "Closed"),
    ("PBI-001", "Iteration 2", "Task", "PBI-001 - Data validation",
     "Cross-check pipeline totals against the CRM source of truth.",
     None, 10, "Active"),
    ("PBI-001", "Iteration 2", "Task", "PBI-001 - Testing and verification",
     "UAT walkthrough scheduled with the sales leadership team.",
     None, 8, "New"),

    # --- PBI-003: Operations KPI Dashboard (On Track, 35%) - Iteration 2 (current) ---
    ("PBI-003", "Iteration 2", "Epic", "PBI-003 - Operations KPI Dashboard",
     "Build a real-time operations KPI dashboard for Northwind Logistics warehouse performance.",
     None, None, "Active"),
    ("PBI-003", "Iteration 2", "Feature", "PBI-003 Delivery Implementation",
     "Ingest warehouse telemetry and model on-time-in-full and throughput KPIs.",
     None, None, "Active"),
    ("PBI-003", "Iteration 2", "User Story", "PBI-003 Complete delivery milestone",
     "As an operations manager, I need live visibility into on-time-in-full performance by warehouse.",
     8, 30, "Active"),
    ("PBI-003", "Iteration 2", "Task", "PBI-003 - Development implementation",
     "Build the incremental refresh pipeline from the warehouse telemetry feed.",
     None, 12, "Active"),
    ("PBI-003", "Iteration 2", "Task", "PBI-003 - Data validation",
     "Spot-check KPI calculations against manual warehouse reports.",
     None, 10, "New"),
    ("PBI-003", "Iteration 2", "Task", "PBI-003 - Testing and verification",
     "Not yet started; scheduled after data validation completes.",
     None, 8, "New"),

    # --- JRV-001: Jarvis Intelligent Delivery Agent (new, 15%) - Iteration 2 (current) ---
    ("JRV-001", "Iteration 2", "Epic", "JRV-001 - Jarvis Intelligent Delivery Agent",
     "Build Jarvis, a multi-agent delivery-intelligence assistant for Shanmukha Regidi, mirroring the MAQ Delivery Agent architecture.",
     None, None, "Active"),
    ("JRV-001", "Iteration 2", "Feature", "JRV-001 Delivery Implementation",
     "Stand up the Portfolio, Engineering, and Analyst agents with Hybrid RAG delivery guidance.",
     None, None, "Active"),
    ("JRV-001", "Iteration 2", "User Story", "JRV-001 Complete delivery milestone",
     "As Shanmukha, I need a working end-to-end demo of Jarvis answering a real delivery question.",
     13, 32, "Active"),
    ("JRV-001", "Iteration 2", "Task", "JRV-001 - Development implementation",
     "Wire the Azure DevOps MCP server and the deterministic sprint-health calculation.",
     None, 14, "Active"),
    ("JRV-001", "Iteration 2", "Task", "JRV-001 - Data validation",
     "Validate SharePoint/D365 CSV ingestion against the local project register.",
     None, 10, "New"),
    ("JRV-001", "Iteration 2", "Task", "JRV-001 - Testing and verification",
     "End-to-end test of a cross-domain question through Copilot Studio.",
     None, 8, "New"),

    # --- PBI-004: Customer Insights Platform (At Risk / Behind) - Iteration 3 (future) ---
    ("PBI-004", "Iteration 3", "Epic", "PBI-004 - Customer Insights Platform",
     "Build a unified customer insights platform for Adventure Works marketing and CX teams.",
     None, None, "New"),
    ("PBI-004", "Iteration 3", "Feature", "PBI-004 Delivery Implementation",
     "Integrate customer, order, and support-ticket data into a single semantic model.",
     None, None, "New"),
    ("PBI-004", "Iteration 3", "User Story", "PBI-004 Complete delivery milestone",
     "As a CX director, I need a 360-degree customer view spanning orders and support history.",
     13, 40, "New"),
    ("PBI-004", "Iteration 3", "Task", "PBI-004 - Development implementation",
     "Model the unified customer entity once source-system requirements are finalized.",
     None, 16, "New"),
    ("PBI-004", "Iteration 3", "Task", "PBI-004 - Data validation",
     "Pending resolution of data-governance sign-off from Adventure Works legal.",
     None, 12, "New"),
    ("PBI-004", "Iteration 3", "Task", "PBI-004 - Testing and verification",
     "Not started; blocked behind development and validation.",
     None, 12, "New"),
    ("PBI-004", "Iteration 3", "Bug", "PBI-004 Delivery Risk Issue",
     "Source system delays and unresolved data-governance requirements threaten the UAT signoff date.",
     None, 8, "New"),

    # --- AZ-001: Cloud Migration Wave 2 (On Track) - Iteration 3 (future) ---
    ("AZ-001", "Iteration 3", "Epic", "AZ-001 - Cloud Migration Wave 2",
     "Migrate Contoso Retail's remaining on-prem workloads to Azure in Wave 2.",
     None, None, "New"),
    ("AZ-001", "Iteration 3", "Feature", "AZ-001 Delivery Implementation",
     "Migrate the order-management and inventory workloads with minimal downtime.",
     None, None, "New"),
    ("AZ-001", "Iteration 3", "User Story", "AZ-001 Complete delivery milestone",
     "As an infrastructure lead, I need Wave 2 workloads migrated within the approved change window.",
     13, 36, "New"),
    ("AZ-001", "Iteration 3", "Task", "AZ-001 - Development implementation",
     "Provision target landing zone and network peering for the migrated workloads.",
     None, 14, "New"),
    ("AZ-001", "Iteration 3", "Task", "AZ-001 - Data validation",
     "Validate data parity post-migration for the inventory database.",
     None, 12, "New"),
    ("AZ-001", "Iteration 3", "Task", "AZ-001 - Testing and verification",
     "Cutover rehearsal scheduled for the start of the migration window.",
     None, 10, "New"),

    # --- D365-001: Project Operations Rollout (At Risk) - Iteration 3 (future) ---
    ("D365-001", "Iteration 3", "Epic", "D365-001 - Project Operations Rollout",
     "Roll out D365 Project Operations for Fabrikam Finance's professional-services teams.",
     None, None, "New"),
    ("D365-001", "Iteration 3", "Feature", "D365-001 Delivery Implementation",
     "Configure timesheet entry, approvals, and project-costing workflows.",
     None, None, "New"),
    ("D365-001", "Iteration 3", "User Story", "D365-001 Complete delivery milestone",
     "As a delivery manager, I need field teams submitting compliant weekly timesheets.",
     8, 28, "New"),
    ("D365-001", "Iteration 3", "Task", "D365-001 - Development implementation",
     "Configure approval workflows and project-costing rules for Phase 2.",
     None, 12, "New"),
    ("D365-001", "Iteration 3", "Task", "D365-001 - Data validation",
     "Audit timesheet adoption rates from the Phase 1 pilot group.",
     None, 8, "New"),
    ("D365-001", "Iteration 3", "Task", "D365-001 - Testing and verification",
     "Change-management training planned ahead of Phase 2 go-live.",
     None, 8, "New"),
    ("D365-001", "Iteration 3", "Bug", "D365-001 Delivery Risk Issue",
     "Timesheet adoption below target; change-management gap with field teams.",
     None, 6, "New"),
]


# ---------------------------------------------------------------
# Main
# ---------------------------------------------------------------

def main() -> None:

    print(f"Seeding Azure DevOps project '{AZDO_PROJECT}' in org '{AZDO_ORG}'...\n")

    # 1. Create/update iterations with real dates, then add each
    #    to the team's iteration list.
    for name, (start, finish) in ITERATIONS.items():
        identifier = create_or_update_iteration(name, start, finish)
        add_team_iteration(identifier, name)

    print()

    # 2. Create work items, tracking the current Epic/Feature/Story
    #    per project so Tasks and Bugs link up to the right parent.
    parent_ids: dict[str, dict[str, int]] = {}

    for (
        project_id,
        iteration,
        wi_type,
        title,
        description,
        story_points,
        hours,
        state,
    ) in WORK_ITEMS:

        parent_ids.setdefault(project_id, {})

        created = create_work_item(
            work_item_type=wi_type,
            title=title,
            description=description,
            iteration_path=iteration,
            story_points=story_points,
            original_estimate=hours,
            state=state,
        )

        work_item_id = created["id"]
        print(f"  Created {wi_type} #{work_item_id}: {title} [{state}]")

        if wi_type == "Epic":
            parent_ids[project_id]["Epic"] = work_item_id

        elif wi_type == "Feature":
            parent_ids[project_id]["Feature"] = work_item_id
            if "Epic" in parent_ids[project_id]:
                link_child_to_parent(work_item_id, parent_ids[project_id]["Epic"])

        elif wi_type == "User Story":
            parent_ids[project_id]["User Story"] = work_item_id
            if "Feature" in parent_ids[project_id]:
                link_child_to_parent(work_item_id, parent_ids[project_id]["Feature"])

        elif wi_type in ("Task", "Bug"):
            if "User Story" in parent_ids[project_id]:
                link_child_to_parent(work_item_id, parent_ids[project_id]["User Story"])

    print("\nSeeding complete.")


if __name__ == "__main__":
    main()