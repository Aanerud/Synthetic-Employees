"""Agency CLI subprocess wrapper.

Invokes `agency copilot` or `agency claude` as a subprocess for each
synthetic employee, passing persona context via --input variables and
M365 access via --mcp workiq.
"""

import asyncio
import json
import logging
import os
import platform
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgencyResult:
    """Result from an Agency CLI invocation."""

    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    actions_taken: List[Dict[str, Any]] = field(default_factory=list)
    emails_sent: int = 0
    teams_messages_sent: int = 0
    calendar_actions: int = 0
    items_flagged_for_later: List[Dict[str, Any]] = field(default_factory=list)
    memory_updates: List[Dict[str, Any]] = field(default_factory=list)
    parsed_ok: bool = False
    error: Optional[str] = None


def _parse_json_summary(stdout: str) -> Optional[Dict[str, Any]]:
    """Extract JSON summary block from Agency stdout.

    Agency output may contain reasoning text followed by a JSON block.
    We look for the last JSON object in the output.
    """
    # Try to find JSON block between ```json and ```
    import re

    json_block = re.findall(r"```json\s*(\{.*?\})\s*```", stdout, re.DOTALL)
    if json_block:
        try:
            return json.loads(json_block[-1])
        except json.JSONDecodeError:
            pass

    # Try to find standalone JSON object (last one in output)
    brace_depth = 0
    last_json_start = -1
    for i, ch in enumerate(stdout):
        if ch == "{":
            if brace_depth == 0:
                last_json_start = i
            brace_depth += 1
        elif ch == "}":
            brace_depth -= 1
            if brace_depth == 0 and last_json_start >= 0:
                candidate = stdout[last_json_start : i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    last_json_start = -1

    return None


class AgencyCliRunner:
    """Spawns Agency CLI processes for each synthetic employee."""

    def __init__(
        self,
        binary_path: str = "agency",
        default_backend: str = "copilot",
        premium_backend: str = "claude",
        premium_roles: Optional[List[str]] = None,
        default_timeout: int = 120,
        role_timeouts: Optional[Dict[str, int]] = None,
        mcp_servers: Optional[List[str]] = None,
        agent_directory: str = ".github/agents",
    ):
        self.binary_path = binary_path
        self.default_backend = default_backend
        self.premium_backend = premium_backend
        self.premium_roles = premium_roles or []
        self.default_timeout = default_timeout
        self.role_timeouts = role_timeouts or {}
        self.mcp_servers = mcp_servers or []
        self.agent_directory = agent_directory

    def _get_backend(self, role: str, is_external: bool = False) -> str:
        """Determine which backend to use based on role and context."""
        if is_external and role in self.premium_roles:
            return self.premium_backend
        return self.default_backend

    def _get_timeout(self, role: str) -> int:
        """Get timeout for a specific role."""
        return self.role_timeouts.get(role, self.default_timeout)

    def _get_agent_template(self, role: str) -> str:
        """Map a role to an agent template name."""
        role_lower = role.lower()

        # KAM must be checked before executives (since "account" contains "cco")
        if "key account" in role_lower:
            return "employee-kam"
        if any(
            title in role_lower
            for title in ["ceo", "coo", "cfo", "cco", "chief"]
        ):
            return "employee-executive"
        if "editorial director" in role_lower:
            return "employee-editorial-director"
        if any(word in role_lower for word in ["editor", "copy chief"]):
            return "employee-editor"
        if "writer" in role_lower:
            return "employee-writer"
        if "proofreader" in role_lower:
            return "employee-proofreader"
        if any(
            word in role_lower
            for word in ["developer", "engineer", "devops", "qa"]
        ):
            return "employee-developer"
        return "employee-default"

    def _build_command(
        self,
        backend: str,
        agent_name: str,
        prompt: str,
        input_vars: Dict[str, str],
        mcp_servers: Optional[List[str]] = None,
    ) -> List[str]:
        """Build the CLI command for subprocess execution."""
        cmd = [self.binary_path, backend]

        # Agent template
        cmd.extend(["--agent", agent_name])

        # MCP servers
        for mcp in mcp_servers or self.mcp_servers:
            cmd.extend(["--mcp", mcp])

        # Input variables
        for key, value in input_vars.items():
            cmd.extend(["--input", f"{key}={value}"])

        # Prompt and output mode
        cmd.extend(["--prompt", prompt])

        # On Windows, try agency.EXE if agency is not found
        if platform.system() == "Windows":
            import shutil
            binary = cmd[0]
            if not shutil.which(binary):
                for variant in [binary + ".EXE", binary + ".exe", binary + ".cmd"]:
                    if shutil.which(variant):
                        cmd[0] = variant
                        break

        return cmd

    async def execute(
        self,
        agent_email: str,
        role: str,
        prompt: str,
        input_vars: Dict[str, str],
        mcp_bearer_token: Optional[str] = None,
        mcp_servers: Optional[List[str]] = None,
        is_external: bool = False,
        timeout_override: Optional[int] = None,
    ) -> AgencyResult:
        """Execute an Agency CLI task for one employee.

        Args:
            agent_email: Employee's email address (for logging).
            role: Employee's role (determines template and backend).
            prompt: The task prompt to send.
            input_vars: Handlebars variables for the agent template.
            mcp_bearer_token: Per-employee MCP auth token.
            mcp_servers: Override MCP servers for this call.
            is_external: Whether this involves external communication.
            timeout_override: Override the default timeout.

        Returns:
            AgencyResult with parsed output and metrics.
        """
        backend = self._get_backend(role, is_external)
        agent_name = self._get_agent_template(role)
        timeout = timeout_override or self._get_timeout(role)

        cmd = self._build_command(
            backend=backend,
            agent_name=agent_name,
            prompt=prompt,
            input_vars=input_vars,
            mcp_servers=mcp_servers,
        )

        # Per-employee environment with MCP auth
        env = dict(os.environ)
        if mcp_bearer_token:
            env["WORKIQ_TOKEN"] = mcp_bearer_token
            env["MCP_BEARER_TOKEN"] = mcp_bearer_token

        logger.info(
            "Executing agency %s for %s (agent=%s, timeout=%ds)",
            backend,
            agent_email,
            agent_name,
            timeout,
        )

        start_time = time.monotonic()

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )

            duration = time.monotonic() - start_time
            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")
            exit_code = proc.returncode or 0

        except asyncio.TimeoutError:
            duration = time.monotonic() - start_time
            # Kill the process
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass

            logger.warning(
                "Agency process timed out for %s after %.1fs",
                agent_email,
                duration,
            )
            return AgencyResult(
                exit_code=-1,
                stdout="",
                stderr="Process timed out",
                duration_seconds=duration,
                error=f"Timed out after {timeout}s",
            )

        except FileNotFoundError:
            duration = time.monotonic() - start_time
            logger.error(
                "Agency binary not found at '%s'", self.binary_path
            )
            return AgencyResult(
                exit_code=-2,
                stdout="",
                stderr=f"Binary not found: {self.binary_path}",
                duration_seconds=duration,
                error=f"Agency binary not found: {self.binary_path}",
            )

        except Exception as exc:
            duration = time.monotonic() - start_time
            logger.error(
                "Agency process failed for %s: %s", agent_email, exc
            )
            return AgencyResult(
                exit_code=-3,
                stdout="",
                stderr=str(exc),
                duration_seconds=duration,
                error=str(exc),
            )

        # Parse result
        result = AgencyResult(
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=duration,
        )

        if exit_code != 0:
            result.error = f"Exit code {exit_code}: {stderr[:500]}"
            logger.warning(
                "Agency returned exit code %d for %s: %s",
                exit_code,
                agent_email,
                stderr[:200],
            )
        else:
            # Parse JSON summary from output
            summary = _parse_json_summary(stdout)
            if summary:
                result.parsed_ok = True
                # Support both old format (actions_taken) and new format (actions)
                actions = summary.get("actions", summary.get("actions_taken", []))
                result.actions_taken = actions
                # Count action types from the actions list
                result.emails_sent = sum(
                    1 for a in actions
                    if a.get("type") in ("send_email", "reply_email")
                )
                result.teams_messages_sent = summary.get(
                    "teams_messages_sent", 0
                )
                result.calendar_actions = sum(
                    1 for a in actions
                    if a.get("type") in (
                        "accept_meeting", "decline_meeting",
                        "tentative_meeting", "create_meeting",
                    )
                )
                result.items_flagged_for_later = summary.get(
                    "items_flagged_for_later", []
                )
                result.memory_updates = summary.get("memory_updates", [])
            else:
                logger.warning(
                    "Could not parse JSON summary from Agency output for %s",
                    agent_email,
                )

        logger.info(
            "Agency completed for %s in %.1fs (exit=%d, emails=%d, teams=%d)",
            agent_email,
            duration,
            exit_code,
            result.emails_sent,
            result.teams_messages_sent,
        )

        return result
