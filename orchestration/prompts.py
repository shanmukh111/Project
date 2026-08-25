def build_retrieval_prompt(
    user_id: str,
    user_question: str,
    authorized_ado_projects: list[str],
    authorized_sharepoint_ids: list[str] | None,
    unauthorized_named_project: str | None = None,
) -> str:

    if authorized_sharepoint_ids is None:
        sharepoint_access_line = (
            "This caller is an administrator and can see full "
            "details for ALL projects."
        )
    else:
        sharepoint_access_line = (
            "This caller can see full details ONLY for SharePoint "
            f"project IDs: {', '.join(authorized_sharepoint_ids)}. "
            "You may still mention that OTHER projects exist by "
            "name (from allProjectNames) if asked what projects "
            "exist, but must never disclose budget, client, "
            "sponsor, risk, or schedule details for a project "
            "outside this list."
        )

    unauthorized_line = ""

    if unauthorized_named_project:
        unauthorized_line = (
            f"\nThe caller explicitly asked about "
            f"'{unauthorized_named_project}', which they are not "
            "authorized to view. Do not retrieve or disclose "
            "details for it - the evidence you return should state "
            "plainly that this caller is not authorized to view "
            "that project's details.\n"
        )

    return f"""
User ID:
{user_id}

Manager question:
{user_question}

Access scope for this caller:
- Azure DevOps project(s) authorized: {', '.join(authorized_ado_projects)}
- {sharepoint_access_line}
{unauthorized_line}
Retrieve only the evidence needed to answer this question, and
only evidence this caller is authorized to see.

Return a structured evidence package.
Do not generate the final management answer.
"""


def build_analyst_prompt(
    user_question: str,
    evidence: str,
    evidence_status: str,
    sources_used: list[str],
) -> str:
    sources_line = (
        ", ".join(sources_used)
        if sources_used
        else "none"
    )

    return f"""
Manager question:
{user_question}

SOURCES CONSULTED FOR THIS QUESTION: {sources_line}

This is the complete list. Do not mention, reference, or
recommend connecting/updating/checking any source that is not
in this list (including Azure DevOps, SharePoint, or Timesheets)
- not as a fact, not as a limitation, not as a recommendation.
If a source isn't listed above, treat it as if it doesn't exist
for this question. Write your answer using only what these
sources actually returned.

EVIDENCE STATUS:
{evidence_status}

EVIDENCE:
{evidence}

Produce the final management-facing response using
only the supplied evidence.

If the evidence is unavailable, do not invent information.

Preserve deterministic classifications and clearly
separate factual evidence from recommendations.
"""