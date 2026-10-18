// Shapes returned by the FastAPI backend (backend/app/api.py, supervisor/routes.py, sim.py).
// Timestamps are ISO strings.

export type Lane = "red" | "amber" | "green";
export type TransferStatus = "connected" | "no_answer" | "caller_hung_up" | "never_started";

/** One row on the board or in the call list (the slim columns). */
export interface CallRow {
  call_id: string;
  source: "retell" | "simulated";
  status: "ongoing" | "ended" | "analyzed";
  started_at: string;
  lane: Lane | null;
  red_flags: string[];
  cluster: string | null;
  intent: string | null;
  reason: string | null;
  caller_name: string | null;
  callback_number: string | null;
  from_number: string | null;
  transfer_status: TransferStatus | null;
  disconnection_reason: string | null;
  needs_review: boolean;
  /** Still on the line: a live call that hasn't ended, or a simulated call before its scripted end. */
  on_line: boolean;
  rules_lane?: Lane | null;
  jev_lane?: Lane | null;
  waiting_min?: number;
}

export interface SurgeState {
  surge_on: boolean;
  switched_at: string | null;
  status_message: string | null;
  routine_callback_window: string;
  priority_callback_window: string;
  surge_routine_window: string;
  surge_priority_window: string;
}

export interface Kpis {
  total: number;
  calls_10min: number;
  on_line: number;
  hung_up: number;
  handled_by_ai: number;
  sorted: number;
  red_median_handoff_s: number | null;
  amber_waiting: number;
  oldest_amber_min: number | null;
  amber_target_min: number;
  red_not_connected: number;
  ai_handled_share: number | null;
}

export interface VolumeBucket {
  bucket: string;
  calls: number;
  red: number;
  amber: number;
  green: number;
}

export interface Board {
  lanes: Partial<Record<Lane | "unsorted", number>>;
  clusters: { cluster: string; calls: number; red_flags: number }[];
  cluster_series: Record<string, number[]>;
  red: CallRow[];
  amber_queue: CallRow[];
  green: CallRow[];
  unsorted: CallRow[];
  volume_1min: VolumeBucket[];
  kpis: Kpis;
  surge: SurgeState;
  open_suggestions: number;
}

interface SuggestionBase {
  id: number;
  call_id: string | null;
  status: "open" | "accepted" | "snoozed" | "dismissed" | "resolved" | "expired";
  snooze_until: string | null;
  created_at: string;
  decided_at: string | null;
}

export type Suggestion =
  | (SuggestionBase & {
      type: "surge_mode";
      evidence: { calls: number; window_min: number; normal: number; red_waiting: number; hung_up_early: number; text: string };
      recommendation: { action: string };
    })
  | (SuggestionBase & {
      type: "status_message";
      evidence: { cluster: string; calls: number; share: number; text: string };
      recommendation: { template_id: string; message: string };
    })
  | (SuggestionBase & {
      type: "staffing_nurses";
      evidence: {
        nurse_minutes_per_hour: number;
        on_phones: number;
        amber_queue: number;
        oldest_amber_min: number;
        red_calls: number;
        red_no_answer: number;
        text: string;
      };
      recommendation: { role: "nurse"; count: number };
    })
  | (SuggestionBase & {
      type: "staffing_doctors";
      evidence: { red_calls: number; window_min: number; rough_signal: boolean; text: string };
      recommendation: { role: "er_doctor"; count: string | null };
    })
  | (SuggestionBase & {
      type: "red_not_connected";
      evidence: {
        transfer_status: TransferStatus;
        red_flags: string[];
        callback_number: string | null;
        caller_name: string | null;
        call_started: string;
        text: string;
      };
      recommendation: { action: string };
    });

export type SuggestionType = Suggestion["type"];

export interface CapturedDetail {
  value: string;
  status: "confirmed" | "unconfirmed" | "pending_confirmation" | "retry";
  method?: string;
  attempts?: number;
  read_back?: string;
  model_heard?: string | null;
  analysis_value?: string;
}

export interface CallDetail extends CallRow {
  scenario: string | null;
  ended_at: string | null;
  duration_ms: number | null;
  urgency: number | null;
  callback_source: "confirmed" | "caller_id" | null;
  rules_result: { lane: Lane | null; red_flags: string[]; reason: string | null; cluster: string | null; stage?: string } | null;
  jev_result: {
    lane: Lane | null;
    confidence?: number;
    latency_ms?: number;
    red_flag?: string;
    red_flag_present?: number;
    reason?: string;
    stage?: string;
  } | null;
  details: Record<string, CapturedDetail>;
  red_flag_at: string | null;
  transfer_started_at: string | null;
  transfer_ended_at: string | null;
  transfer_target: string | null;
  summary: string | null;
  recording_url: string | null;
  has_recording: boolean;
  transcript: { item_id: string; role: string; content: string | null; time_sec: number | null }[];
  events: { actor: "system" | "supervisor"; type: string; payload: Record<string, unknown>; created_at: string }[];
  alerts: Suggestion[];
}

export interface Analytics {
  window_min: number;
  volume_5min: VolumeBucket[];
  lane_mix: Record<Lane, number>;
  classifiers: {
    jev_classified: number;
    rules_jev_agree: number;
    mean_jev_confidence: number | null;
    mean_jev_latency_ms: number | null;
  };
  events: Record<string, number>;
  details: Partial<Record<CapturedDetail["status"], number>> & { confirmation_rate: number | null };
  handoff: {
    red_calls: number;
    mean_sec_flag_to_transfer: number | null;
    mean_sec_to_nurse_answer: number | null;
    connected: number;
    told_to_call_911: number;
    other_not_connected: number;
    share_told_to_call_911: number | null;
  };
}

export interface NurseLine {
  id: number;
  label: string;
  number: string;
  role: string;
  on_duty: boolean;
  priority: number;
  updated_at: string;
}

export interface StatusMessages {
  active: string | null;
  templates: { id: string; event: string; cluster: string; text: string }[];
}

export interface SimState {
  scenario: string | null;
  running: boolean;
  inserted: number;
  total: number;
  scenarios: { id: string; label: string; default_count: number }[];
}
