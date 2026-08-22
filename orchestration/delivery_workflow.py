import uuid
from collections.abc import Awaitable, Callable

from agent_framework import (
    AgentSession,
    FunctionInvocationContext,
    MCPStdioTool,
    SessionStore,
)

from orchestration.evidence_models import (
    DeliveryEvidence,
)

from orchestration.evidence_validation import (
    run_with_single_retry,
)

from orchestration.prompts import (
    build_analyst_prompt,
    build_retrieval_prompt,
)

from agents.analyst_agent import (
    create_analyst_agent,
)

from agents.engineering_agent import (
    create_engineering_agent,
)

from agents.engineering_tools import (
    build_engineering_tools,
)

from agents.analyst_tools import (
    build_analyst_tools,
)

from reporting.charts import (
    build_effort_bar_chart,
    build_html_report,
    build_status_pie_chart,
    save_chart_png,
)

from security.output_filter import (
    filter_out_of_scope_sources,
)


AZURE_DEVOPS_TOOLS = {
    "get_project_info",
    "get_active_work_items",
    "get_iterations",
    "get_current_sprint_summary",
    "get_sprint_summary_by_name",
}


# -----------------------------------------------------
# Per-session conversational memory
#
# _agent_session_store holds a MAF AgentSession snapshot for the
# Data Retrieval Agent so it remembers prior turns/tool results
# within the same logged-in session, even though a brand-new
# Agent object is created for every request.
#
# Process-local; resets on restart. A multi-instance production
# deployment would need a shared backing store (Redis, Cosmos DB,
# etc.) implementing the same interface.
# -----------------------------------------------------

_agent_session_store = SessionStore()


async def _load_agent_session(
    session_id: str | None,
) -> AgentSession | None:
    """
    Loads the stored AgentSession for this login session_id.
    Returns a fresh AgentSession if none exists yet, or None if
    session_id was not supplied (memory-less request).
    """

    if not session_id:
        return None

    scoped_id = f"{session_id}:retrieval"

    stored = await _agent_session_store.get(scoped_id)

    return stored or AgentSession(session_id=scoped_id)


async def _save_agent_session(
    session_id: str | None,
    session: AgentSession | None,
) -> None:
    """Persists the AgentSession back to the store after a run."""

    if not session_id or session is None:
        return

    scoped_id = f"{session_id}:retrieval"

    await _agent_session_store.set(scoped_id, session)


