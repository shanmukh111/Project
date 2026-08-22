def route_question(
    user_question: str,
    previous_routing: dict | None = None,
) -> dict:
    """
    Deterministically decides which evidence
    branches are relevant to the question.

    previous_routing, when supplied, is the routing decision
    from the prior turn in the same session. It is used only
    as a fallback when this question has no recognizable
    portfolio/engineering signal of its own — for example a
    follow-up like "is it at risk?" that implicitly continues
    the prior turn's topic rather than starting a new one.
    """

    question = user_question.lower()

    portfolio_terms = {
        "project",
        "projects",
        "portfolio",
        "power bi",
        "d365",
        "dynamics",
        "budget",
        "schedule",
        "milestone",
        "timesheet",
        "timesheets",
        "utilization",
        "variance",
    }

    engineering_terms = {
        "sprint",
        "iteration",
        "work item",
        "work items",
        "azure devops",
        "engineering",
        "backlog",
        "completion",
        "delivery gap",
    }

    recommendation_terms = {
        "recommend",
        "recommendation",
        "recommendations",
        "management action",
        "management actions",
        "prioritize",
        "mitigation",
        "what should",
    }

    use_portfolio = any(
        term in question
        for term in portfolio_terms
    )

    use_engineering = any(
        term in question
        for term in engineering_terms
    )

    wants_guidance = any(
        term in question
        for term in recommendation_terms
    )

    if not use_portfolio and not use_engineering:
        if previous_routing is not None and (
            previous_routing.get("portfolio")
            or previous_routing.get("engineering")
        ):
            # Ambiguous follow-up with no domain keyword of its
            # own: continue whichever domain(s) were active last
            # turn instead of defaulting to both. This avoids
            # pulling in an unrelated evidence branch and avoids
            # tripping authorization for a domain the question
            # never actually asked about.
            use_portfolio = bool(
                previous_routing.get("portfolio", False)
            )
            use_engineering = bool(
                previous_routing.get("engineering", False)
            )
        else:
            use_portfolio = True
            use_engineering = True

    return {
        "portfolio": use_portfolio,
        "engineering": use_engineering,
        "guidance": wants_guidance,
    }


def route_devops_tools(
    user_question: str,
) -> list[str]:
    """
    Select the minimum Azure DevOps MCP tool set
    required for the engineering question.
    """

    question = user_question.lower()

    # Sprint health / progress questions
    if (
        "sprint" in question
        or "sprint health" in question
        or "delivery gap" in question
        or "completion" in question
    ):
        return [
            "get_current_sprint_summary",
        ]

    # Work-item / backlog questions
    if (
        "work item" in question
        or "work items" in question
        or "backlog" in question
    ):
        return [
            "get_active_work_items",
        ]

    # Iteration questions
    if (
        "iteration" in question
        or "iterations" in question
    ):
        return [
            "get_iterations",
        ]

    # General Azure DevOps/project information
    return [
        "get_project_info",
    ]