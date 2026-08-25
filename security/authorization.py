"""
security/authorization.py

Access is granted by a flat email allowlist, matching real Teams
identity (Copilot Studio's User.Email) rather than a self-declared
user_id string. There is no login/session-issuance step anymore -
every request carries the caller's email directly, and it's
checked against the allowlist on each call.

The authorized email itself doubles as the key for conversational
memory (see orchestration/delivery_workflow.py's session_id
parameter) - one real identity per person is a stable, natural key,
so no separate session token needs to be issued or tracked.
"""

from dataclasses import dataclass


AUTHORIZED_EMAILS = {
    "nelanti.kumar@maqsoftware.com",
    "shanmukha.regidi@maqsoftware.com",
}


class AuthorizationError(Exception):
    """Raised when the caller's email is not on the allowlist."""


@dataclass
class UserAccess:
    email: str


def authorize_email(email: str) -> UserAccess:
    """
    Checks the given email against the allowlist.

    Raises AuthorizationError if the email is missing or not
    authorized.
    """

    if not email or not email.strip():
        raise AuthorizationError(
            "No email was provided."
        )

    normalized_email = email.strip().lower()

    allowed = {
        allowed_email.lower()
        for allowed_email in AUTHORIZED_EMAILS
    }

    if normalized_email not in allowed:
        raise AuthorizationError(
            f"'{email}' is not authorized to use this agent."
        )

    return UserAccess(
        email=normalized_email,
    )


# -----------------------------------------------------------------
# Per-user access tiers.
#
# Two dimensions of access, per authorized email:
#
# - ado_projects: which Azure DevOps project(s) this caller may
#   see live sprint/work-item data for. mcp_server/devops_server.py
#   is scoped to a single AZDO_PROJECT per request (injected as an
#   environment variable when the MCP subprocess is launched fresh
#   for each request - see orchestration/delivery_workflow.py), so
#   for a caller authorized for more than one project, the specific
#   project used for a given request is resolved from the
#   question's own wording (see resolve_ado_project_for_question).
#
# - sharepoint_project_ids: which SharePoint "Project ID" rows this
#   caller may see full details for (budget, client, sponsor, risk,
#   schedule). None means unrestricted (administrator) - every
#   other value is an explicit allowlist. A caller who is NOT
#   authorized for a given project can still be told that project's
#   NAME exists (see agents/engineering_tools.py's
#   "allProjectNames") - only the detailed row is withheld.
#
# is_admin exists as an explicit flag (not just "sharepoint_project_
# ids is None") so a future admin with a real project restriction
# doesn't accidentally read as "unrestricted" by omission.
# -----------------------------------------------------------------

AUTHORIZED_ACCESS = {
    "shanmukha.regidi@maqsoftware.com": {
        "is_admin": True,
        "ado_projects": ["Jarvis", "Alpha"],
        "sharepoint_project_ids": None,
    },
    "nelanti.kumar@maqsoftware.com": {
        "is_admin": False,
        "ado_projects": ["Alpha"],
        "sharepoint_project_ids": ["ALP-001", "ALP-002"],
    },
}

# Every Azure DevOps project name that exists anywhere in this
# system, regardless of who's authorized for it - used to detect
# when a caller explicitly names a project they're NOT authorized
# for, as opposed to a project that simply doesn't exist at all.
ALL_KNOWN_ADO_PROJECTS = ["Jarvis", "Alpha"]


@dataclass
class AccessProfile:
    email: str
    is_admin: bool
    ado_projects: list[str]
    sharepoint_project_ids: list[str] | None  # None = unrestricted


def get_access_profile(email: str) -> AccessProfile:
    """
    Returns the full access profile for an already-authorized
    email.

    Callers should only invoke this after authorize_email() has
    already succeeded for the same email - this function does not
    re-validate the allowlist itself, and raises AuthorizationError
    if the email has no access profile configured (which should not
    happen for an already-authorized email; treat it as a
    configuration gap if it does).
    """

    normalized_email = email.strip().lower()

    mapping = {
        mapped_email.lower(): profile
        for mapped_email, profile in AUTHORIZED_ACCESS.items()
    }

    profile = mapping.get(normalized_email)

    if not profile:
        raise AuthorizationError(
            f"'{email}' is authorized but has no access profile "
            "configured."
        )

    sharepoint_ids = profile["sharepoint_project_ids"]

    return AccessProfile(
        email=normalized_email,
        is_admin=profile["is_admin"],
        ado_projects=list(profile["ado_projects"]),
        sharepoint_project_ids=(
            None if sharepoint_ids is None else list(sharepoint_ids)
        ),
    )


def resolve_ado_project_for_question(
    access: AccessProfile,
    user_question: str,
) -> tuple[str, str | None]:
    """
    Decides which single Azure DevOps project this request's MCP
    subprocess should be scoped to, and whether the caller named a
    project they are not authorized for.

    Returns (scoped_project, unauthorized_named_project):
      - scoped_project: the project to actually inject as
        AZDO_PROJECT for this request. If the question names one of
        the caller's own authorized projects, that one is used. If
        it names no project, or names one the caller isn't
        authorized for, this falls back to the caller's first
        authorized project (a safe default - the MCP subprocess
        always needs some valid project to start against).
      - unauthorized_named_project: the project name the caller
        asked about but is not authorized for, or None if the
        question didn't name one, or named one they ARE authorized
        for. Callers (delivery_workflow.py) pass this through to
        the retrieval agent's prompt so it can state plainly that
        details for that project are not authorized, instead of
        silently answering about the fallback project instead.
    """

    question_lower = user_question.lower()

    matched_authorized = next(
        (
            project
            for project in access.ado_projects
            if project.lower() in question_lower
        ),
        None,
    )

    if matched_authorized:
        return matched_authorized, None

    unauthorized_named_project = next(
        (
            project
            for project in ALL_KNOWN_ADO_PROJECTS
            if project.lower() in question_lower
            and project not in access.ado_projects
        ),
        None,
    )

    fallback_project = access.ado_projects[0]

    return fallback_project, unauthorized_named_project