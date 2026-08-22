import os
import re
from base64 import b64encode
from datetime import datetime, timezone
import httpx
from dotenv import load_dotenv
from fastmcp import FastMCP

load_dotenv()

AZDO_ORG = os.getenv("AZDO_ORG")
AZDO_PROJECT = os.getenv("AZDO_PROJECT")
AZDO_PAT = os.getenv("AZDO_PAT")

mcp = FastMCP(name="MAQ Azure DevOps MCP Server")

def get_auth_header() -> dict:
    token = b64encode(f":{AZDO_PAT}".encode()).decode()
    return {
        "Authorization": f"Basic {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


@mcp.tool
def get_project_info() -> dict:
    """Returns basic information about the configured Azure DevOps project."""

    url = (
        f"https://dev.azure.com/{AZDO_ORG}/"
        f"_apis/projects/{AZDO_PROJECT}?api-version=7.1"
    )

    try:
        response = httpx.get(
            url,
            headers=get_auth_header(),
            timeout=20.0,
        )

        response.raise_for_status()
        data = response.json()

        return {
            "success": True,
            "id": data.get("id"),
            "name": data.get("name"),
            "description": data.get("description"),
            "state": data.get("state"),
            "visibility": data.get("visibility"),
        }

    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
        }


@mcp.tool
def get_active_work_items() -> dict:
    """Returns active Azure DevOps work items for the configured project."""

    wiql_url = (
        f"https://dev.azure.com/{AZDO_ORG}/{AZDO_PROJECT}/"
        f"_apis/wit/wiql?api-version=7.1"
    )

    wiql_query = {
        "query": """
        SELECT
            [System.Id],
            [System.Title],
            [System.WorkItemType],
            [System.State],
            [System.AssignedTo]
        FROM WorkItems
        WHERE
            [System.TeamProject] = @project
            AND [System.State] <> 'Closed'
            AND [System.State] <> 'Removed'
        ORDER BY [System.ChangedDate] DESC
        """
    }

    try:
        wiql_response = httpx.post(
            wiql_url,
            headers=get_auth_header(),
            json=wiql_query,
            timeout=20.0,
        )

        wiql_response.raise_for_status()

        work_items = wiql_response.json().get("workItems", [])

        if not work_items:
            return {
                "success": True,
                "count": 0,
                "items": [],
            }

        ids = [str(item["id"]) for item in work_items[:50]]

        details_url = (
            f"https://dev.azure.com/{AZDO_ORG}/{AZDO_PROJECT}/"
            f"_apis/wit/workitems"
            f"?ids={','.join(ids)}"
            f"&fields=System.Id,System.Title,System.WorkItemType,"
            f"System.State,System.AssignedTo,System.IterationPath"
            f"&api-version=7.1"
        )

        details_response = httpx.get(
            details_url,
            headers=get_auth_header(),
            timeout=20.0,
        )

        details_response.raise_for_status()

        results = []

        for item in details_response.json().get("value", []):
            fields = item.get("fields", {})

            assigned_to = fields.get("System.AssignedTo")

            if isinstance(assigned_to, dict):
                assigned_to = assigned_to.get("displayName")

            results.append(
                {
                    "id": fields.get("System.Id"),
                    "title": fields.get("System.Title"),
                    "type": fields.get("System.WorkItemType"),
                    "state": fields.get("System.State"),
                    "assignedTo": assigned_to,
                    "iterationPath": fields.get("System.IterationPath"),
                }
            )

        return {
            "success": True,
            "count": len(results),
            "items": results,
        }

    except httpx.HTTPStatusError as exc:
        return {
            "success": False,
            "error": "Azure DevOps returned an HTTP error",
            "status_code": exc.response.status_code,
            "details": exc.response.text,
        }

    except Exception as exc:
        return {
            "success": False,
            "error": "Azure DevOps request failed",
            "details": str(exc),
        }

