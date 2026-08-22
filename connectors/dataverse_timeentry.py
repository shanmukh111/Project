import os
import re
import subprocess
import json
import time
from threading import Lock
import httpx
from dotenv import load_dotenv

load_dotenv()

DATAVERSE_URL = os.getenv(
    "DATAVERSE_URL",
    "https://org41a6fc2f.crm.dynamics.com"
)

DATAVERSE_API_VERSION = os.getenv(
    "DATAVERSE_API_VERSION",
    "v9.2"
)

DATAVERSE_ENTITY_SET = os.getenv(
    "DATAVERSE_ENTITY_SET",
    "cr1e5_timeentries"
)

# ---------------------------------------------------------
# Token cache
#
# get_access_token() previously launched a fresh PowerShell
# process on every single call. When a question touches many
# projects (e.g. several at-risk projects in one request), this
# was called once per project and dominated total latency,
# which is what was causing Copilot Studio to perceive a
# timeout and retry the whole request.
#
# Azure AD access tokens are typically valid ~60-90 minutes.
# We cache for a conservative 45 minutes and refetch after that.
# ---------------------------------------------------------

_TOKEN_CACHE_TTL_SECONDS = 45 * 60

_cached_token: str | None = None
_cached_token_fetched_at: float = 0.0
_token_lock = Lock()


def _fetch_access_token_from_powershell() -> str:
    """
    Gets a fresh Dataverse access token using the already
    authenticated Azure PowerShell session.

    Security:
    - Suppresses PowerShell warning/progress noise.
    - Extracts only the value between explicit token markers.
    - Never prints or exposes the token in application errors.
    """

    powershell_command = f"""
    $ErrorActionPreference = "Stop"
    $WarningPreference = "SilentlyContinue"
    $ProgressPreference = "SilentlyContinue"
    $InformationPreference = "SilentlyContinue"
    $VerbosePreference = "SilentlyContinue"
    $DebugPreference = "SilentlyContinue"

    $secureToken = (
        Get-AzAccessToken `
            -ResourceUrl "{DATAVERSE_URL}/" `
            -AsSecureString `
            -WarningAction SilentlyContinue
    ).Token

    $token = [System.Net.NetworkCredential]::new(
        "",
        $secureToken
    ).Password

    Write-Output ("__TOKEN_BEGIN__" + $token + "__TOKEN_END__")
    """

    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            powershell_command,
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "Unable to retrieve Dataverse access token."
        )

    match = re.search(
        r"__TOKEN_BEGIN__(.*?)__TOKEN_END__",
        result.stdout,
        flags=re.DOTALL,
    )

    if match is None:
        raise RuntimeError(
            "Unable to retrieve Dataverse access token."
        )

    token = match.group(1).strip()

    if (
        not token
        or any(
            character in token
            for character in (
                "\r",
                "\n",
                "\t",
                " ",
            )
        )
    ):
        raise RuntimeError(
            "Unable to retrieve Dataverse access token."
        )

    return token


def get_access_token() -> str:
    """
    Returns a cached Dataverse access token, refetching from
    PowerShell only when the cache is empty or has aged past
    _TOKEN_CACHE_TTL_SECONDS.

    This avoids launching a new PowerShell process for every
    Dataverse call — previously happened once per project when
    a question touched multiple projects, which dominated
    request latency.
    """

    global _cached_token
    global _cached_token_fetched_at

    now = time.time()

    if (
        _cached_token is not None
        and (now - _cached_token_fetched_at)
        < _TOKEN_CACHE_TTL_SECONDS
    ):
        return _cached_token

    with _token_lock:
        now = time.time()

        if (
            _cached_token is not None
            and (now - _cached_token_fetched_at)
            < _TOKEN_CACHE_TTL_SECONDS
        ):
            return _cached_token

        _cached_token = (
            _fetch_access_token_from_powershell()
        )
        _cached_token_fetched_at = now

        return _cached_token

