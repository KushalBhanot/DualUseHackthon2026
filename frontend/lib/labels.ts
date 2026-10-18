import type { Lane, TransferStatus } from "./types";

// Display names for the backend's label sets (backend/app/classify/labels.py).

export const LANE: Record<Lane, string> = { red: "Now", amber: "A person soon", green: "Can wait" };

export const LANE_RULE: Record<Lane, string> = {
  red: "Red flag · warm transfer under 10 s",
  amber: "Never automated · callback within 15 min",
  green: "Status message · scheduled callback",
};

export const LANE_ORDER: Lane[] = ["red", "amber", "green"];

export const FLAG: Record<string, string> = {
  chest_pain: "Chest pain",
  breathing: "Trouble breathing",
  bleeding: "Bleeding won't stop",
  stroke: "Stroke signs",
  unresponsive: "Unresponsive / fainted",
  seizure: "Seizure",
  self_harm_or_violence: "Self-harm or violence",
  overdose_poisoning: "Overdose or poisoning",
  severe_allergy: "Severe allergy",
  pregnancy_bleeding_or_pain: "Pregnancy bleeding or pain",
  infant_fever: "Infant fever",
  caller_in_danger: "Caller in danger",
};

export const REASON: Record<string, string> = {
  asked_for_person: "Asked for a person",
  confused_or_unclear: "Confused or unclear",
  family_locating: "Family locating",
  mental_health: "Mental health",
  child_under_2: "Child under 2",
  hospice: "Hospice",
  recent_discharge: "Recent discharge",
  vulnerable_caller: "Vulnerable caller",
  repeat_caller: "Repeat caller",
  info_did_not_help_and_vulnerable: "Info didn't help, vulnerable",
};

export const CLUSTER: Record<string, string> = {
  outage: 'Outage and "are you open?"',
  family: "Looking for a family member",
  help: "Offers to help",
  media: "Media requests",
  scheduling: "Appointments",
  billing: "Billing",
  medication: "Medication and refills",
  mental_health: "Distress and anxiety",
  child: "Children under 2",
  injury_or_illness: "Injury or illness",
  other: "Other",
};

export const TRANSFER: Record<TransferStatus, { tone: "green" | "red"; label: string }> = {
  connected: { tone: "green", label: "Nurse connected" },
  no_answer: { tone: "red", label: "No answer · told to call 911" },
  caller_hung_up: { tone: "red", label: "Caller hung up" },
  never_started: { tone: "red", label: "Transfer never started" },
};

export const DETAIL_STATUS: Record<string, { tone: "green" | "amber" | "grey" | "blue"; label: string }> = {
  confirmed: { tone: "green", label: "Confirmed" },
  unconfirmed: { tone: "amber", label: "Unconfirmed" },
  pending_confirmation: { tone: "grey", label: "Reading back" },
  retry: { tone: "amber", label: "Retrying" },
};

export const DETAIL_FIELD: Record<string, string> = {
  caller_name: "Name",
  callback_number: "Callback",
  patient_name: "Patient",
  date_of_birth: "Date of birth",
  doctor_name: "Doctor",
  medication_name: "Medication",
};

export const RESOLVE_OUTCOME = {
  called_back: "Called back",
  reached_911: "Reached 911",
  unreachable: "Unreachable",
} as const;

export const label = (map: Record<string, string>, key: string | null | undefined) => (key ? map[key] ?? humanize(key) : "");

export function humanize(s: string) {
  const t = s.replace(/_/g, " ");
  return t.charAt(0).toUpperCase() + t.slice(1);
}
