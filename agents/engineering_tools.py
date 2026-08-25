from connectors.d365_timesheet import (
    get_timesheets as fetch_timesheets,
)


def build_engineering_tools(
    mark_source,
    project_register: list[dict] | None = None,
    authorized_sharepoint_ids: list[str] | None = None,
):
    """
    Builds the local (non-MCP) tools for the Data Retrieval Agent:

    - SharePoint: the project register rows already fetched by
      the Copilot Studio flow and passed in with this request.
    - D365 Timesheets: read locally from the CSV path configured
      by D365_TIMESHEETS_PATH.

    Azure DevOps MCP tools are passed separately by the
    orchestration layer, since they come from a running MCP
    server process rather than a plain Python function.

    authorized_sharepoint_ids: the caller's authorized SharePoint
    "Project ID" values (see security/authorization.py). None means
    unrestricted (administrator). This is enforced here, in code -
    not left to the model to respect on its own - so a caller can
    always be told which project NAMES exist, but full row details
    (budget, client, sponsor, risk, schedule) are only ever
    returned for rows this caller is actually authorized for.
    """

    def get_sharepoint_projects() -> dict:
        """
        Returns the SharePoint project register for this request
        (already fetched by the Copilot Studio flow, not queried
        live by this tool).

        Use for: project status, budget/schedule status, risk
        summary, sponsor, phase, milestones, next milestone date -
        anything about overall project health. Not for sprint or
        work-item detail - that's Azure DevOps.

        "projects" contains full row detail, already filtered to
        only what this caller is authorized to see in full.
        "allProjectNames" always lists every project's name,
        regardless of authorization - safe to answer "what
        projects exist" with, even for a project whose full
        details aren't in "projects".
        """

        mark_source(
            "SharePoint"
        )

        if not project_register:
            return {
                "success": False,
                "error": (
                    "No SharePoint project register data "
                    "was supplied for this request."
                ),
            }

        all_project_names = [
            row.get("Project Name")
            for row in project_register
            if row.get("Project Name")
        ]

        if authorized_sharepoint_ids is None:
            authorized_rows = project_register
        else:
            authorized_rows = [
                row
                for row in project_register
                if row.get("Project ID") in authorized_sharepoint_ids
            ]

        return {
            "success": True,
            "projects": authorized_rows,
            "allProjectNames": all_project_names,
        }


    def get_timesheets(
        project_id: str | None = None,
    ) -> dict:
        """
        Returns D365 Project Operations timesheet rows: planned
        vs actual vs billable hours, approval status, and
        utilization percent, per employee per week.

        Use for: who logged time, billable vs actual hours,
        approval status, utilization trends. Not for sprint or
        work-item detail - that's Azure DevOps. Not for overall
        project status - that's SharePoint.

        project_id: optional. Filters to a single project's
        timesheet rows (e.g. "PBI-002"). Omit to get all rows this
        caller is authorized for.
        """

        mark_source(
            "Timesheets"
        )

        if (
            authorized_sharepoint_ids is not None
            and project_id is not None
            and project_id not in authorized_sharepoint_ids
        ):
            return {
                "success": False,
                "error": (
                    f"Not authorized to view timesheets for "
                    f"project '{project_id}'."
                ),
            }

        try:
            rows = fetch_timesheets(
                project_id=project_id
            )

        except FileNotFoundError:
            return {
                "success": False,
                "error": (
                    "Timesheet data file was not found."
                ),
            }

        if (
            authorized_sharepoint_ids is not None
            and project_id is None
        ):
            # Fetch-all case for a non-admin caller - restrict to
            # only their authorized projects' rows, same
            # enforcement as the single-project_id case above.
            rows = [
                row
                for row in rows
                if row.get("project_id") in authorized_sharepoint_ids
            ]

        return {
            "success": True,
            "timesheets": rows,
        }


    return [
        get_sharepoint_projects,
        get_timesheets,
    ]