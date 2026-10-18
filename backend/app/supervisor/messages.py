"""Status messages approved ahead of time. The AI suggests one; it never writes new wording.

Each is one sentence, spoken in the greeting right after the AI disclosure.
"""

TEMPLATES = [
    {"id": "power_outage", "event": "outage", "cluster": "outage",
     "text": "Harbor General's emergency room is open and running on backup power."},
    {"id": "it_outage", "event": "it_outage", "cluster": "outage",
     "text": "Our patient portal and some phone lines are down, but the emergency room is open."},
    {"id": "earthquake", "event": "earthquake", "cluster": "outage",
     "text": "Harbor General is open after the earthquake and the emergency room is running."},
    {"id": "family_info", "event": "any", "cluster": "family",
     "text": "We can't share patient information by phone, but stay on the line and we'll arrange a staff callback."},
    {"id": "offers_of_help", "event": "any", "cluster": "help",
     "text": "Thank you for offering to help; please don't come in, and stay on the line for a sign-up link."},
    {"id": "fire", "event": "fire", "cluster": "outage",
     "text": "Harbor General is open and not affected by the fire, and the emergency room is running."},
]


def for_cluster(cluster: str) -> dict | None:
    return next((t for t in TEMPLATES if t["cluster"] == cluster), None)
