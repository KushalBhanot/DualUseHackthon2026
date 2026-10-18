-- Night Ledger backend schema: 6 tables. Applied on startup; safe to re-run.

CREATE TABLE IF NOT EXISTS calls (
  call_id              text PRIMARY KEY,
  source               text NOT NULL DEFAULT 'retell',        -- retell | simulated
  scenario             text,
  status               text NOT NULL DEFAULT 'ongoing',       -- ongoing | ended | analyzed
  from_number          text,
  started_at           timestamptz NOT NULL DEFAULT now(),
  ended_at             timestamptz,
  duration_ms          integer,
  disconnection_reason text,

  -- supervisor fields
  lane                 text CHECK (lane IN ('green', 'amber', 'red')),
  red_flags            text[] NOT NULL DEFAULT '{}',
  cluster              text,
  intent               text,
  reason               text,
  urgency              real,
  caller_name          text,
  callback_number      text,
  callback_source      text,                                  -- confirmed | caller_id
  needs_review         boolean NOT NULL DEFAULT false,

  -- classifiers (latest result each) and captured details
  rules_result         jsonb,
  jev_result           jsonb,
  details              jsonb NOT NULL DEFAULT '{}',

  -- red-flag handoff
  red_flag_at          timestamptz,
  transfer_started_at  timestamptz,
  transfer_ended_at    timestamptz,
  transfer_target      text,
  transfer_status      text,                                  -- connected | no_answer | caller_hung_up | never_started

  -- post-call
  summary              text,
  recording_url        text,
  recording            bytea,
  raw                  jsonb
);
CREATE INDEX IF NOT EXISTS calls_started_idx ON calls (started_at DESC);

CREATE TABLE IF NOT EXISTS transcript_items (
  call_id    text NOT NULL REFERENCES calls ON DELETE CASCADE,
  item_id    text NOT NULL,
  role       text NOT NULL,
  content    text,
  time_sec   real,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (call_id, item_id)
);

CREATE TABLE IF NOT EXISTS events (
  id         bigserial PRIMARY KEY,
  call_id    text REFERENCES calls ON DELETE CASCADE,
  actor      text NOT NULL DEFAULT 'system',                  -- system | supervisor
  type       text NOT NULL,
  payload    jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS events_call_idx ON events (call_id, created_at);

CREATE TABLE IF NOT EXISTS suggestions (
  id             bigserial PRIMARY KEY,
  type           text NOT NULL,      -- surge_mode | status_message | staffing_nurses | staffing_doctors | red_not_connected
  call_id        text REFERENCES calls ON DELETE CASCADE,
  evidence       jsonb NOT NULL DEFAULT '{}',
  recommendation jsonb NOT NULL DEFAULT '{}',
  status         text NOT NULL DEFAULT 'open',  -- open | accepted | snoozed | dismissed | resolved | expired
  snooze_until   timestamptz,
  created_at     timestamptz NOT NULL DEFAULT now(),
  decided_at     timestamptz
);
CREATE INDEX IF NOT EXISTS suggestions_status_idx ON suggestions (status, type);

CREATE TABLE IF NOT EXISTS nurse_lines (
  id         bigserial PRIMARY KEY,
  label      text NOT NULL,
  number     text NOT NULL,          -- E.164
  role       text NOT NULL DEFAULT 'nurse',
  on_duty    boolean NOT NULL DEFAULT true,
  priority   integer NOT NULL DEFAULT 1,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS surge_state (
  id                       integer PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  surge_on                 boolean NOT NULL DEFAULT false,
  switched_at              timestamptz,
  status_message           text,
  routine_callback_window  text NOT NULL DEFAULT 'tomorrow morning between 8 and 11',
  priority_callback_window text NOT NULL DEFAULT 'within 30 minutes',
  surge_routine_window     text NOT NULL DEFAULT 'tomorrow between 8 AM and 2 PM',
  surge_priority_window    text NOT NULL DEFAULT 'within 45 minutes'
);
INSERT INTO surge_state (id) VALUES (1) ON CONFLICT DO NOTHING;

-- One-way trigger: the higher of two lanes. Every AI write to calls.lane goes through this,
-- so code can raise a lane but never lower it. Only a supervisor endpoint sets lane directly.
CREATE OR REPLACE FUNCTION lane_max(a text, b text) RETURNS text
LANGUAGE sql IMMUTABLE AS $$
  SELECT CASE
    WHEN coalesce(array_position(ARRAY['green','amber','red'], b), 0)
       > coalesce(array_position(ARRAY['green','amber','red'], a), 0) THEN b
    ELSE a END
$$;