@mcp.tool
def get_iterations() -> dict:
    """Returns Azure DevOps iterations configured for the current project/team."""

    url = (
        f"https://dev.azure.com/{AZDO_ORG}/{AZDO_PROJECT}/"
        f"_apis/work/teamsettings/iterations?api-version=7.1"
    )

    try:
        response = httpx.get(
            url,
            headers=get_auth_header(),
            timeout=20.0,
        )

        response.raise_for_status()

        data = response.json()

        iterations = []

        for item in data.get("value", []):
            attributes = item.get("attributes", {})

            iterations.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "path": item.get("path"),
                    "startDate": attributes.get("startDate"),
                    "finishDate": attributes.get("finishDate"),
                    "timeFrame": attributes.get("timeFrame"),
                }
            )

        return {
            "success": True,
            "count": len(iterations),
            "iterations": iterations,
        }

    except httpx.HTTPStatusError as exc:
        return {
            "success": False,
            "error": "Azure DevOps returned an HTTP error",
            "status_code": exc.response.status_code,
            "details": exc.response.text,
        }

    except Exception as exc:
        return {
            "success": False,
            "error": "Azure DevOps request failed",
            "details": str(exc),
        }


def _fetch_all_iterations() -> list:
    """Returns every iteration configured for the team, unfiltered."""

    url = (
        f"https://dev.azure.com/{AZDO_ORG}/{AZDO_PROJECT}/"
        f"_apis/work/teamsettings/iterations?api-version=7.1"
    )

    response = httpx.get(
        url,
        headers=get_auth_header(),
        timeout=20.0,
    )
    response.raise_for_status()

    return response.json().get("value", [])


def _extract_iteration_number(name: str) -> str | None:
    """
    Extracts the sprint/iteration number embedded in a name, so
    "Sprint 3", "Iteration 3", "iteration3", and "3" can all be
    recognized as referring to the same iteration.

    Returns the number as a string, or None if the name has no
    embedded number at all.
    """

    if not name:
        return None

    match = re.search(r"\d+", name)

    return match.group(0) if match else None


