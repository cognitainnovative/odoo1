"""Normalise Meta Graph API social webhook payloads (Facebook / Instagram)."""
from __future__ import annotations


def normalise_social(raw: dict) -> list[dict]:
    """Return a list of normalised social events from a Graph webhook payload."""
    out = []
    object_type = raw.get("object", "")

    for entry in raw.get("entry", []):
        # Facebook page events
        for change in entry.get("changes", []):
            field = change.get("field", "")
            value = change.get("value", {})

            if field == "feed":
                msg_type = value.get("item", "post")
                out.append({
                    "platform": "facebook",
                    "object_type": object_type,
                    "event_type": field,
                    "msg_type": msg_type,
                    "external_id": value.get("post_id") or value.get("comment_id", ""),
                    "author_id": value.get("from", {}).get("id", ""),
                    "author_name": value.get("from", {}).get("name", ""),
                    "body": value.get("message", ""),
                    "post_id": value.get("post_id", ""),
                    "raw": value,
                })
            elif field == "messages":
                # Instagram / Messenger DMs
                for msg in value.get("messages", []):
                    out.append({
                        "platform": "instagram" if object_type == "instagram" else "messenger",
                        "object_type": object_type,
                        "event_type": "message",
                        "msg_type": "dm",
                        "external_id": msg.get("mid", ""),
                        "author_id": msg.get("from", {}).get("id", ""),
                        "author_name": msg.get("from", {}).get("name", ""),
                        "body": msg.get("text", ""),
                        "raw": msg,
                    })

        # Instagram mentions / story_mentions
        for mention in entry.get("messaging", []):
            out.append({
                "platform": "instagram",
                "object_type": object_type,
                "event_type": "messaging",
                "msg_type": mention.get("type", "message"),
                "external_id": mention.get("message", {}).get("mid", ""),
                "author_id": mention.get("sender", {}).get("id", ""),
                "author_name": "",
                "body": mention.get("message", {}).get("text", ""),
                "raw": mention,
            })

    return out
