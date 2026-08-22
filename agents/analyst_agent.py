import os
from dotenv import load_dotenv

load_dotenv()

from agent_framework import Agent
from agent_framework.openai import OpenAIChatClient

from agents.analyst_instructions import (
    ANALYST_AGENT_INSTRUCTIONS,
)


def create_analyst_agent(
    middleware=None,
):
    """
    Creates the MAQ Delivery Analyst Agent (Insight Orchestrator).

    This agent should not receive live data-source tools (Azure
    DevOps, SharePoint, Timesheets) - it only analyzes validated
    evidence passed by the workflow. It does receive its own
    Hybrid RAG tool at .run() time (see analyst_tools.py), for
    guidance/interpretation content, not live facts.
    """

    agent_kwargs = {}

    if middleware:
        agent_kwargs["middleware"] = middleware

    return Agent(
        client=OpenAIChatClient(
            api_key=os.getenv("OPENAI_API_KEY"),
            model=os.getenv("OPENAI_MODEL", "gpt-4o")
        ),
        name="MAQDeliveryAnalystAgent",
        instructions=ANALYST_AGENT_INSTRUCTIONS,
        **agent_kwargs,
    )