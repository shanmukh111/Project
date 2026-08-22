from pydantic import BaseModel, Field


class EvidenceSource(BaseModel):
    name: str
    available: bool = True


class DeliveryEvidence(BaseModel):
    """
    Structured evidence returned by the Data Retrieval Agent.

    The numeric fields below exist so the backend can render real
    charts deterministically from Python, rather than asking the
    LLM to produce chart data itself. The retrieval agent's job for
    these fields is transcription, not calculation: copy the exact
    numbers already present in whichever Azure DevOps tool result
    it used. Leave a field null when no tool call actually returned
    it for this question - never estimate or invent a number here.
    """

    branch: str = "delivery"
    success: bool
    summary: str
    sources: list[str] = Field(default_factory=list)

    # Work item status breakdown (from get_current_sprint_summary
    # or get_sprint_summary_by_name), for the status pie chart.
    total_work_items: int | None = None
    completed_work_items: int | None = None
    in_progress_work_items: int | None = None
    new_work_items: int | None = None

    # Effort breakdown (same tools), for the effort bar chart.
    planned_hours: float | None = None
    completed_hours: float | None = None
    remaining_hours: float | None = None

    # Deterministic delivery classification - never overridden by
    # the LLM, always copied verbatim from the tool result.
    completion_percent: float | None = None
    sprint_elapsed_percent: float | None = None
    health_status: str | None = None

    iteration_name: str | None = None


class AnalystReport(BaseModel):
    """
    Final output of the Insight Orchestrator: the narrative answer
    plus any recommendations, kept separate so the API layer can
    render them into distinct sections of the HTML report.
    """

    answer: str
    recommendations: list[str] = Field(default_factory=list)