#!/usr/bin/env python3
"""
Simple end-to-end test: Two agents exchange emails via MCP server.

Uses stdio transport (same as Claude Desktop) for 1:1 parity.

Flow:
1. Victoria sends an email to François
2. François checks inbox, finds the email
3. François replies to Victoria
4. Victoria checks inbox, finds the reply
"""

import time
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from src.auth.mcp_token_manager import MCPTokenManager

# Test participants
VICTORIA = "victoria.palmer@a830edad9050849coep9vqp9bog.onmicrosoft.com"
FRANCOIS = "francois.moreau@a830edad9050849coep9vqp9bog.onmicrosoft.com"


def main():
    print("=" * 60)
    print("Email Exchange Test: Victoria <-> François")
    print("(Using stdio transport - same as Claude Desktop)")
    print("=" * 60)
    print()

    # Initialize token manager
    token_manager = MCPTokenManager()

    # Step 1: Get stdio clients for both users (spawns mcp-adapter.cjs)
    print("[1/6] Creating stdio MCP clients...")

    try:
        victoria_client = token_manager.get_stdio_client(VICTORIA)
        print(f"  ✓ Victoria: MCP client ready (stdio transport)")
    except Exception as e:
        print(f"  ✗ Victoria: failed - {e}")
        return False

    try:
        francois_client = token_manager.get_stdio_client(FRANCOIS)
        print(f"  ✓ François: MCP client ready (stdio transport)")
    except Exception as e:
        print(f"  ✗ François: failed - {e}")
        victoria_client.close()
        return False

    print()

    # Step 2: Victoria sends email to François
    print("[2/6] Victoria sending email to François...")

    subject = f"Test Email - {datetime.now().strftime('%H:%M:%S')}"
    body = """Hi François,

This is a test email from the Synthetic Employees system.

Could you please confirm you received this message?

Best regards,
Victoria Palmer
Editorial Director"""

    try:
        result = victoria_client.send_mail(
            to=FRANCOIS,
            subject=subject,
            body=body
        )
        print(f"  ✓ Email sent: '{subject}'")
    except Exception as e:
        print(f"  ✗ Failed to send email: {e}")
        victoria_client.close()
        francois_client.close()
        return False

    print()

    # Step 3: Wait a moment for email to be delivered
    print("[3/6] Waiting for email delivery (5 seconds)...")
    time.sleep(5)
    print("  ✓ Done waiting")
    print()

    # Step 4: François checks inbox
    print("[4/6] François checking inbox...")

    try:
        inbox = francois_client.get_inbox(limit=10)

        # Find Victoria's email
        victoria_email = None
        for email in inbox:
            email_subject = email.get("subject", "")
            # Handle both normalized (from.email) and raw (from.emailAddress.address) formats
            from_data = email.get("from", {})
            sender = from_data.get("email") or from_data.get("emailAddress", {}).get("address", "")
            if subject in email_subject or VICTORIA.lower() in sender.lower():
                victoria_email = email
                break

        if victoria_email:
            print(f"  ✓ Found email from Victoria!")
            print(f"    Subject: {victoria_email.get('subject')}")
            from_data = victoria_email.get('from', {})
            sender_email = from_data.get('email') or from_data.get('emailAddress', {}).get('address', 'unknown')
            print(f"    From: {sender_email}")
            print(f"    Preview: {victoria_email.get('bodyPreview', victoria_email.get('preview', ''))[:100]}...")
        else:
            print(f"  ⚠ Email not found in inbox yet (found {len(inbox)} emails)")
            print("    Recent emails:")
            for email in inbox[:5]:
                print(f"    - {email.get('subject', '(no subject)')}")
            # Continue anyway - email might still arrive

    except Exception as e:
        print(f"  ✗ Failed to check inbox: {e}")
        victoria_client.close()
        francois_client.close()
        return False

    print()

    # Step 5: François replies (if we found the email)
    print("[5/6] François replying to Victoria...")

    if victoria_email:
        reply_body = """Hi Victoria,

Yes, I received your test message loud and clear!

The Synthetic Employees system is working perfectly.

Best regards,
François Moreau
Senior Editor - Literary"""

        try:
            message_id = victoria_email.get("id")
            result = francois_client.reply_to_mail(message_id, reply_body)
            print(f"  ✓ Reply sent!")
        except Exception as e:
            print(f"  ✗ Failed to reply: {e}")
            # Try sending a new email instead
            print("  → Trying to send a new email instead...")
            try:
                francois_client.send_mail(
                    to=VICTORIA,
                    subject=f"Re: {subject}",
                    body=reply_body
                )
                print(f"  ✓ New email sent as reply")
            except Exception as e2:
                print(f"  ✗ Failed to send email: {e2}")
    else:
        # Send a new email since we couldn't find the original
        print("  → Sending new email since original not found...")
        try:
            francois_client.send_mail(
                to=VICTORIA,
                subject=f"Response to your test",
                body="Hi Victoria, I'm responding to your test. The system works!"
            )
            print(f"  ✓ Email sent!")
        except Exception as e:
            print(f"  ✗ Failed: {e}")

    print()

    # Step 6: Victoria checks for reply
    print("[6/6] Victoria checking for reply (waiting 5 seconds)...")
    time.sleep(5)

    try:
        inbox = victoria_client.get_inbox(limit=10)

        # Find François's reply
        francois_reply = None
        for email in inbox:
            from_data = email.get("from", {})
            sender = from_data.get("email") or from_data.get("emailAddress", {}).get("address", "")
            if FRANCOIS.lower() in sender.lower():
                francois_reply = email
                break

        if francois_reply:
            print(f"  ✓ Found reply from François!")
            print(f"    Subject: {francois_reply.get('subject')}")
            print(f"    Preview: {francois_reply.get('bodyPreview', francois_reply.get('preview', ''))[:100]}...")
        else:
            print(f"  ⚠ Reply not found yet (may take a moment to arrive)")

    except Exception as e:
        print(f"  ✗ Failed to check inbox: {e}")

    print()
    print("=" * 60)
    print("Test Complete!")
    print("=" * 60)

    # Clean up stdio clients
    victoria_client.close()
    francois_client.close()

    return True


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
