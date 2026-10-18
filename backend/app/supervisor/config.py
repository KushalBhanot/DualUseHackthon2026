"""Supervisor thresholds. Agree on these with nursing leadership on a calm day."""

TICK_SECONDS = 15

# Surge prompt
BASELINE_CALLS_PER_HOUR = 20      # a normal night
SURGE_MULTIPLIER = 5              # prompt at 5x the normal rate...
SURGE_WINDOW_MIN = 3              # ...over the last 3 minutes
SURGE_MIN_CALLS = 5               # and never for fewer calls than this
SNOOZE_MIN = 2                    # "Not yet, ask in 2 min"
HUNG_UP_EARLY_MS = 30_000         # callers who hung up within 30 s

# Status message suggestion
MESSAGE_WINDOW_MIN = 10
MESSAGE_CLUSTER_SHARE = 0.3       # one topic is 30%+ of calls (callers spread over ~9 topics in a surge)
MESSAGE_MIN_CALLS = 5

# Staffing
STAFFING_WINDOW_MIN = 30
RED_MIN = 10                      # nurse minutes per red call
AMBER_MIN = 8                     # nurse minutes per amber callback
UTILIZATION = 0.8
NURSES_ON_PHONES = 1
AMBER_TARGET_MIN = 15             # amber callback target
AMBER_LOOKBACK_MIN = 60           # v1 has no "callback done" yet, so only recent amber calls count as waiting
RED_NO_ANSWER_WINDOW_MIN = 10
RED_NO_ANSWER_TRIGGER = 2
DOCTOR_TIERS = [(15, "3+"), (6, "1-2")]  # red-flag calls per hour -> suggested ER doctors
