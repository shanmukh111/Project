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