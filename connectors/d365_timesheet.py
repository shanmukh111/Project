import csv
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DATA_FILE = Path(
    os.getenv(
        "D365_TIMESHEETS_PATH",
        "data/d365/timesheets.csv",
    )
)


def get_timesheets(
    project_id: str | None = None,
) -> list[dict]:
    """Returns D365 Project Operations timesheet export records."""

    timesheets = []

    with DATA_FILE.open(
        mode="r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        reader = csv.DictReader(file)

        for row in reader:
            if project_id:
                if row["project_id"].lower() != project_id.lower():
                    continue

            row["planned_hours"] = float(
                row["planned_hours"]
            )

            row["actual_hours"] = float(
                row["actual_hours"]
            )

            row["billable_hours"] = float(
                row["billable_hours"]
            )

            row["utilization_percent"] = float(
                row["utilization_percent"]
            )

            timesheets.append(row)

    return timesheets
def get_project_timesheet_summary(
    project_id: str,
) -> dict:
    """Returns aggregated timesheet signals for a project."""

    rows = get_timesheets(project_id=project_id)

    if not rows:
        return {
            "project_id": project_id,
            "planned_hours": 0,
            "actual_hours": 0,
            "billable_hours": 0,
            "variance_hours": 0,
            "variance_percent": 0,
            "average_utilization_percent": 0,
            "pending_approvals": 0,
        }

    planned_hours = sum(
        row["planned_hours"] for row in rows
    )

    actual_hours = sum(
        row["actual_hours"] for row in rows
    )

    billable_hours = sum(
        row["billable_hours"] for row in rows
    )

    pending_approvals = sum(
        1
        for row in rows
        if row["approval_status"].lower() == "pending"
    )

    average_utilization = (
        sum(
            row["utilization_percent"]
            for row in rows
        )
        / len(rows)
    )

    variance_hours = actual_hours - planned_hours

    variance_percent = (
        (variance_hours / planned_hours) * 100
        if planned_hours > 0
        else 0
    )

    return {
        "project_id": project_id,
        "planned_hours": round(planned_hours, 2),
        "actual_hours": round(actual_hours, 2),
        "billable_hours": round(billable_hours, 2),
        "variance_hours": round(variance_hours, 2),
        "variance_percent": round(variance_percent, 2),
        "average_utilization_percent": round(
            average_utilization,
            2
        ),
        "pending_approvals": pending_approvals,
    }