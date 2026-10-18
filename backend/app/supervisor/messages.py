"""Status-message templates approved ahead of time. At 2 AM the supervisor approves; nobody writes."""

TEMPLATES = {
    "outage": {
        "title": "Power outage, ER open",
        "text": "We know about the power outage. Harbor General's emergency room is open and running on backup power. "
                "Tomorrow's appointments will be confirmed by text. We can't share patient information by phone.",
    },
    "help": {
        "title": "Thanks, donation link by text",
        "text": "Thank you for offering to help. We'll text you the blood drive and volunteer sign-up link.",
    },
    "fire": {
        "title": "Wildfire smoke, ER entrance",
        "text": "Harbor General is open and is not being evacuated. Use the north ER entrance on 4th Street. "
                "If smoke makes it hard to breathe, tell us right away.",
    },
    "earthquake_minor": {
        "title": "Small quake, all services running",
        "text": "The hospital is not damaged and all services are running. Appointments go ahead as planned.",
    },
    "family": {
        "title": "Family information line",
        "text": "If you're looking for a family member, we'll take their details and a staff member will call you back. "
                "We can't share patient information by phone.",
    },
}

# Which template to suggest when a cluster dominates the line
CLUSTER_TEMPLATE = {"outage": "outage", "help": "help", "family": "family"}
