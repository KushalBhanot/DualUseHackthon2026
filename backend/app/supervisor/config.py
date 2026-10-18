"""Thresholds agreed with nursing leadership on a calm day. One file, so they're easy to review."""

BASELINE_CALLS_PER_HOUR = 20      # normal overnight volume
SURGE_MULTIPLIER = 5              # prompt surge mode at 5x normal
SURGE_WINDOW_MIN = 3
SURGE_MIN_CALLS = 5
SNOOZE_MIN = 2                    # "Not yet, ask in 2 min"

STATUS_CLUSTER_SHARE = 0.40       # suggest a status message when one cluster is 40% of recent calls
STATUS_WINDOW_MIN = 10
STATUS_MIN_CALLS = 5

STAFF_WINDOW_MIN = 30
RED_MIN = 10                      # nurse minutes per red call
AMBER_MIN = 8                     # nurse minutes per amber callback
NURSE_UTILIZATION = 0.8
NURSES_ON_PHONES = 2
AMBER_TARGET_MIN = 15             # oldest amber caller should be called back within 15 min
DOCTOR_TIERS = [(15, "3+"), (6, "1-2")]  # red injury/illness calls per hour -> ER doctors to consider

RED_TRANSFER_TARGET_S = 10
