from connectors.d365_timesheet import (
    get_timesheets as fetch_timesheets,
)


def build_engineering_tools(
    mark_source,
    project_register: list[dict] | None = None,
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

        return {
            "success": True,
            "projects": project_register,
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
        timesheet rows (e.g. "PBI-002"). Omit to get all rows.
        """

        mark_source(
            "Timesheets"
        )

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

        return {
            "success": True,
            "timesheets": rows,
        }


    return [
        get_sharepoint_projects,
        get_timesheets,
    ]