def _build_sprint_summary(iteration: dict) -> dict:
    """
    Builds the completion / health-status summary for a single
    iteration dict as returned by the Azure DevOps iterations API.

    Shared by get_current_sprint_summary and
    get_sprint_summary_by_name so both return identical,
    deterministically-calculated fields.
    """

    try:
        iteration_id = iteration.get("id")
        attributes = iteration.get("attributes", {})

        workitems_url = (
            f"https://dev.azure.com/{AZDO_ORG}/{AZDO_PROJECT}/"
            f"_apis/work/teamsettings/iterations/{iteration_id}/workitems"
            f"?api-version=7.1"
        )

        workitems_response = httpx.get(
            workitems_url,
            headers=get_auth_header(),
            timeout=20.0,
        )
        workitems_response.raise_for_status()

        relations = workitems_response.json().get("workItemRelations", [])

        work_item_ids = []

        for relation in relations:
            target = relation.get("target")

            if target and target.get("id"):
                work_item_ids.append(str(target["id"]))

        work_item_ids = list(dict.fromkeys(work_item_ids))

        if not work_item_ids:
            return {
                "success": True,
                "iteration": {
                    "id": iteration_id,
                    "name": iteration.get("name"),
                    "path": iteration.get("path"),
                    "startDate": attributes.get("startDate"),
                    "finishDate": attributes.get("finishDate"),
                    "timeFrame": attributes.get("timeFrame"),
                },
                "totalWorkItems": 0,
                "completedWorkItems": 0,
                "activeWorkItems": 0,
                "completionPercent": 0,
                "plannedHours": 0,
                "completedHours": 0,
                "remainingHours": 0,
                "items": [],
            }

        ids_param = ",".join(work_item_ids[:200])

        details_url = (
            f"https://dev.azure.com/{AZDO_ORG}/{AZDO_PROJECT}/"
            f"_apis/wit/workitems"
            f"?ids={ids_param}"
            f"&fields=System.Id,System.Title,System.WorkItemType,"
            f"System.State,System.AssignedTo,System.IterationPath,"
            f"Microsoft.VSTS.Scheduling.OriginalEstimate,"
            f"Microsoft.VSTS.Scheduling.CompletedWork,"
            f"Microsoft.VSTS.Scheduling.RemainingWork"
            f"&api-version=7.1"
        )

        details_response = httpx.get(
            details_url,
            headers=get_auth_header(),
            timeout=20.0,
        )
        details_response.raise_for_status()

        items = []
        completed_count = 0
        in_progress_count = 0
        new_count = 0

        planned_hours_total = 0.0
        completed_hours_total = 0.0
        remaining_hours_total = 0.0

        completed_states = {
            "Closed",
            "Done",
            "Resolved",
            "Completed",
        }

        in_progress_states = {
            "Active",
            "In Progress",
            "Committed",
        }

        for item in details_response.json().get("value", []):
            fields = item.get("fields", {})

            assigned_to = fields.get("System.AssignedTo")

            if isinstance(assigned_to, dict):
                assigned_to = assigned_to.get("displayName")

            state = fields.get("System.State")

            original_estimate = fields.get(
                "Microsoft.VSTS.Scheduling.OriginalEstimate"
            ) or 0

            completed_work = fields.get(
                "Microsoft.VSTS.Scheduling.CompletedWork"
            ) or 0

            remaining_work = fields.get(
                "Microsoft.VSTS.Scheduling.RemainingWork"
            ) or 0

            planned_hours_total += original_estimate
            completed_hours_total += completed_work
            remaining_hours_total += remaining_work

            if state in completed_states:
                completed_count += 1
            elif state in in_progress_states:
                in_progress_count += 1
            else:
                new_count += 1

            items.append(
                {
                    "id": fields.get("System.Id"),
                    "title": fields.get("System.Title"),
                    "type": fields.get("System.WorkItemType"),
                    "state": state,
                    "assignedTo": assigned_to,
                    "iterationPath": fields.get("System.IterationPath"),
                    "originalEstimateHours": original_estimate,
                    "completedHours": completed_work,
                    "remainingHours": remaining_work,
                }
            )

        total = len(items)
        remaining = total - completed_count

        completion_percent = (
            round((completed_count / total) * 100, 2)
            if total > 0
            else 0
        )
        start_date_text = attributes.get("startDate")
        finish_date_text = attributes.get("finishDate")

        sprint_elapsed_percent = 0.0

        if start_date_text and finish_date_text:
            start_date = datetime.fromisoformat(
                start_date_text.replace("Z", "+00:00")
            )

            finish_date = datetime.fromisoformat(
                finish_date_text.replace("Z", "+00:00")
            )

            now = datetime.now(timezone.utc)

            total_duration = (
                finish_date - start_date
            ).total_seconds()

            elapsed_duration = (
                now - start_date
            ).total_seconds()

            if total_duration > 0:
                sprint_elapsed_percent = (
                    elapsed_duration / total_duration
                ) * 100

            sprint_elapsed_percent = round(
                max(0, min(100, sprint_elapsed_percent)),
                2
            )

        delivery_gap = round(
            completion_percent - sprint_elapsed_percent,
            2
        )

        if delivery_gap >= -10:
            health_status = "On Track"

        elif delivery_gap >= -25:
            health_status = "At Risk"

        else:
            health_status = "Behind"   
        return {
            "success": True,
            "iteration": {
                "id": iteration_id,
                "name": iteration.get("name"),
                "path": iteration.get("path"),
                "startDate": attributes.get("startDate"),
                "finishDate": attributes.get("finishDate"),
                "timeFrame": attributes.get("timeFrame"),
            },
            "totalWorkItems": total,
            "completedWorkItems": completed_count,
            "newWorkItems": new_count,
            "inProgressWorkItems": in_progress_count,
            "remainingWorkItems": remaining,
            "completionPercent": completion_percent,
            "sprintElapsedPercent": sprint_elapsed_percent,
            "deliveryGapPercent": delivery_gap,
            "healthStatus": health_status,
            "plannedHours": round(planned_hours_total, 2),
            "completedHours": round(completed_hours_total, 2),
            "remainingHours": round(remaining_hours_total, 2),
            "items": items,
        }

    except httpx.HTTPStatusError as exc:
        return {
            "success": False,
            "error": "Azure DevOps returned an HTTP error",
            "status_code": exc.response.status_code,
            "details": exc.response.text,
        }

    except Exception as exc:
        return {
            "success": False,
            "error": "Azure DevOps request failed",
            "details": str(exc),
        }