def get_headers() -> dict:
    token = get_access_token()

    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "OData-MaxVersion": "4.0",
        "OData-Version": "4.0",
        "Prefer": (
            'odata.include-annotations="'
            'OData.Community.Display.V1.FormattedValue"'
        ),
    }


def get_time_entries(
    project_id: str | None = None,
    top: int = 100,
) -> list[dict]:

    fields = [
        "cr1e5_timeentryid1",
        "cr1e5_projectid",
        "cr1e5_projectname",
        "cr1e5_employeeid",
        "cr1e5_employeename",
        "cr1e5_employeerole",
        "cr1e5_technologyused",
        "cr1e5_plannedhours",
        "cr1e5_actualhours",
        "cr1e5_billablehours",
        "cr1e5_utilizationpercentage",
        "cr1e5_billableutilizationpercentage",
        "cr1e5_variancehours",
        "cr1e5_variancepercentage",
        "cr1e5_approvalstatus",
        "cr1e5_timesheetstatus",
        "cr1e5_riskindicator",
        "cr1e5_managercomments",
        "cr1e5_workdate",
        "cr1e5_lastupdated",
    ]

    params = {
        "$select": ",".join(fields),
        "$top": top,
    }

    if project_id:
        params["$filter"] = (
            f"cr1e5_projectid eq '{project_id}'"
        )

    url = (
        f"{DATAVERSE_URL}"
        f"/api/data/{DATAVERSE_API_VERSION}"
        f"/{DATAVERSE_ENTITY_SET}"
    )

    with httpx.Client(timeout=30) as client:
        response = client.get(
            url,
            headers=get_headers(),
            params=params,
        )

        response.raise_for_status()

        return response.json()["value"]


def get_project_timesheet_summary(
    project_id: str,
) -> dict:

    rows = get_time_entries(
        project_id=project_id,
        top=500,
    )

    if not rows:
        return {
            "project_id": project_id,
            "entry_count": 0,
            "planned_hours": 0,
            "actual_hours": 0,
            "billable_hours": 0,
            "variance_hours": 0,
            "variance_percent": 0,
            "average_utilization_percent": 0,
            "pending_approvals": 0,
            "high_risk_entries": 0,
        }

    planned_hours = sum(
        float(row.get("cr1e5_plannedhours", 0) or 0)
        for row in rows
    )

    actual_hours = sum(
        float(row.get("cr1e5_actualhours", 0) or 0)
        for row in rows
    )

    billable_hours = sum(
        float(row.get("cr1e5_billablehours", 0) or 0)
        for row in rows
    )

    average_utilization = (
        sum(
            float(
                row.get(
                    "cr1e5_utilizationpercentage",
                    0,
                ) or 0
            )
            for row in rows
        )
        / len(rows)
    )

    pending_approvals = 0
    high_risk_entries = 0

    for row in rows:
        approval_label = row.get(
            "cr1e5_approvalstatus"
            "@OData.Community.Display.V1.FormattedValue"
        )

        risk_label = row.get(
            "cr1e5_riskindicator"
            "@OData.Community.Display.V1.FormattedValue"
        )

        if approval_label == "Pending":
            pending_approvals += 1

        if risk_label == "High":
            high_risk_entries += 1

    variance_hours = actual_hours - planned_hours

    variance_percent = (
        (variance_hours / planned_hours) * 100
        if planned_hours > 0
        else 0
    )

    return {
        "project_id": project_id,
        "entry_count": len(rows),
        "planned_hours": round(planned_hours, 2),
        "actual_hours": round(actual_hours, 2),
        "billable_hours": round(billable_hours, 2),
        "variance_hours": round(variance_hours, 2),
        "variance_percent": round(
            variance_percent,
            2,
        ),
        "average_utilization_percent": round(
            average_utilization,
            2,
        ),
        "pending_approvals": pending_approvals,
        "high_risk_entries": high_risk_entries,
    }


if __name__ == "__main__":
    print(
        json.dumps(
            get_project_timesheet_summary(
                "PBI-004"
            ),
            indent=2,
        )
    )