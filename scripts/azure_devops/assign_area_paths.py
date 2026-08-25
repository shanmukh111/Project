"""
assign_area_paths.py

One-time migration: creates an Area Path per client engagement
inside a given Azure DevOps project, and assigns every existing
work item in that project to the correct one, inferred from its
title prefix (e.g. "PBI-002 - Finance Reporting Modernization" ->
area path "Jarvis\\PBI-002", or "ALP-001 - ..." -> "Alpha\\ALP-001").

This is what actually fixes the cross-contamination bug where
get_current_sprint_summary/get_sprint_summary_by_name pooled every
epic sharing an iteration together, regardless of which client
engagement it belonged to. Once this has run for a project, its
sprint tools can filter by project_id and get a correctly-scoped
result.

Works against ONE Azure DevOps project per run - pass the project
name as a command-line argument. Defaults to whatever AZDO_PROJECT
is set to in .env if no argument is given.

Run from the repository root, once per project:
    python scripts/azure_devops/assign_area_paths.py Jarvis
    python scripts/azure_devops/assign_area_paths.py Alpha

Safe to re-run: area path creation is idempotent (skips if it
already exists), and re-patching a work item's Area Path to the
same value it already has is a no-op.

Requires the same .env as the rest of the repo:
    AZDO_ORG, AZDO_PAT
(AZDO_PROJECT from .env is only used as the default if no
command-line argument is given.)
"""

import os
import re
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

AZDO_ORG = os.getenv("AZDO_ORG")
AZDO_PAT = os.getenv("AZDO_PAT")

# The project to migrate - from the command line if given,
# otherwise whatever AZDO_PROJECT is currently set to in .env.
AZDO_PROJECT = (
    sys.argv[1] if len(sys.argv) > 1 else os.getenv("AZDO_PROJECT")
)

if not all([AZDO_ORG, AZDO_PAT, AZDO_PROJECT]):
    raise ValueError(
        "Missing AZDO_ORG or AZDO_PAT in .env, or no project given "
        "(pass one as a command-line argument, e.g. "
        "'python scripts/azure_devops/assign_area_paths.py Alpha')."
    )

from base64 import b64encode

_token = b64encode(f":{AZDO_PAT}".encode()).decode()

HEADERS_JSON = {
    "Authorization": f"Basic {_token}",
    "Content-Type": "application/json",
}

HEADERS_PATCH = {
    "Authorization": f"Basic {_token}",
    "Content-Type": "application/json-patch+json",
}

BASE_URL = f"https://dev.azure.com/{AZDO_ORG}/{AZDO_PROJECT}/_apis"

# Every project_id this system's demo data uses, per real Azure
# DevOps project. Add to the relevant list if new client-engagement
# epics are seeded later.
PROJECT_ID_MAP = {
    "Jarvis": [
        "PBI-001",
        "PBI-002",
        "PBI-003",
        "PBI-004",
        "PBI-005",
        "AZ-001",
        "D365-001",
        "JRV-001",
    ],
    "Alpha": [
        "ALP-001",
        "ALP-002",
    ],
}

KNOWN_PROJECT_IDS = PROJECT_ID_MAP.get(AZDO_PROJECT)

if KNOWN_PROJECT_IDS is None:
    raise ValueError(
        f"No known project_id list configured for Azure DevOps "
        f"project '{AZDO_PROJECT}' - add one to PROJECT_ID_MAP in "
        f"this script before running the migration against it."
    )

# Matches a leading project_id prefix like "PBI-002", "ALP-001",
# or "D365-001" at the start of a work item title. The prefix
# itself can mix letters and digits (e.g. "D365"), so this isn't
# pure letters-then-digits - only the character right before the
# final "-<digits>" group is required to be a letter, which is
# enough to rule out titles that don't start with a project_id at
# all.
TITLE_PREFIX_PATTERN = re.compile(r"^([A-Z][A-Z0-9]*-\d+)")


