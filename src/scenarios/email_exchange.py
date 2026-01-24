"""Email exchange scenario between two synthetic employees using MSAL authentication."""

import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from src.agents.agent_registry import AgentConfig, AgentRegistry
from src.auth.token_manager import TokenManager
from src.graph_client.client import GraphClient, GraphClientError


@dataclass
class ScenarioResult:
    """Result of running a scenario."""

    success: bool
    steps_completed: int
    total_steps: int
    error: Optional[str] = None
    details: Optional[dict] = None


class EmailExchangeScenario:
    """
    Two-person email exchange scenario using MSAL authentication.

    Flow:
    1. Victoria sends email to François about style guide review
    2. François checks inbox, finds Victoria's email
    3. François replies with literary insights
    4. Victoria reads the reply
    """

    def __init__(self, agent_registry: AgentRegistry):
        self.agent_registry = agent_registry
        self.token_manager = TokenManager()
        self.victoria: Optional[AgentConfig] = None
        self.francois: Optional[AgentConfig] = None
        self.victoria_client: Optional[GraphClient] = None
        self.francois_client: Optional[GraphClient] = None

    def setup(self) -> bool:
        """Load agents and authenticate with MSAL."""
        print("\n" + "=" * 60)
        print("Email Exchange Scenario Setup")
        print("=" * 60)

        # Find Victoria
        self.victoria = self.agent_registry.get_agent_by_email(
            "victoria.palmer@a830edad9050849coep9vqp9bog.onmicrosoft.com"
        )
        if not self.victoria:
            print("Error: Victoria Palmer not found in agents.json")
            return False
        print(f"Found: {self.victoria.name} ({self.victoria.role})")

        # Find François
        self.francois = self.agent_registry.get_agent_by_email(
            "francois.moreau@a830edad9050849coep9vqp9bog.onmicrosoft.com"
        )
        if not self.francois:
            print("Error: François Moreau not found in agents.json")
            return False
        print(f"Found: {self.francois.name} ({self.francois.role})")

        # Get passwords (from agent config or env default)
        default_password = os.getenv("DEFAULT_PASSWORD")
        victoria_password = self.victoria.password or default_password
        francois_password = self.francois.password or default_password

        if not victoria_password or not francois_password:
            print("Error: No password configured. Set DEFAULT_PASSWORD in .env or password in agents.json")
            return False

        # Authenticate with MSAL
        print("\nAuthenticating with Microsoft Graph API...")

        try:
            print(f"  Authenticating {self.victoria.name}...")
            victoria_token = self.token_manager.authenticate(
                username=self.victoria.email,
                password=victoria_password,
            )
            self.victoria_client = GraphClient(victoria_token)
            result = self.victoria_client.test_connection()
            if result["status"] != "success":
                print(f"    Error: {result.get('error')}")
                return False
            print(f"    Connected as: {result.get('email')}")

            print(f"  Authenticating {self.francois.name}...")
            francois_token = self.token_manager.authenticate(
                username=self.francois.email,
                password=francois_password,
            )
            self.francois_client = GraphClient(francois_token)
            result = self.francois_client.test_connection()
            if result["status"] != "success":
                print(f"    Error: {result.get('error')}")
                return False
            print(f"    Connected as: {result.get('email')}")

        except ValueError as e:
            print(f"  Authentication failed: {e}")
            return False

        print("\nSetup complete!")
        return True

    def run(self, delay_seconds: int = 2) -> ScenarioResult:
        """Execute the email exchange scenario."""
        if not self.victoria_client or not self.francois_client:
            return ScenarioResult(
                success=False,
                steps_completed=0,
                total_steps=4,
                error="Scenario not set up. Call setup() first.",
            )

        print("\n" + "=" * 60)
        print("Running Email Exchange Scenario")
        print("=" * 60)

        steps_completed = 0
        total_steps = 4
        details = {}

        try:
            # Step 1: Victoria sends email to François
            print(f"\n[Step 1/4] Victoria sends email to François...")
            subject = "Quarterly Style Guide Review"
            body = """Dear François,

I hope this message finds you well. As we approach the end of the quarter, I'd like to request your expert review of our recent fiction submissions with particular attention to style consistency.

Your keen eye for narrative craft and the musicality of language would be invaluable in assessing whether our current submissions align with the TextCraft style guidelines, particularly in the areas of:

1. Narrative voice consistency
2. Dialogue authenticity
3. Prose rhythm and flow
4. Adherence to our house style for literary fiction

Please provide your assessment by end of week. I'm especially interested in any submissions you believe show exceptional promise.

Best regards,
Victoria Palmer
Editorial Director, TextCraft Europe"""

            self.victoria_client.send_mail(
                to=self.francois.email, subject=subject, body=body
            )
            details["email_sent"] = {
                "from": self.victoria.email,
                "to": self.francois.email,
                "subject": subject,
                "timestamp": datetime.now().isoformat(),
            }
            print(f"    Sent: '{subject}'")
            steps_completed += 1
            time.sleep(delay_seconds)

            # Step 2: François checks inbox and finds Victoria's email
            print(f"\n[Step 2/4] François checks inbox...")
            inbox = self.francois_client.get_inbox(limit=10)
            victoria_email = None

            for email in inbox:
                sender = email.get("from", {}).get("emailAddress", {}).get("address", "")
                if "victoria.palmer" in sender.lower():
                    victoria_email = email
                    break

            if not victoria_email:
                print("    Warning: Could not find Victoria's email in inbox (may have delivery delay)")
                details["email_found"] = False
            else:
                details["email_found"] = True
                details["email_id"] = victoria_email.get("id")
                print(f"    Found email: '{victoria_email.get('subject', 'Unknown')}'")
            steps_completed += 1
            time.sleep(delay_seconds)

            # Step 3: François replies with literary insights
            print(f"\n[Step 3/4] François replies with literary insights...")
            reply_body = """Dear Victoria,

Thank you for entrusting me with this important review. I have carefully examined the recent fiction submissions through the lens of our style guidelines, and I am pleased to share my observations.

**Narrative Voice Consistency:**
The majority of submissions demonstrate solid command of narrative perspective. I noted three manuscripts with particularly compelling voices that maintain integrity throughout - I shall flag these for your attention.

**Dialogue Authenticity:**
This remains our strongest area. Writers are capturing the cadence of natural speech while avoiding the trap of mere transcription. The balance between realism and artistry is well-maintained.

**Prose Rhythm and Flow:**
Here I found the most variance. Several submissions would benefit from more attention to sentence-level musicality. I recommend we consider a supplementary workshop on this topic for our regular contributors.

**House Style Adherence:**
Generally excellent, though I've noted a tendency toward American spellings creeping into work intended for our European editions. A gentle reminder in our next author newsletter might be prudent.

Three submissions stand out as exceptional: "The Lighthouse Keeper's Daughter," "Autumn in Montmartre," and the poetry collection "Tides." I recommend we prioritize these for our next editorial meeting.

With warm regards,
François Moreau
Senior Editor - Literary"""

            if victoria_email and victoria_email.get("id"):
                # Use reply if we have the email ID
                self.francois_client.reply_to_mail(
                    message_id=victoria_email["id"], body=reply_body
                )
            else:
                # Fall back to sending a new email
                self.francois_client.send_mail(
                    to=self.victoria.email,
                    subject=f"Re: {subject}",
                    body=reply_body,
                )

            details["reply_sent"] = {
                "from": self.francois.email,
                "to": self.victoria.email,
                "timestamp": datetime.now().isoformat(),
            }
            print(f"    Sent reply to Victoria")
            steps_completed += 1
            time.sleep(delay_seconds)

            # Step 4: Victoria reads the reply
            print(f"\n[Step 4/4] Victoria checks inbox for reply...")
            victoria_inbox = self.victoria_client.get_inbox(limit=10)
            francois_reply = None

            for email in victoria_inbox:
                sender = email.get("from", {}).get("emailAddress", {}).get("address", "")
                if "francois.moreau" in sender.lower():
                    francois_reply = email
                    break

            if not francois_reply:
                print("    Warning: Reply not yet visible in inbox (may have delivery delay)")
                details["reply_received"] = False
            else:
                details["reply_received"] = True
                print(f"    Found reply: '{francois_reply.get('subject', 'Unknown')}'")
            steps_completed += 1

            # Summary
            print("\n" + "=" * 60)
            print("Scenario Complete!")
            print("=" * 60)
            print(f"Steps completed: {steps_completed}/{total_steps}")
            print(f"Email sent: Victoria -> François")
            print(f"Reply sent: François -> Victoria")
            print("\nCheck M365 mailboxes to verify emails arrived.")

            return ScenarioResult(
                success=True,
                steps_completed=steps_completed,
                total_steps=total_steps,
                details=details,
            )

        except GraphClientError as e:
            print(f"\n    Graph API Error: {str(e)}")
            return ScenarioResult(
                success=False,
                steps_completed=steps_completed,
                total_steps=total_steps,
                error=str(e),
                details=details,
            )
        except Exception as e:
            print(f"\n    Unexpected error: {str(e)}")
            return ScenarioResult(
                success=False,
                steps_completed=steps_completed,
                total_steps=total_steps,
                error=str(e),
                details=details,
            )


def run_email_exchange(agent_registry: AgentRegistry) -> ScenarioResult:
    """Convenience function to run the email exchange scenario."""
    scenario = EmailExchangeScenario(agent_registry)

    if not scenario.setup():
        return ScenarioResult(
            success=False,
            steps_completed=0,
            total_steps=4,
            error="Setup failed",
        )

    return scenario.run()
