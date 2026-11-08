import json


def encode_sse(event_name: str, data: dict, event_id: int | None = None) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    prefix = f"id: {event_id}\n" if event_id is not None else ""
    return f"{prefix}event: {event_name}\ndata: {payload}\n\n"
