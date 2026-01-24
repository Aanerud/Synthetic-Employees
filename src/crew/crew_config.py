"""CrewAI configuration for synthetic employees."""

from crewai import Agent, Task
from src.agents.agent_registry import AgentConfig
from src.agents.roles import get_role
from src.mcp_client.client import MCPClient, MCPTool


def create_crew_agent(agent_config: AgentConfig, mcp_client: MCPClient) -> Agent:
    """Create a CrewAI agent from agent configuration."""
    role = get_role(agent_config.role)

    # Create MCP tool wrapper for CrewAI
    mcp_tool = MCPTool(mcp_client)

    # Create CrewAI agent
    crew_agent = Agent(
        role=role.name,
        goal=f"Effectively perform {role.name} responsibilities",
        backstory=f"""You are {agent_config.name}, a {role.name} at the company.
        Your communication style is {role.communication_style}.
        You are responsible for: {', '.join(role.responsibilities[:3])}.
        """,
        verbose=False,
        allow_delegation=False,
    )

    return crew_agent


def create_email_check_task(agent: Agent, description: str = "Check and respond to emails") -> Task:
    """Create a task for checking emails."""
    return Task(
        description=description,
        agent=agent,
        expected_output="Summary of emails processed and actions taken",
    )


def create_calendar_check_task(agent: Agent, description: str = "Review calendar and respond to meeting invites") -> Task:
    """Create a task for checking calendar."""
    return Task(
        description=description,
        agent=agent,
        expected_output="Summary of calendar events and responses",
    )