def create_area_path(name: str) -> None:
    url = f"{BASE_URL}/wit/classificationnodes/Areas?api-version=7.1"

    response = requests.post(
        url,
        headers=HEADERS_JSON,
        json={"name": name},
    )

    if response.status_code in (200, 201):
        print(f"Created area path '{name}'.")
        return

    if response.status_code == 409:
        print(f"Area path '{name}' already exists.")
        return

    print(f"Azure DevOps Error (create area path '{name}'):")
    print(response.text)
    response.raise_for_status()


def get_all_work_items() -> list[dict]:
    wiql_url = f"{BASE_URL}/wit/wiql?api-version=7.0"

    query = {
        "query": """
            SELECT [System.Id], [System.Title]
            FROM WorkItems
            WHERE [System.TeamProject] = @project
            ORDER BY [System.Id]
        """
    }

    response = requests.post(wiql_url, headers=HEADERS_JSON, json=query)
    response.raise_for_status()

    ids = [
        str(item["id"])
        for item in response.json().get("workItems", [])
    ]

    if not ids:
        return []

    # Azure DevOps' work items batch-details endpoint caps out at
    # 200 IDs per request - chunk defensively so this keeps working
    # as the project's item count grows, not just for today's size.
    all_details: list[dict] = []
    chunk_size = 200

    for i in range(0, len(ids), chunk_size):
        chunk = ids[i:i + chunk_size]
        ids_param = ",".join(chunk)

        details_url = (
            f"{BASE_URL}/wit/workitems"
            f"?ids={ids_param}"
            f"&fields=System.Id,System.Title,System.AreaPath"
            f"&api-version=7.0"
        )

        details_response = requests.get(details_url, headers=HEADERS_JSON)
        details_response.raise_for_status()

        all_details.extend(details_response.json().get("value", []))

    return all_details


def set_area_path(work_item_id: int, area_path: str) -> None:
    url = f"{BASE_URL}/wit/workitems/{work_item_id}?api-version=7.0"

    body = [{
        "op": "add",
        "path": "/fields/System.AreaPath",
        "value": area_path,
    }]

    response = requests.patch(url, headers=HEADERS_PATCH, json=body)

    if not response.ok:
        print(f"Azure DevOps Error (set area path on #{work_item_id}):")
        print(response.text)

    response.raise_for_status()


def main() -> None:
    print(f"Assigning area paths in project '{AZDO_PROJECT}'...\n")

    for project_id in KNOWN_PROJECT_IDS:
        create_area_path(project_id)

    print()

    work_items = get_all_work_items()
    print(f"Found {len(work_items)} work items to check.\n")

    updated = 0
    skipped_no_match = 0
    skipped_already_correct = 0

    for item in work_items:
        fields = item.get("fields", {})
        item_id = fields.get("System.Id")
        title = fields.get("System.Title", "")
        current_area_path = fields.get("System.AreaPath")

        match = TITLE_PREFIX_PATTERN.match(title)

        if not match:
            print(f"  Skipping #{item_id} '{title}' - no project_id prefix found.")
            skipped_no_match += 1
            continue

        project_id = match.group(1)

        if project_id not in KNOWN_PROJECT_IDS:
            print(f"  Skipping #{item_id} '{title}' - '{project_id}' not in KNOWN_PROJECT_IDS.")
            skipped_no_match += 1
            continue

        expected_area_path = f"{AZDO_PROJECT}\\{project_id}"

        if current_area_path == expected_area_path:
            skipped_already_correct += 1
            continue

        set_area_path(item_id, expected_area_path)
        print(f"  #{item_id} '{title}' -> {expected_area_path}")
        updated += 1

    print(
        f"\nDone. {updated} updated, "
        f"{skipped_already_correct} already correct, "
        f"{skipped_no_match} skipped (no recognizable project_id)."
    )


if __name__ == "__main__":
    main()