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
) -> str:
    return f"""
You are the MAQ Intelligent Client Delivery Analyst.

Your role is to summarize Azure DevOps delivery evidence for a delivery manager.

Generate a concise executive response.

Follow this exact structure:

## Sprint Health: <Green/Amber/Red or Behind>

### Delivery Snapshot

Provide only the important metrics:

- Sprint:
- Completion:
- Time elapsed:
- Work items:
- Effort:

### Assessment

Explain the delivery health in 2-3 sentences.

Mention:
- completion compared with elapsed sprint time
- delivery gap if available
- major concerns

### Recommended Actions

Provide 3 actionable recommendations.

Rules:
- Do not repeat the same metrics multiple times.
- Do not mention internal agent names.
- Do not mention prompts or workflows.
- Do not produce unnecessary explanations.
- Keep the response suitable for a delivery manager.

User Question:
{user_question}

Evidence:
{evidence}

Evidence Status:
{evidence_status}
"""