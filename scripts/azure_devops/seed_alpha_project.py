"""
seed_alpha_project.py

Seeds the "Alpha" Azure DevOps project with a genuinely separate,
Power BI-themed dataset - epics, features, user stories, and tasks
distinct from Jarvis's content, so the two projects have real,
different underlying data to distinguish them.

Unlike seed_full_dataset.py, this script does NOT read AZDO_PROJECT
from .env - it targets "Alpha" directly, so it can be run without
touching or overriding your existing Jarvis-scoped .env. AZDO_ORG
and AZDO_PAT are still read from .env, since those are shared
across both projects in the same organization.

Requires the "Alpha" project to already exist in Azure DevOps
before running this - create it first (Organization settings ->
Projects -> New project), matching this exact name, case-sensitive,
since orchestration/delivery_workflow.py resolves this project name
from security/authorization.py's AUTHORIZED_PROJECTS mapping.

Run from the repository root:
    python scripts/azure_devops/seed_alpha_project.py

Safe to re-run for iterations (upsert-style); work items are always
created fresh, so re-running duplicates work items - meant to be
run once against a clean Alpha project.
"""

import os
from urllib.parse import quote

import requests
from dotenv import load_dotenv

load_dotenv()

AZDO_ORG = os.getenv("AZDO_ORG")
AZDO_PAT = os.getenv("AZDO_PAT")

# Deliberately hardcoded, not read from .env - this script always
# targets Alpha regardless of what AZDO_PROJECT is set to elsewhere.
AZDO_PROJECT = "Alpha"

if not all([AZDO_ORG, AZDO_PAT]):
    raise ValueError("Missing AZDO_ORG or AZDO_PAT in .env")

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
# Iteration setup (dates + team assignment) - identical mechanics
# to seed_full_dataset.py, targeting Alpha's own classification
# nodes (iterations are per-project in Azure DevOps, so Alpha
# needs its own, separate from Jarvis's).
# ---------------------------------------------------------------

def create_or_update_iteration(name: str, start_date: str, finish_date: str) -> str:
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
        print(f"'{name}' is already on the team's iteration list.")
        return

    print("Azure DevOps Error (add team iteration):")
    print(response.text)
    response.raise_for_status()


# ---------------------------------------------------------------
# Task "Activity" inference - same three canonical task titles
# as seed_full_dataset.py, so the deterministic Azure DevOps
# tools (mcp_server/devops_server.py) work identically on Alpha.
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
    if state == "Closed":
        return original_estimate, 0.0

    if state == "Active":
        completed = round(original_estimate * 0.6, 1)
        remaining = round(original_estimate - completed, 1)
        return completed, remaining

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
# Iteration plan - Alpha's own iterations, independent of
# Jarvis's. Iteration 2 is the "current" one (today falls inside
# its date range), matching the same staggering pattern used for
# Jarvis so "current sprint" questions resolve correctly.
# ---------------------------------------------------------------

ITERATIONS = {
    "Iteration 1": ("2026-08-03", "2026-08-16"),
    "Iteration 2": ("2026-08-17", "2026-08-30"),
    "Iteration 3": ("2026-08-31", "2026-09-13"),
}


# ---------------------------------------------------------------
# Full work item dataset for Alpha - Power BI Center-of-Excellence
# themed work, genuinely distinct from Jarvis's content.
# (project_id, iteration, type, title, description, story_points,
#  hours, state)
# ---------------------------------------------------------------

WORK_ITEMS = [
    # --- ALP-001: Enterprise Semantic Model Governance (current, Active) - Iteration 2 ---
    ("ALP-001", "Iteration 2", "Epic", "ALP-001 - Enterprise Semantic Model Governance",
     "Establish a certified, governed enterprise semantic model layer in Power BI, replacing ad-hoc per-team datasets.",
     None, None, "Active"),
    ("ALP-001", "Iteration 2", "Feature", "ALP-001 Delivery Implementation",
     "Build the certified semantic model, endorsement workflow, and row-level security framework.",
     None, None, "Active"),
    ("ALP-001", "Iteration 2", "User Story", "ALP-001 Complete delivery milestone",
     "As a BI governance lead, I need a single certified semantic model so teams stop building duplicate datasets.",
     13, 34, "Active"),
    ("ALP-001", "Iteration 2", "Task", "ALP-001 - Development implementation",
     "Build the certified semantic model and configure dataset endorsement in the Power BI service.",
     None, 14, "Closed"),
    ("ALP-001", "Iteration 2", "Task", "ALP-001 - Data validation",
     "Validate row-level security rules against each department's access requirements.",
     None, 10, "Active"),
    ("ALP-001", "Iteration 2", "Task", "ALP-001 - Testing and verification",
     "UAT with department report owners on the new certified model.",
     None, 10, "New"),
    ("ALP-001", "Iteration 2", "Bug", "ALP-001 Delivery Risk Issue",
     "Two departments' existing reports have unresolved DAX incompatibilities against the new certified model.",
     None, 6, "Active"),

    # --- ALP-002: Power BI Embedded Analytics Portal (future, New) - Iteration 3 ---
    ("ALP-002", "Iteration 3", "Epic", "ALP-002 - Power BI Embedded Analytics Portal",
     "Deliver a white-labeled, embedded analytics portal exposing Power BI reports to external client users.",
     None, None, "New"),
    ("ALP-002", "Iteration 3", "Feature", "ALP-002 Delivery Implementation",
     "Integrate Power BI Embedded, configure app-owns-data authentication, and build the portal shell.",
     None, None, "New"),
    ("ALP-002", "Iteration 3", "User Story", "ALP-002 Complete delivery milestone",
     "As a client-facing account manager, I need clients to view their own dashboards without an internal Power BI license.",
     13, 38, "New"),
    ("ALP-002", "Iteration 3", "Task", "ALP-002 - Development implementation",
     "Implement app-owns-data embedding with tenant-scoped row-level security.",
     None, 16, "New"),
    ("ALP-002", "Iteration 3", "Task", "ALP-002 - Data validation",
     "Confirm each client tenant only sees their own scoped data through the embedded portal.",
     None, 12, "New"),
    ("ALP-002", "Iteration 3", "Task", "ALP-002 - Testing and verification",
     "Not yet started; scheduled after embedding and tenant isolation are complete.",
     None, 10, "New"),
]


# ---------------------------------------------------------------
# Main
# ---------------------------------------------------------------

def main() -> None:

    print(f"Seeding Azure DevOps project '{AZDO_PROJECT}' in org '{AZDO_ORG}'...\n")

    for name, (start, finish) in ITERATIONS.items():
        identifier = create_or_update_iteration(name, start, finish)
        add_team_iteration(identifier, name)

    print()

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