async def run_delivery_workflow(
    *,
    user_id: str,
    session_id: str | None,
    user_question: str,
    mark_source,
    sources_used: set,
    project_register: list[dict] | None = None,
) -> dict:
    """
    Executes the MAQ two-agent delivery workflow.

    Flow:

        Data Retrieval Agent (free tool selection over Azure
        DevOps, SharePoint, and D365 Timesheets - no deterministic
        pre-routing; the agent reasons about which source(s) the
        question needs, per its few-shot instructions, and can
        call more than one in the same turn)
                |
                v
        validation / retry
                |
                v
        Insight Orchestrator (reasoning + narrative answer,
        with its own Hybrid RAG tool for guidance/recommendations)
                |
                v
        Chart + HTML report generation (deterministic,
        built from the evidence's numeric fields - never
        from anything the LLM produced)
    """

    # -----------------------------------------------------
    # Authorization
    #
    # Authorization is a flat email allowlist check done before
    # this function is called (security.authorization.authorize_email).
    # No per-domain routing check is needed here.
    # -----------------------------------------------------

    print(
        "[Workflow] Running for user:",
        user_id,
    )


    # -----------------------------------------------------
    # Request-scoped tools
    #
    # SharePoint uses project_register data already fetched by
    # the calling flow. Timesheets reads a local CSV. Azure
    # DevOps MCP is set up separately below (a running process,
    # not a plain function). The retrieval agent decides for
    # itself which of these a question actually needs, per its
    # few-shot instructions.
    # -----------------------------------------------------

    retrieval_tools = (
        build_engineering_tools(
            mark_source=mark_source,
            project_register=project_register,
        )
    )


    # -----------------------------------------------------
    # Conversational memory for this login session
    # -----------------------------------------------------

    retrieval_agent_session = await _load_agent_session(
        session_id,
    )


    # -----------------------------------------------------
    # Azure DevOps source tracking middleware
    # -----------------------------------------------------

    async def track_tool_usage(
        context: FunctionInvocationContext,
        call_next:
            Callable[
                [],
                Awaitable[None],
            ],
    ) -> None:

        tool_name = (
            context.function.name
        )

        print(
            "[ToolTracking] "
            f"Retrieval called: {tool_name}"
        )

        normalized_name = (
            tool_name.lower()
        )

        is_azure_devops_tool = (
            "azure_devops"
            in normalized_name
            or any(
                tool_name_item
                in normalized_name
                for tool_name_item
                in AZURE_DEVOPS_TOOLS
            )
        )

        if is_azure_devops_tool:
            mark_source(
                "Azure DevOps"
            )

        # Execute the tool normally.
        await call_next()

        # Azure DevOps MCP tools are single-use within one agent run.
        #
        # This preserves MCP/autonomous tool selection, but prevents the
        # function-invocation loop from requesting the exact same live
        # Azure DevOps operation repeatedly after it already returned.
        #
        # FunctionInvocationContext.remove_tools(...) updates the live tool
        # list for the NEXT model/tool iteration.
        if is_azure_devops_tool:
            context.remove_tools(
                [tool_name]
            )

            print(
                "[ToolControl] Removed single-use "
                f"Azure DevOps tool: {tool_name}"
            )


    # -----------------------------------------------------
    # Azure DevOps MCP lifetime
    # -----------------------------------------------------

    async with MCPStdioTool(
        name="azure_devops",
        command="python",
        args=[
            "mcp_server/devops_server.py"
        ],
    ) as devops_mcp:

        async with (
            create_engineering_agent(
                middleware=[
                    track_tool_usage,
                ],
            )
        ) as retrieval_agent:

            async def run_retrieval():
                """
                Single evidence-gathering branch. The agent
                freely chooses among Azure DevOps, SharePoint,
                and Timesheets, per its few-shot instructions -
                there is no deterministic pre-routing step.
                """

                prompt = build_retrieval_prompt(
                    user_id=user_id,
                    user_question=user_question,
                )

                return await retrieval_agent.run(
                    prompt,
                    tools=[
                        devops_mcp,
                        *retrieval_tools,
                    ],
                    session=retrieval_agent_session,
                    options={
                        "response_format": DeliveryEvidence,
                    },
                )

            retrieval_result = (
                await run_with_single_retry(
                    run_retrieval,
                    "Data Retrieval Agent",
                    DeliveryEvidence,
                )
            )


    # -----------------------------------------------------
    # Persist conversational memory for this login session
    # -----------------------------------------------------

    await _save_agent_session(
        session_id,
        retrieval_agent_session,
    )


    # -----------------------------------------------------
    # Evidence validation summary
    # -----------------------------------------------------

    retrieval_status = (
        retrieval_result["status"]
    )

    print(
        "[Workflow] Retrieval status:",
        retrieval_status,
    )

    if not retrieval_result["success"]:
        raise RuntimeError(
            "The Data Retrieval Agent could not "
            "gather evidence for this question."
        )


    # -----------------------------------------------------
    # Agent 2 — Insight Orchestrator
    # -----------------------------------------------------

    analyst_prompt = (
        build_analyst_prompt(
            user_question=user_question,
            evidence=retrieval_result["text"],
            evidence_status=retrieval_status,
            sources_used=sorted(sources_used),
        )
    )

    print(
        "[Workflow] Starting "
        "Insight Orchestrator..."
    )

    analyst_tools = (
        build_analyst_tools(
            mark_source=mark_source,
        )
    )

    async with (
        create_analyst_agent()
    ) as analyst_agent:

        analyst_response = (
            await analyst_agent.run(
                analyst_prompt,
                tools=analyst_tools,
            )
        )

    print(
        "[Workflow] Insight Orchestrator complete."
    )

    filtered_answer, lines_removed = (
        filter_out_of_scope_sources(
            analyst_response.text,
            sorted(sources_used),
        )
    )

    if lines_removed:
        print(
            "[Workflow] Removed out-of-scope "
            "source reference(s) from the answer."
        )


    # -----------------------------------------------------
    # Deterministic chart + HTML report generation
    #
    # Built entirely from retrieval_result["evidence_dict"]'s
    # numeric fields - never from anything the LLM wrote in its
    # own text, so the charts stay as trustworthy as the
    # underlying deterministic sprint-health numbers they're
    # drawn from.
    # -----------------------------------------------------

    report_id = str(uuid.uuid4())

    evidence_dict = retrieval_result.get("evidence_dict", {})

    chart_pie_b64 = build_status_pie_chart(evidence_dict)
    chart_bar_b64 = build_effort_bar_chart(evidence_dict)

    chart_urls = {}

    if chart_pie_b64:
        save_chart_png(chart_pie_b64, report_id, "status_pie")
        chart_urls["status_pie"] = f"/reports/{report_id}_status_pie.png"

    if chart_bar_b64:
        save_chart_png(chart_bar_b64, report_id, "effort_bar")
        chart_urls["effort_bar"] = f"/reports/{report_id}_effort_bar.png"

    build_html_report(
        question=user_question,
        answer=filtered_answer,
        chart_pie_b64=chart_pie_b64,
        chart_bar_b64=chart_bar_b64,
        sources=sorted(sources_used),
        report_id=report_id,
    )

    print(
        "[Workflow] Report generated:",
        report_id,
    )


    # -----------------------------------------------------
    # Workflow result
    # -----------------------------------------------------

    return {
        "success": True,
        "answer": filtered_answer,
        "report_id": report_id,
        "report_url": f"/reports/{report_id}.html",
        "chart_urls": chart_urls,

        "workflow": {
            "strategy": "three-source-retrieval",
            "retrieval_agent": {
                "status": retrieval_status,
                "attempts": retrieval_result["attempts"],
            },
            "analyst_agent": {
                "status": "success",
            },
        },
    }