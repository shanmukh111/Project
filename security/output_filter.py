import re


_SECRET_PATTERNS = [
    # OpenAI-style API keys
    re.compile(
        r"\bsk-[A-Za-z0-9_\-]{20,}\b"
    ),

    # Bearer tokens / JWT-like values
    re.compile(
        r"\bBearer\s+[A-Za-z0-9._\-]{20,}\b",
        re.IGNORECASE,
    ),

    # JWT tokens
    re.compile(
        r"\beyJ[A-Za-z0-9_\-]+"
        r"\.[A-Za-z0-9_\-]+"
        r"\.[A-Za-z0-9_\-]+\b"
    ),

    # Common secret assignment patterns
    re.compile(
        r"(?i)\b("
        r"api[_\-]?key|"
        r"access[_\-]?token|"
        r"secret|"
        r"password|"
        r"pat"
        r")\b"
        r"\s*[:=]\s*"
        r"[^\s,;]+"
    ),
]


def redact_secrets(
    text: str,
) -> tuple[str, bool]:
    """
    Redacts high-risk secret patterns from model output.

    Returns:
        (sanitized_text, secret_detected)
    """

    if not text:
        return text, False

    sanitized = text
    detected = False

    for pattern in _SECRET_PATTERNS:
        updated = pattern.sub(
            "[REDACTED_SECRET]",
            sanitized,
        )

        if updated != sanitized:
            detected = True

        sanitized = updated

    return sanitized, detected


# ---------------------------------------------------------
# Out-of-scope source mention filtering
#
# Prompt instructions alone did not reliably stop the model from
# mentioning sources that were never queried for a given question
# (e.g. "Work items: Not provided in the returned evidence" or
# "Ensure Azure DevOps boards are up to date" on a SharePoint-only
# answer). This deterministically strips any line referencing a
# source not in sources_used, the same way secret redaction is
# handled in code rather than left to instruction-following.
# ---------------------------------------------------------

_SOURCE_TERMS = {
    "Azure DevOps": [
        "azure devops",
        "work item",
        "work-item",
        "sprint",
        "devops board",
        "elapsed time",
        "elapsed-time",
    ],
    "SharePoint": [
        "sharepoint",
        "project register",
    ],
    "Timesheets": [
        "timesheet",
        "d365",
    ],
}


def filter_out_of_scope_sources(
    text: str,
    sources_used: list[str],
) -> tuple[str, bool]:
    """
    Removes any line that references a data source not actually
    used to answer this question (e.g. a stray "no Azure DevOps
    data was returned" line on a SharePoint-only answer).

    Returns:
        (filtered_text, line_removed)
    """

    if not text:
        return text, False

    forbidden_terms = []

    for source, terms in _SOURCE_TERMS.items():
        if source not in sources_used:
            forbidden_terms.extend(terms)

    if not forbidden_terms:
        return text, False

    lines = text.split("\n")
    kept_lines = []
    removed = False

    for line in lines:
        lower_line = line.lower()

        if any(
            term in lower_line
            for term in forbidden_terms
        ):
            removed = True
            continue

        kept_lines.append(line)

    return "\n".join(kept_lines), removed