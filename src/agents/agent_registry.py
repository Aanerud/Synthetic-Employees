"""Agent registry for loading and managing agents."""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from .roles import Role, get_role


@dataclass
class AgentConfig:
    """Configuration for a single agent."""

    name: str
    email: str
    role: str
    department: str
    user_id: str
    password: Optional[str] = None
    mcp_bearer_token: Optional[str] = None
    created_at: Optional[str] = None
    metadata: Optional[Dict] = None


class AgentRegistry:
    """Load and manage agent configurations."""

    def __init__(self, config_path: str = "config/agents.json"):
        self.config_path = Path(config_path)
        self.agents: List[AgentConfig] = []
        self.agents_by_email: Dict[str, AgentConfig] = {}
        self.agents_by_role: Dict[str, List[AgentConfig]] = {}
        self.agents_by_department: Dict[str, List[AgentConfig]] = {}

    def load_agents(self) -> List[AgentConfig]:
        """Load agents from configuration file."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Agent configuration not found: {self.config_path}")

        with open(self.config_path, "r") as f:
            config = json.load(f)

        agents_data = config.get("agents", [])
        self.agents = []

        for agent_data in agents_data:
            agent = AgentConfig(
                name=agent_data["name"],
                email=agent_data["email"],
                role=agent_data["role"],
                department=agent_data["department"],
                user_id=agent_data.get("userId", ""),
                password=agent_data.get("password"),
                mcp_bearer_token=agent_data.get("mcpBearerToken"),
                created_at=agent_data.get("createdAt"),
                metadata=agent_data.get("metadata"),
            )
            self.agents.append(agent)

            # Index by email
            self.agents_by_email[agent.email] = agent

            # Index by role
            if agent.role not in self.agents_by_role:
                self.agents_by_role[agent.role] = []
            self.agents_by_role[agent.role].append(agent)

            # Index by department
            if agent.department not in self.agents_by_department:
                self.agents_by_department[agent.department] = []
            self.agents_by_department[agent.department].append(agent)

        print(f"✓ Loaded {len(self.agents)} agents from {self.config_path}")
        return self.agents

    def get_agent_by_email(self, email: str) -> Optional[AgentConfig]:
        """Get agent by email address."""
        return self.agents_by_email.get(email)

    def get_agents_by_role(self, role: str) -> List[AgentConfig]:
        """Get all agents with a specific role."""
        return self.agents_by_role.get(role, [])

    def get_agents_by_department(self, department: str) -> List[AgentConfig]:
        """Get all agents in a department."""
        return self.agents_by_department.get(department, [])

    def get_role_for_agent(self, agent: AgentConfig) -> Role:
        """Get role definition for an agent."""
        return get_role(agent.role)

    def list_agents(self) -> None:
        """Print list of all agents grouped by department."""
        print(f"\n✓ Loaded {len(self.agents)} agents from {self.config_path}\n")

        for department, agents in sorted(self.agents_by_department.items()):
            print(f"{department}:")
            for agent in agents:
                print(f"  - {agent.name} ({agent.role}) - {agent.email}")
            print()

    def get_agent_stats(self) -> Dict[str, int]:
        """Get statistics about loaded agents."""
        return {
            "total_agents": len(self.agents),
            "departments": len(self.agents_by_department),
            "roles": len(self.agents_by_role),
            "by_department": {
                dept: len(agents) for dept, agents in self.agents_by_department.items()
            },
            "by_role": {role: len(agents) for role, agents in self.agents_by_role.items()},
        }

    def validate_tokens(self) -> Dict[str, bool]:
        """Check if all agents have valid bearer tokens."""
        validation = {}
        for agent in self.agents:
            has_token = bool(agent.mcp_bearer_token and len(agent.mcp_bearer_token) > 0)
            validation[agent.email] = has_token
            if not has_token:
                print(f"⚠ Warning: Agent {agent.email} has no bearer token")
        return validation

    def filter_agents(
        self,
        emails: Optional[List[str]] = None,
        roles: Optional[List[str]] = None,
        departments: Optional[List[str]] = None,
    ) -> List[AgentConfig]:
        """Filter agents by email, role, or department."""
        filtered = self.agents

        if emails:
            filtered = [a for a in filtered if a.email in emails]

        if roles:
            filtered = [a for a in filtered if a.role in roles]

        if departments:
            filtered = [a for a in filtered if a.department in departments]

        return filtered
