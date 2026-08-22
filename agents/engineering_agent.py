import os
from dotenv import load_dotenv

load_dotenv()

from agent_framework import Agent
from agent_framework.openai import OpenAIChatClient

from agents.engineering_instructions import (
    ENGINEERING_AGENT_INSTRUCTIONS,
)


def create_engineering_agent(
    middleware=None,
):
    """
    Creates the MAQ Engineering Evidence Agent.
    """

    agent_kwargs = {}

    if middleware:
        agent_kwargs["middleware"] = middleware

    return Agent(
        client=OpenAIChatClient(
            api_key=os.getenv("OPENAI_API_KEY"),
            model=os.getenv("OPENAI_MODEL", "gpt-4o")
        ),
        name="MAQEngineeringEvidenceAgent",
        instructions=ENGINEERING_AGENT_INSTRUCTIONS,
        **agent_kwargs,
    )