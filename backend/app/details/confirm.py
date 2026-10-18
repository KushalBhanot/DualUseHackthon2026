"""Did the caller actually say the read-back was right? Judged from the transcript, not the agent."""

import re

NO = re.compile(r"\b(no|nope|nah|wrong|incorrect|not quite|not right|that's not|it's not|actually|wait|no it's)\b")
YES = re.compile(r"\b(yes|yeah|yep|yup|ya|correct|right|exactly|perfect|affirmative|sí|si|uh[- ]huh|mm[- ]hmm|that's it|you got it)\b")


def judge_reply(reply: str) -> str | None:
    """'yes' / 'no' / None (unclear). A 'no' or a correction beats a 'yes' ("yes, no wait, it's 43")."""
    t = reply.lower()
    if NO.search(t) or re.search(r"\d", t):
        return "no"
    if YES.search(t):
        return "yes"
    return None
