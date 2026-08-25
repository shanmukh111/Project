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


# -----------------------------------------------------------------
# Per-user Azure DevOps project scoping.
#
# Azure DevOps tools (mcp_server/devops_server.py) are scoped to a
# single AZDO_PROJECT, injected as an environment variable when the
# MCP subprocess is launched fresh for each request (see
# orchestration/delivery_workflow.py). This maps each authorized
# email to the one Azure DevOps project their questions should be
# scoped to - two authorized users can now be answered against two
# genuinely different projects, rather than the whole system
# sharing one hardcoded project regardless of who's asking.
#
# The project name here must exactly match the real Azure DevOps
# project name (case-sensitive).
# -----------------------------------------------------------------

AUTHORIZED_PROJECTS = {
    "nelanti.kumar@maqsoftware.com": "Alpha",
    "shanmukha.regidi@maqsoftware.com": "Jarvis",
}


def resolve_authorized_project(email: str) -> str:
    """
    Returns the Azure DevOps project name this authorized email
    is scoped to.

    Callers should only invoke this after authorize_email() has
    already succeeded for the same email - this function does not
    re-validate the allowlist itself, and raises AuthorizationError
    if the email has no project mapping (which should not happen
    for an already-authorized email; treat it as a configuration
    gap if it does).
    """

    normalized_email = email.strip().lower()

    mapping = {
        mapped_email.lower(): project
        for mapped_email, project in AUTHORIZED_PROJECTS.items()
    }

    project = mapping.get(normalized_email)

    if not project:
        raise AuthorizationError(
            f"'{email}' is authorized but has no Azure DevOps "
            "project mapping configured."
        )

    return project


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