@mcp.tool
def get_current_sprint_summary() -> dict:
    """Returns summary and work items for the current Azure DevOps iteration."""

    try:
        iterations_url = (
            f"https://dev.azure.com/{AZDO_ORG}/{AZDO_PROJECT}/"
            f"_apis/work/teamsettings/iterations?$timeframe=Current&api-version=7.1"
        )

        iterations_response = httpx.get(
            iterations_url,
            headers=get_auth_header(),
            timeout=20.0,
        )
        iterations_response.raise_for_status()

        iterations = iterations_response.json().get("value", [])

        if not iterations:
            return {
                "success": False,
                "error": "No current iteration found."
            }

        return _build_sprint_summary(iterations[0])

    except httpx.HTTPStatusError as exc:
        return {
            "success": False,
            "error": "Azure DevOps returned an HTTP error",
            "status_code": exc.response.status_code,
            "details": exc.response.text,
        }

    except Exception as exc:
        return {
            "success": False,
            "error": "Azure DevOps request failed",
            "details": str(exc),
        }


@mcp.tool
def get_sprint_summary_by_name(iteration_name: str) -> dict:
    """
    Returns the same completion/health-status summary as
    get_current_sprint_summary, but for a specific named iteration
    (e.g. "Iteration 1", "Iteration 2", "Sprint 3") instead of
    whichever iteration Azure DevOps currently flags as Current.

    Use this whenever the user names a specific sprint/iteration.
    Use get_current_sprint_summary only when the user asks about
    the current/active sprint without naming one.
    """

    try:
        iterations = _fetch_all_iterations()

        normalized_target = iteration_name.strip().lower()

        matching_iteration = next(
            (
                item
                for item in iterations
                if str(item.get("name", "")).strip().lower()
                == normalized_target
            ),
            None,
        )

        # -----------------------------------------------------
        # Fuzzy fallback: match by embedded sprint/iteration
        # number so "Sprint 3", "iteration 3", "iteration3",
        # and "3" all resolve to the same Azure DevOps iteration
        # regardless of exact wording. Only applied when the
        # exact name match above found nothing, and only
        # resolved automatically when the number is unambiguous.
        # -----------------------------------------------------

        if matching_iteration is None:
            target_number = _extract_iteration_number(
                iteration_name
            )

            if target_number is not None:
                number_matches = [
                    item
                    for item in iterations
                    if _extract_iteration_number(
                        str(item.get("name", ""))
                    )
                    == target_number
                ]

                if len(number_matches) == 1:
                    matching_iteration = number_matches[0]

                elif len(number_matches) > 1:
                    return {
                        "success": False,
                        "error": (
                            f"'{iteration_name}' matches more "
                            "than one iteration name."
                        ),
                        "candidates": [
                            item.get("name")
                            for item in number_matches
                        ],
                    }

        if matching_iteration is None:
            available_names = [
                item.get("name")
                for item in iterations
            ]

            return {
                "success": False,
                "error": (
                    f"Iteration '{iteration_name}' was not found."
                ),
                "availableIterations": available_names,
            }

        return _build_sprint_summary(matching_iteration)

    except httpx.HTTPStatusError as exc:
        return {
            "success": False,
            "error": "Azure DevOps returned an HTTP error",
            "status_code": exc.response.status_code,
            "details": exc.response.text,
        }

    except Exception as exc:
        return {
            "success": False,
            "error": "Azure DevOps request failed",
            "details": str(exc),
        }


if __name__ == "__main__":
    mcp.run()