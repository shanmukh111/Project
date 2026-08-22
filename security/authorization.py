from dataclasses import dataclass
import time
import uuid
from threading import Lock


@dataclass(frozen=True)
class UserAccess:
    user_id: str
    role: str
    can_view_portfolio: bool
    can_view_engineering: bool
    can_view_timesheets: bool


# ---------------------------------------------------------
# Demo authorization map
#
# Production replacement:
# Microsoft Entra ID claims / groups / app roles.
# ---------------------------------------------------------

AUTHORIZED_USERS = {
    "manager01": UserAccess(
        user_id="manager01",
        role="DeliveryManager",
        can_view_portfolio=True,
        can_view_engineering=True,
        can_view_timesheets=True,
    ),

    "engineering01": UserAccess(
        user_id="engineering01",
        role="EngineeringLead",
        can_view_portfolio=False,
        can_view_engineering=True,
        can_view_timesheets=False,
    ),

    "portfolio01": UserAccess(
        user_id="portfolio01",
        role="PortfolioLead",
        can_view_portfolio=True,
        can_view_engineering=False,
        can_view_timesheets=True,
    ),
}


class AuthorizationError(Exception):
    """
    Raised when a user is unknown or is not permitted
    to access the requested evidence domain.
    """


def get_user_access(
    user_id: str,
) -> UserAccess:
    """
    Returns the access profile for a known demo user.
    """

    normalized_user_id = (
        user_id.strip().lower()
    )

    access = AUTHORIZED_USERS.get(
        normalized_user_id
    )

    if access is None:
        raise AuthorizationError(
            "User is not authorized."
        )

    return access


def authorize_route(
    *,
    user_id: str,
    routing: dict,
) -> UserAccess:
    """
    Validates whether the user can access the
    evidence domains required by the routing decision.
    """

    access = get_user_access(
        user_id
    )

    if (
        routing.get("portfolio")
        and not access.can_view_portfolio
    ):
        raise AuthorizationError(
            "User is not authorized "
            "for portfolio evidence."
        )

    if (
        routing.get("engineering")
        and not access.can_view_engineering
    ):
        raise AuthorizationError(
            "User is not authorized "
            "for engineering evidence."
        )

    return access


# ---------------------------------------------------------
# Login sessions
#
# A logged-in manager receives a session_id and uses it on
# every subsequent /delivery/query call instead of re-sending
# their user_id. This closes the gap where any caller could
# previously claim to be any user_id, and it doubles as the
# identity that conversational memory (AgentSession) is keyed
# on, so a manager who logs in once and asks several questions
# gets continuity across them.
#
# Production replacement: real token issuance backed by
# Microsoft Entra ID, not an in-memory map.
# ---------------------------------------------------------

SESSION_IDLE_TIMEOUT_SECONDS = 8 * 60 * 60  # 8 hours


class SessionExpiredError(AuthorizationError):
    """
    Raised when a session_id is unknown, was never issued, or
    has gone idle past SESSION_IDLE_TIMEOUT_SECONDS.
    """


@dataclass
class LoginSession:
    session_id: str
    user_id: str
    role: str
    created_at: float
    last_seen_at: float


_login_sessions: dict[str, LoginSession] = {}
_session_lock = Lock()


def create_login_session(
    user_id: str,
) -> LoginSession:
    """
    Validates user_id against the authorization map and issues
    a new login session for it.

    Raises AuthorizationError if user_id is not recognized.
    """

    access = get_user_access(user_id)

    now = time.time()

    session = LoginSession(
        session_id=str(uuid.uuid4()),
        user_id=access.user_id,
        role=access.role,
        created_at=now,
        last_seen_at=now,
    )

    with _session_lock:
        _login_sessions[session.session_id] = session

    return session


def resolve_login_session(
    session_id: str,
) -> UserAccess:
    """
    Resolves a session_id back to the authenticated user's
    access profile and refreshes its idle-expiry window.

    Raises SessionExpiredError if the session is unknown or
    has expired.
    """

    with _session_lock:
        session = _login_sessions.get(session_id)

        if session is None:
            raise SessionExpiredError(
                "Session is invalid or has expired. "
                "Please log in again."
            )

        now = time.time()

        if (
            now - session.last_seen_at
            > SESSION_IDLE_TIMEOUT_SECONDS
        ):
            del _login_sessions[session_id]

            raise SessionExpiredError(
                "Session is invalid or has expired. "
                "Please log in again."
            )

        session.last_seen_at = now

    return get_user_access(session.user_id)


def end_login_session(
    session_id: str,
) -> None:
    """Logs a session out immediately, if it exists."""

    with _session_lock:
        _login_sessions.pop(session_id, None)