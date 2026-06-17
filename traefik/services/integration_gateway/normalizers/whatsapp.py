"""Normalise Meta WhatsApp Cloud API webhook payloads.

Meta sends a nested object; we flatten it to what Odoo's
whatsapp.message.process_inbound_webhook() expects.
"""
from __future__ import annotations


def normalise_whatsapp(raw: dict) -> list[dict]:
    """Return a list of normalised message dicts (one per message in the payload)."""
    out = []
    for entry in raw.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            messages = value.get("messages", [])
            contacts = {c["wa_id"]: c for c in value.get("contacts", [])}
            for msg in messages:
                wa_id = msg.get("from", "")
                contact = contacts.get(wa_id, {})
                profile_name = contact.get("profile", {}).get("name", "")

                body = ""
                msg_type = msg.get("type", "text")
                if msg_type == "text":
                    body = msg.get("text", {}).get("body", "")
                elif msg_type in ("image", "video", "audio", "document", "sticker"):
                    media = msg.get(msg_type, {})
                    body = f"[{msg_type}] {media.get('caption', '') or media.get('filename', '')}"
                elif msg_type == "location":
                    loc = msg.get("location", {})
                    body = f"[location] lat={loc.get('latitude')} lng={loc.get('longitude')}"
                elif msg_type == "button":
                    body = msg.get("button", {}).get("text", "")
                elif msg_type == "interactive":
                    reply = msg.get("interactive", {})
                    body = (
                        reply.get("button_reply", {}).get("title")
                        or reply.get("list_reply", {}).get("title", "")
                    )

                out.append({
                    "external_id": msg.get("id", ""),
                    "from_number": wa_id,
                    "profile_name": profile_name,
                    "body": body,
                    "msg_type": msg_type,
                    "timestamp": msg.get("timestamp", ""),
                    "phone_number_id": value.get("metadata", {}).get("phone_number_id", ""),
                    "raw": msg,
                })
    return out
