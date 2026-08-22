def build_retrieval_prompt(
    user_id: str,
    user_question: str,
) -> str:
    return f"""
User ID:
{user_id}

Manager question:
{user_question}

Retrieve only the evidence needed to answer this question.

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