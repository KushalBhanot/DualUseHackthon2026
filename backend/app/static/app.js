// Night Ledger supervisor board. Plain JS, polls /api/state, renders into #main.
const S = { view: 'board', data: null, sel: null, detail: null, q: '', callsLane: '', calls: [], nurse: [], templates: null, edits: {}, brief: null };
const LANG = { en: 'English', es: 'Spanish', ko: 'Korean', hy: 'Armenian', zh: 'Mandarin', vi: 'Vietnamese', tl: 'Tagalog' };
const CB = { ai_queued: ['grey', 'AI callback queued'], scheduled: ['grey', 'AI callback queued'], ai_calling: ['blue', 'AI calling back…'], ai_reached_ok: ['green', 'Reached · fine'], ai_reached_red: ['red', 'Reached · red flag, transferred'], ai_no_answer: ['amber', 'No answer · retrying'], callback_failed: ['red', 'Unreachable twice'], welfare_check: ['grey', 'Welfare check requested'], closed: ['grey', 'Closed'], try_again: ['grey', 'Trying again'] };
const LANE = { red: 'Now', amber: 'A person soon', green: 'Can wait' };
const LANE_RULE = { red: 'Red flag · warm transfer under 10 s', amber: 'Never automated · callback within 15 min', green: 'Status message · scheduled callback' };
const CLUSTER = { outage: 'Outage and "are you open?"', family: 'Looking for a family member', help: 'Offers to help', media: 'Media requests',
  scheduling: 'Appointments', billing: 'Billing', medication: 'Medication and refills', mental_health: 'Distress and anxiety',
  child: 'Children under 2', injury_or_illness: 'Injury or illness', other: 'Other' };
const TEMPLATE_FOR = { outage: 'outage', help: 'help', family: 'family' };
const FLAG = { chest_pain: 'Chest pain', breathing: 'Trouble breathing', bleeding: 'Bleeding won\'t stop', stroke: 'Stroke signs', unresponsive: 'Unresponsive / fainted',
  seizure: 'Seizure', self_harm_or_violence: 'Self-harm or violence', overdose_poisoning: 'Overdose or poisoning', severe_allergy: 'Severe allergy',
  pregnancy_bleeding_or_pain: 'Pregnancy bleeding or pain', infant_fever: 'Infant fever', caller_in_danger: 'Caller in danger' };
const REASON = { asked_for_person: 'Asked for a person', confused_or_unclear: 'Confused or unclear', family_locating: 'Family locating', mental_health: 'Mental health',
  child_under_2: 'Child under 2', hospice: 'Hospice', recent_discharge: 'Recent discharge', vulnerable_caller: 'Vulnerable caller', repeat_caller: 'Repeat caller' };
const TRANSFER = { connected: ['green', 'Nurse connected'], no_answer: ['red', 'No answer · told to call 911'], caller_hung_up: ['red', 'Caller hung up'], never_started: ['red', 'Transfer never started'] };

const $ = (s) => document.querySelector(s);
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const clock = (s) => { s = Math.floor(s) % 86400; return [Math.floor(s / 3600), Math.floor(s / 60) % 60, s % 60].map((v) => String(v).padStart(2, '0')).join(':'); };
const wait = (s) => { s = Math.max(0, Math.floor(s)); return s < 60 ? s + 's' : Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0'); };
const pct = (v) => (v == null ? '—' : Math.round(v * 100) + '%');
const phone = (n) => { const d = String(n || '').replace(/\D/g, '').slice(-10); return d.length === 10 ? `(${d.slice(0, 3)}) ${d.slice(3, 6)}-${d.slice(6)}` : esc(n || 'unknown'); };
const simClock = () => (S.data?.sim?.clock_s != null ? S.data.sim.clock_s : (Date.now() / 1000 - new Date().getTimezoneOffset() * 60) % 86400);
const atClock = (t) => { const sim = S.data?.sim; return sim?.started_at ? clock(sim.clock_start + (t - sim.started_at)) : new Date(t * 1000).toTimeString().slice(0, 8); };

async function api(path, opts = {}) {
  const r = await fetch(path, { headers: { 'content-type': 'application/json' }, ...opts, body: opts.body ? JSON.stringify(opts.body) : undefined });
  if (!r.ok) { const t = await r.json().catch(() => ({})); throw new Error(t.detail || r.statusText); }
  return r.json();
}
function toast(msg) { $('#toast').innerHTML = `<div class="toast" role="status">${esc(msg)}</div>`; clearTimeout(toast.t); toast.t = setTimeout(() => ($('#toast').innerHTML = ''), 2600); }

async function poll() {
  try {
    S.data = await api('/api/state');
    if (S.sel) {
      S.detail = await api('/api/calls/' + encodeURIComponent(S.sel)).catch(() => null);
      if (!S.detail) S.sel = null; // the call is gone (for example after a board reset)
    }
    if (S.view === 'calls') S.calls = await api('/api/calls?limit=200' + (S.callsLane ? '&lane=' + S.callsLane : ''));
    render();
  } catch (e) { console.warn(e); }
}

function render() {
  const a = document.activeElement;
  const editing = a && $('#main').contains(a) && (a.tagName === 'TEXTAREA' || a.tagName === 'INPUT');
  if (!editing) $('#main').innerHTML = ({ board: viewBoard, calls: viewCalls, analytics: viewAnalytics, setup: viewSetup, demo: viewDemo }[S.view] || viewBoard)();
  $('#respond').innerHTML = S.view === 'board' ? respondBar() : '';
  $('#drawer').innerHTML = S.brief ? briefModal(S.brief) : (S.sel && S.detail ? drawer(S.detail) : '');
  const urgent = (S.data?.suggestions || []).some((x) => x.type === 'red_not_connected');
  $('#navdot').hidden = !urgent;
  document.querySelectorAll('.side [data-view]').forEach((b) => b.setAttribute('aria-current', b.dataset.view === S.view ? 'page' : 'false'));
}

// ------------------------------------------------------------------ board
function header(title, sub, right = '') {
  return `<div class="head"><div><h1>${title}</h1><div class="sub">${sub}</div></div><div class="grow"></div>${right}</div>`;
}

function viewBoard() {
  const d = S.data; if (!d) return '<p class="muted">Loading the line…</p>';
  const b = d.board, sg = d.surge, sim = d.sim;
  const scen = sim.scenario ? ` · ${esc(sim.scenarios[sim.scenario])}` : '';
  const right = `
    <a class="pill" href="/api/report" target="_blank" rel="noopener">After-action report</a>
    <span class="surgebadge ${sg.is_on ? 'on' : 'off'}">${sg.is_on ? '<span class="pulse"></span>Surge mode on' : 'Surge mode off'}</span>
    <label class="search"><svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7" fill="none" stroke="#6B7280" stroke-width="2"/><path d="M20 20l-4-4" stroke="#6B7280" stroke-width="2" stroke-linecap="round"/></svg><span class="sr">Filter calls</span><input id="q" type="search" placeholder="Filter callers, intents…" value="${esc(S.q)}"><span class="kbd">⌘ K</span></label>`;
  return header('Night shift, K. Mensah', `Harbor General · after-hours line · <span class="tab">${clock(simClock())}</span>${scen}`, right)
    + decisions(d.suggestions) + statusCard(sg) + kpis(b) + lanes(b) + `<div class="row">${hotspotsCard(b)}${callbacksCard(b.callbacks)}</div>` + `<div class="row">${watch(b, sg)}${volume(b)}${languagesCard(b.languages)}</div>`;
}

function decisions(list) {
  if (!list.length) return '';
  // Red alerts first. Show two in full; fold the rest so the other decisions stay visible.
  const reds = list.filter((s) => s.type === 'red_not_connected'), rest = list.filter((s) => s.type !== 'red_not_connected');
  const shown = S.showAllRed ? reds : reds.slice(0, 2), hidden = S.showAllRed ? [] : reds.slice(2);
  const fold = hidden.length ? `<div class="decision redalert" style="padding:12px 20px"><b style="color:#991B1B">+${hidden.length} more red caller${hidden.length > 1 ? 's' : ''} not connected</b>
    <span style="flex:1 1 300px">${hidden.map((s) => esc(s.evidence.caller_name || 'Caller')).join(' · ')}</span><button class="pill sm" data-act="showred">Show all</button></div>` : '';
  return `<section class="decisions" aria-label="Decisions waiting for you">${shown.map(decision).join('')}${fold}${rest.map(decision).join('')}</section>`;
}

function ev(v, l) { return `<div class="ev"><b class="tab">${esc(v)}</b><span>${esc(l)}</span></div>`; }

function decision(s) {
  const e = s.evidence || {}, r = s.recommendation || {};
  if (s.type === 'red_not_connected') {
    const flags = (e.red_flags || []).map((f) => FLAG[f] || f).join(', ') || 'red flag';
    return `<div class="decision redalert" role="alert"><svg width="22" height="20" viewBox="0 0 18 16" aria-hidden="true"><path d="M9 0l9 16H0z" fill="#DC2626"/><path d="M9 6v4M9 12.5v.5" stroke="#fff" stroke-width="1.8" stroke-linecap="round"/></svg>
      <div class="body"><h2>Red caller not connected</h2><div>${esc(flags)} · ${esc(e.caller_name || 'Unknown caller')} · call back <b class="tab">${phone(e.callback_number)}</b> · ${esc((TRANSFER[e.transfer_status] || [, e.transfer_status])[1])} · ${atClock(e.at)}</div>
      <div class="muted" style="font-size:13px">This alert can't be snoozed or dismissed. Close it with what happened.</div></div>
      <div class="actions"><button class="pill red" data-act="decide" data-id="${s.id}" data-action="resolve" data-outcome="called_back">Called back</button><button class="pill" data-act="decide" data-id="${s.id}" data-action="resolve" data-outcome="reached_911">Reached 911</button><button class="pill" data-act="decide" data-id="${s.id}" data-action="resolve" data-outcome="unreachable">Unreachable</button><button class="pill sm" data-act="open" data-id="${esc(s.call_id)}">Handoff Card</button></div></div>`;
  }
  if (s.type === 'amber_unreachable') {
    return `<div class="decision amberalert" role="alert"><div class="body"><h2>${esc(e.caller_name || 'Caller')} didn't pick up twice</h2><div>${esc(REASON[e.reason] || e.reason || '')} · ${esc(e.intent || '')} · <span class="tab">${phone(e.callback_number)}</span></div></div>
      <div class="actions"><button class="pill dark" data-act="decide" data-id="${s.id}" data-action="resolve" data-outcome="try_again">Try again</button><button class="pill" data-act="decide" data-id="${s.id}" data-action="resolve" data-outcome="welfare_check">Ask police for a welfare check</button><button class="pill" data-act="decide" data-id="${s.id}" data-action="resolve" data-outcome="closed">Close</button></div></div>`;
  }
  if (s.type === 'callback_unreachable') {
    return `<div class="decision amberalert" role="alert"><div class="body"><h2>${esc(e.caller_name || 'Caller')} hung up and didn't answer 2 AI callbacks</h2><div>${esc(e.intent || '')}${e.neighborhood ? ' · ' + esc(e.neighborhood) : ''} · <span class="tab">${phone(e.callback_number)}</span></div><div class="muted" style="font-size:13px">Only a person can close this.</div></div>
      <div class="actions"><button class="pill dark" data-act="decide" data-id="${s.id}" data-action="resolve" data-outcome="try_again">Try again</button><button class="pill" data-act="decide" data-id="${s.id}" data-action="resolve" data-outcome="welfare_check">Ask police for a welfare check</button><button class="pill" data-act="decide" data-id="${s.id}" data-action="resolve" data-outcome="closed">Close</button><button class="pill sm" data-act="open" data-id="${esc(s.call_id)}">Handoff Card</button></div></div>`;
  }
  if (s.type === 'surge_mode') {
    return `<div class="decision surge"><div class="body"><span class="muted" style="font-size:13px;font-weight:700">Decision 1 · suggested by the line, needs you</span><h2>Switch on surge mode?</h2>
      <div class="evidence">${ev(e.calls_3min, `calls in 3 min (normal ≈ ${e.normal_3min})`)}${ev(e.top_cluster_count, `about ${CLUSTER[e.top_cluster] || e.top_cluster}`)}${ev(e.red_waiting, 'red flags waiting')}${ev(e.amber_waiting, 'waiting for a person')}${ev(e.hung_up_3min, 'hung up while waiting')}</div>
      <div class="muted" style="font-size:13px">Surge mode gives held callers callback times, plays the active status message and calls back people who hung up.</div></div>
      <div class="actions"><button class="pill amber" data-act="decide" data-id="${s.id}" data-action="accept">Switch on surge mode</button><button class="pill ghost-dark" data-act="decide" data-id="${s.id}" data-action="snooze">Not yet, ask in 2 min</button><button class="pill ghost-dark sm" data-act="decide" data-id="${s.id}" data-action="dismiss">Dismiss</button></div></div>`;
  }
  if (s.type === 'status_message') {
    const text = S.edits[s.id] ?? r.text;
    return `<div class="decision"><div class="body"><span class="muted" style="font-size:13px;font-weight:700">Decision 2 · pre-approved wording</span><h2>Play this message to every caller?</h2>
      <div><b>${esc(e.count)}</b> of ${esc(e.calls_10min)} calls in the last 10 min are about <b>${esc(CLUSTER[e.cluster] || e.cluster)}</b> (${pct(e.share)}).</div>
      <label class="sr" for="msg-${s.id}">Status message</label><textarea id="msg-${s.id}" data-edit="${s.id}">${esc(text)}</textarea></div>
      <div class="actions"><button class="pill dark" data-act="decide" data-id="${s.id}" data-action="accept" data-text="1">Activate message</button><button class="pill" data-act="decide" data-id="${s.id}" data-action="snooze">Not yet</button><button class="pill sm" data-act="decide" data-id="${s.id}" data-action="dismiss">Dismiss</button></div></div>`;
  }
  if (s.type === 'staffing_nurses') {
    const n = r.count;
    return `<div class="decision"><div class="body"><span class="muted" style="font-size:13px;font-weight:700">Decision 6 · staffing</span><h2>Call in ${esc(n)} nurse${n > 1 ? 's' : ''}?</h2>
      <div class="evidence">${ev(e.amber_waiting, 'waiting for a person')}${ev(e.oldest_amber_min + ' min', `oldest wait (target ${e.target_min})`)}${ev(e.red_per_h + '/h', 'red calls')}${ev(e.amber_per_h + '/h', 'amber callbacks')}${ev(e.on_phones, 'nurses on phones')}</div>
      <div class="muted" style="font-size:13px">Accepting records your decision. Paging staff happens outside Night Ledger.</div></div>
      <div class="actions"><button class="pill dark" data-act="decide" data-id="${s.id}" data-action="accept">Record: call them in</button><button class="pill" data-act="decide" data-id="${s.id}" data-action="snooze">Not yet</button><button class="pill sm" data-act="decide" data-id="${s.id}" data-action="dismiss">Dismiss</button></div></div>`;
  }
  if (s.type === 'staffing_doctors') {
    return `<div class="decision"><div class="body"><span class="muted" style="font-size:13px;font-weight:700">Decision 6 · rough signal only</span><h2>Consider calling in ${esc(r.count)} ER doctors</h2>
      <div>${esc(e.red_injury_30min)} injury or illness red-flag calls in 30 min (≈ ${esc(e.per_hour)}/h). Phone calls can't measure how full the ER is.</div></div>
      <div class="actions"><button class="pill dark" data-act="decide" data-id="${s.id}" data-action="accept">Record decision</button><button class="pill" data-act="decide" data-id="${s.id}" data-action="snooze">Not yet</button><button class="pill sm" data-act="decide" data-id="${s.id}" data-action="dismiss">Dismiss</button></div></div>`;
  }
  return '';
}

function statusCard(sg) {
  if (!sg.status_message) return '';
  return `<section class="card" style="padding:16px 20px;display:flex;flex-wrap:wrap;gap:12px;align-items:center;border-color:#CDE3F5;background:#F5FAFE">
    <span class="chip blue">Playing to every caller</span><span style="flex:1 1 400px">${esc(sg.status_message)}</span>
    <button class="pill sm" data-act="stopmsg">Stop message</button></section>`;
}

function kpis(b) {
  const k = b.kpis;
  const last10 = b.volume.slice(-10).map((v) => v.red + v.amber + v.green);
  const max = Math.max(1, ...last10);
  const bars = last10.map((n) => `<span class="${n ? '' : 'zero'}" style="height:${Math.max(12, (n / max) * 100)}%"></span>`).join('');
  const hand = k.red_median_handoff_s;
  return `<div class="row">
    <section class="card kpi"><span class="l">Calls, last 10 min</span><span class="v tab">${k.calls_10min}</span><div class="bars" aria-hidden="true">${bars}</div></section>
    <section class="card kpi"><span class="l">On the line now</span><span class="v tab">${k.on_line}</span><span class="muted" style="font-size:13px">${k.total} tonight · ${k.hung_up} hung up</span></section>
    <section class="card kpi" style="${k.red_not_connected ? 'border-color:#F6C8C8;background:#FFF8F8' : ''}"><span class="l">Red handoff, median</span><span class="v tab">${hand == null ? '—' : hand + ' s'}</span><span style="font-size:13px" class="${k.red_not_connected ? '' : 'muted'}">${k.red_not_connected ? `<b style="color:#991B1B">${k.red_not_connected} not connected</b>` : 'target under 10 s'}</span></section>
    <section class="card kpi" style="${k.oldest_amber_min > 15 ? 'border-color:#F5D9A8;background:#FFFBF3' : ''}"><span class="l">Waiting for a person</span><span class="v tab">${k.amber_waiting}</span><span class="muted" style="font-size:13px">oldest <span class="tag tab">${k.oldest_amber_min} min</span> · target 15</span></section>
    <section class="accent kpi"><span class="l" style="color:#fff;opacity:.95">Answered without a human</span><span class="v tab">${pct(k.ai_handled_share)}</span>
      <div style="height:6px;border-radius:3px;background:rgba(255,255,255,.35);margin-top:6px"><div style="width:${Math.round(k.ai_handled_share * 100)}%;height:6px;border-radius:3px;background:#fff"></div></div>
      <span style="font-size:13px;opacity:.95">${k.ai_handled} callers got their answer · red flags always reach a nurse</span></section></div>`;
}

function match(c) { if (!S.q) return true; const t = S.q.toLowerCase(); return [c.caller_name, c.intent, c.cluster, c.reason].some((v) => String(v || '').toLowerCase().includes(t)); }

function callRow(c) {
  const chips = [];
  (c.red_flags || []).forEach((f) => chips.push(`<span class="chip red-soft">${esc(FLAG[f] || f)}</span>`));
  if (c.lane === 'amber' && c.reason) chips.push(`<span class="chip amber">${esc(REASON[c.reason] || c.reason)}</span>`);
  if (c.transfer_status) { const [cl, l] = TRANSFER[c.transfer_status] || ['grey', c.transfer_status]; chips.push(`<span class="chip ${cl === 'green' ? 'green' : 'red'}">${esc(l)}</span>`); }
  if (c.callback_status && c.lane !== 'red' && c.callback_status !== 'waiting' && c.disconnection_reason !== 'user_hangup' && !CB[c.callback_status]) chips.push(`<span class="chip grey">Callback: ${esc(c.callback_status.replace('_', ' '))}</span>`);
  if (c.language && c.language !== 'en') chips.push(`<span class="chip purple">${esc(LANG[c.language] || c.language)}</span>`);
  if (c.disconnection_reason === 'user_hangup') { const cb = CB[c.callback_status]; chips.push(cb ? `<span class="chip ${cb[0]}">Hung up · ${esc(cb[1])}</span>` : '<span class="chip grey">Hung up</span>'); }
  if (c.neighborhood) chips.push(`<span class="muted" style="font-size:12px">${esc(c.neighborhood)}</span>`);
  const rank = { green: 0, amber: 1, red: 2 };
  if (c.model_lane && c.rules_lane === c.lane && rank[c.lane] > rank[c.model_lane]) chips.push(`<span class="chip blue" title="The model said ${esc(c.model_lane)}; the rules raised it">Rules caught it</span>`);
  if (c.needs_review) chips.push('<span class="chip grey">Review</span>');
  if (c.source === 'retell') chips.push('<span class="chip purple">Live call</span>');
  return `<button class="callrow ${S.sel === c.call_id ? 'sel' : ''}" data-act="open" data-id="${esc(c.call_id)}">
    <span class="who">${esc(c.caller_name || 'Unknown caller')}</span><span class="tag tab" title="Time since the call came in">${wait(c.wait_s)}</span>
    <span class="what">${esc(c.intent || 'Classifying…')}</span><span class="meta">${chips.join('')}</span></button>`;
}

function lanes(b) {
  const col = (l, list) => `<section class="card lane ${l}" aria-label="${LANE[l]}"><div class="bar"></div>
    <div class="lane-h"><div><div class="ttl">${LANE[l]} <span class="info">i</span></div><div class="rule">${LANE_RULE[l]}</div></div><span class="n tab">${b.counts[l]}</span></div>
    <div class="calls">${list.filter(match).map(callRow).join('') || `<div class="empty">${l === 'red' ? 'No red-flag callers right now.' : 'Nobody here yet.'}</div>`}</div></section>`;
  return `<div class="lanes">${col('red', b.red)}${col('amber', b.amber)}${col('green', b.green)}</div>`;
}

function watch(b, sg) {
  const rows = b.clusters.slice(0, 6).map((c) => {
    const max = Math.max(1, ...c.series);
    const spark = c.series.map((n) => `<span class="${n ? '' : 'zero'}" style="height:${Math.max(14, (n / max) * 100)}%"></span>`).join('');
    const tpl = TEMPLATE_FOR[c.cluster];
    const btn = tpl && sg.status_cluster !== tpl ? `<button class="pill sm" data-act="usetpl" data-tpl="${tpl}">Use status message</button>` : (tpl ? '<span class="chip blue">Message playing</span>' : '');
    return `<div class="cluster"><div><div class="nm">${esc(CLUSTER[c.cluster] || c.cluster)}</div><div class="muted" style="font-size:13px"><b class="tab" style="color:#111827">${c.count}</b> callers · ${c.red ? `<span style="color:#991B1B;font-weight:700">${c.red} red flag${c.red > 1 ? 's' : ''}</span>` : '0 red flags'}</div></div>
      <div style="display:flex;align-items:center;gap:12px"><div class="spark" aria-hidden="true">${spark}</div>${btn}</div></div>`;
  }).join('');
  return `<section class="card" style="flex:1.3 1 420px;min-width:0;overflow:hidden"><div class="card-h"><span class="ttl">Watch · what callers keep asking <span class="info">i</span></span><span class="grow"></span><span class="muted" style="font-size:13px;font-weight:600">last 10 min</span></div>
    ${rows || '<div class="empty">Clusters appear here as calls come in. One card instead of 140 calls.</div>'}</section>`;
}

function volume(b) {
  const max = Math.max(1, ...b.volume.map((v) => v.red + v.amber + v.green));
  const cols = b.volume.map((v) => {
    const h = (n) => (n / max) * 120;
    return `<div style="flex:1;display:flex;flex-direction:column-reverse;gap:2px;height:124px">
      ${v.green ? `<span style="height:${h(v.green)}px;background:#74D47B;border-radius:4px"></span>` : ''}${v.amber ? `<span style="height:${h(v.amber)}px;background:#D97706;border-radius:4px"></span>` : ''}${v.red ? `<span style="height:${h(v.red)}px;background:#DC2626;border-radius:4px"></span>` : ''}
      ${v.red + v.amber + v.green ? '' : '<span style="height:6px;background:#F3F5F7;border-radius:3px"></span>'}</div>`;
  }).join('');
  return `<section class="card" style="flex:1 1 360px;min-width:0;padding-bottom:16px"><div class="card-h"><span class="ttl">Calls per minute <span class="info">i</span></span></div>
    <div style="display:flex;align-items:flex-end;gap:4px;padding:0 20px" role="img" aria-label="Calls per minute over the last 20 minutes by lane">${cols}</div>
    <div style="display:flex;justify-content:space-between;padding:6px 20px 0" class="muted"><span style="font-size:12px">20 min ago</span><span style="font-size:12px">now</span></div>
    <div style="display:flex;gap:14px;padding:10px 20px 0;font-size:12px;font-weight:600;color:#374151">
      <span style="display:flex;align-items:center;gap:6px"><span style="width:14px;height:4px;border-radius:2px;background:#DC2626"></span>Now</span>
      <span style="display:flex;align-items:center;gap:6px"><span style="width:14px;height:4px;border-radius:2px;background:#D97706"></span>A person soon</span>
      <span style="display:flex;align-items:center;gap:6px"><span style="width:14px;height:4px;border-radius:2px;background:#74D47B"></span>Can wait</span></div></section>`;
}

function respondBar() {
  const d = S.data; if (!d) return '';
  const nextAmber = d.board.amber[0];
  return `<div class="respond"><b style="font-size:14px">Response</b><span class="muted">The AI sorts. Surge mode, broadcasts and call-ins wait for you.</span><span class="grow"></span>
    ${nextAmber ? `<button class="pill ghost-dark" data-act="open" data-id="${esc(nextAmber.call_id)}">Next callback: ${esc(nextAmber.caller_name || 'caller')}</button>` : ''}
    ${d.surge.status_message ? '<button class="pill ghost-dark" data-act="stopmsg">Stop status message</button>' : ''}
    <button class="pill ${d.surge.is_on ? 'ghost-dark' : 'amber'}" data-act="surge" data-on="${d.surge.is_on ? 0 : 1}">${d.surge.is_on ? 'Switch surge mode off' : 'Switch on surge mode'}</button></div>`;
}


function hotspotsCard(b) {
  const spots = b.hotspots || [];
  const max = Math.max(1, ...spots.map((s) => s.count));
  const rows = spots.map((s) => `<div class="cluster"><div><div class="nm">${esc(s.place)}</div><div class="muted" style="font-size:13px"><b class="tab" style="color:#111827">${s.count}</b> callers · ${s.red ? `<span style="color:#991B1B;font-weight:700">${s.red} red${s.flags.length ? ' (' + esc(s.flags.map((f) => FLAG[f] || f).join(', ')) + ')' : ''}</span>` : '0 red'} · first <span class="tab">${esc(s.first_clock)}</span></div></div>
    <div style="width:140px;height:8px;border-radius:4px;background:#F3F5F7"><div style="width:${Math.round((s.count / max) * 100)}%;height:8px;border-radius:4px;background:${s.red ? '#DC2626' : '#1A87D6'}"></div></div></div>`).join('');
  return `<section class="card" style="flex:1.3 1 460px;min-width:0;overflow:hidden"><div class="card-h"><span class="ttl">Hotspots · where calls come from <span class="info">i</span></span><span class="grow"></span><span class="muted" style="font-size:13px;font-weight:600">last 15 min</span></div>
    ${rows || '<div class="empty">Places appear as callers mention them.</div>'}
    <div style="padding:14px 20px;border-top:1px solid #F0F2F5;display:flex;gap:10px;align-items:center;flex-wrap:wrap"><span class="muted" style="font-size:13px;flex:1 1 220px">Callers are your earliest sensor. Send incident command what they're reporting.</span><button class="pill dark" data-act="brief">Brief for incident command</button></div></section>`;
}

function callbacksCard(cb) {
  if (!cb) return '';
  const stat = (v, l, col) => `<div class="ev" style="background:#F6F8FA"><b class="tab" style="${col ? 'color:' + col : ''}">${v}</b><span>${l}</span></div>`;
  const rows = cb.recent.slice(0, 5).map((r) => { const s = CB[r.status] || ['grey', r.status || 'queued'];
    return `<button class="callrow" data-act="open" data-id="${esc(r.call_id)}"><span class="who">${esc(r.caller_name || 'Caller')}</span><span class="chip ${s[0]}">${esc(s[1])}</span><span class="what">${esc(r.intent || '')}${r.neighborhood ? ' · ' + esc(r.neighborhood) : ''}</span></button>`; }).join('');
  return `<section class="card" style="flex:1 1 380px;min-width:0;overflow:hidden"><div class="card-h"><span class="ttl">AI callbacks to hang-ups <span class="info">i</span></span></div>
    <div class="evidence" style="padding:0 20px 12px">${stat(cb.hung_up, 'hung up')}${stat(cb.calling + cb.queued, 'calling / queued')}${stat(cb.reached_ok + cb.reached_red, 'reached again', '#2F7A35')}${stat(cb.reached_red, 'red flags found', cb.reached_red ? '#991B1B' : '')}${stat(cb.failed, 'unreachable')}</div>
    <div class="calls" style="max-height:260px;border-top:1px solid #F0F2F5">${rows || '<div class="empty">Nobody has hung up yet. Every hang-up under 30 s gets an AI callback.</div>'}</div></section>`;
}

function languagesCard(langs) {
  const entries = Object.entries(langs || {}).sort((a, b) => b[1] - a[1]);
  const total = entries.reduce((n, [, v]) => n + v, 0) || 1;
  const other = entries.filter(([k]) => k !== 'en').reduce((n, [, v]) => n + v, 0);
  const cols = { en: '#C9D1DA', es: '#1A87D6', ko: '#C78BE8', hy: '#F6C35B', zh: '#74D47B', vi: '#5DB8F2', tl: '#E58E5A' };
  return `<section class="card" style="flex:0.8 1 280px;min-width:0;padding-bottom:16px"><div class="card-h"><span class="ttl">Languages <span class="info">i</span></span></div>
    <div style="padding:0 20px"><div class="v tab" style="font-size:30px;font-weight:800">${Math.round((other / total) * 100)}%</div><div class="muted" style="font-size:13px">of callers this hour spoke a language other than English, answered in their language and translated live</div>
    <div style="display:flex;height:10px;border-radius:5px;overflow:hidden;margin:12px 0">${entries.map(([k, v]) => `<span style="width:${(v / total) * 100}%;background:${cols[k] || '#9AA3B5'}"></span>`).join('')}</div>
    <div style="display:flex;flex-wrap:wrap;gap:6px">${entries.map(([k, v]) => `<span class="chip grey"><span style="width:8px;height:8px;border-radius:50%;background:${cols[k] || '#9AA3B5'}"></span>${esc(LANG[k] || k)} ${v}</span>`).join('')}</div></div></section>`;
}

function briefModal(b) {
  return `<div class="scrim" data-act="closebrief"></div><aside class="drawer" role="dialog" aria-label="Brief for incident command" style="height:auto;bottom:auto;max-height:calc(100vh - 40px)">
    <div class="top"><div style="flex:1"><div class="muted" style="font-size:13px;font-weight:700">Facts only, from the call log · you send it</div><h2>Brief for incident command</h2></div><button class="pill sm" data-act="closebrief" aria-label="Close">✕</button></div>
    <div class="scroll"><label class="sr" for="brieftext">Brief text</label><textarea id="brieftext" readonly style="width:100%;min-height:220px;border-radius:14px;border:1px solid var(--border);background:var(--soft);padding:12px 14px;font:14px/1.6 Manrope,sans-serif">${esc(b.text)}</textarea>
    <span class="muted" style="font-size:13px">Paste it into the incident channel, radio log or WebEOC. Marking it sent records the decision in the after-action report.</span></div>
    <div class="foot"><button class="pill dark" data-act="copybrief">Copy brief</button><button class="pill" data-act="sentbrief">Mark as sent to IC</button></div></aside>`;
}

// ------------------------------------------------------------------ handoff card
function drawer(c) {
  const rr = c.rules_result || {}, m = c.jev_result || {};
  const flags = (c.red_flags || []);
  const step = { red: 4, amber: 3, green: 1 }[c.lane] ?? 0;
  const ladder = ['Ask', 'Slow', 'Hold: can wait', 'Hold: a person soon', 'Hand to a person'].map((n, i) => {
    const col = i <= step ? (i === step ? ({ red: '#DC2626', amber: '#D97706', green: '#74D47B' }[c.lane] || '#74D47B') : '#C9D1DA') : '#F3F5F7';
    return `<div><div style="background:${col}"></div><span style="${i === step ? '' : 'color:#6B7280'}">${n}</span></div>`;
  }).join('');
  const detail = (k, label) => { const d = (c.details || {})[k]; if (!d) return ''; const st = d.status; const cl = st === 'confirmed' ? 'green' : st === 'caller_id' ? 'blue' : 'amber';
    return `<span class="muted">${label}</span><span class="tab" style="font-weight:700">${k === 'callback_number' ? phone(d.value) : esc(d.value)}</span><span class="chip ${cl}">${esc(st === 'caller_id' ? 'caller ID' : st)}</span>`; };
  const transfer = c.transfer_status ? (() => { const [cl, l] = TRANSFER[c.transfer_status] || ['grey', c.transfer_status];
    const secs = c.transfer_started_at && c.red_flag_at ? (c.transfer_started_at - c.red_flag_at).toFixed(1) + ' s' : '—';
    return `<div class="sec"><h3>Warm transfer</h3><div class="kv"><span class="muted">Outcome</span><span style="font-weight:700">${esc(l)}</span><span class="chip ${cl === 'green' ? 'green' : 'red'}">${esc(c.transfer_status.replace('_', ' '))}</span>
      <span class="muted">Red flag → transfer</span><span class="tab" style="font-weight:700">${secs}</span><span class="chip grey">target 10 s</span><span class="muted">Nurse line</span><span>${esc(c.transfer_target || '—')}</span><span></span></div></div>`; })() : '';
  const events = (c.events || []).slice(-8).map((e) => `<div><span class="tab muted">${atClock(e.created_at)}</span><span>${esc(e.type.replace(/_/g, ' '))}${e.actor === 'supervisor' ? ' · <b>you</b>' : ''}</span></div>`).join('');
  const lowerTo = { red: ['amber', 'green'], amber: ['green'], green: [] }[c.lane] || [];
  const amberActs = c.lane === 'amber' && ['waiting', 'no_answer', null].includes(c.callback_status)
    ? `<button class="pill dark" data-act="cb" data-id="${esc(c.call_id)}" data-outcome="reached">Called back: reached</button><button class="pill" data-act="cb" data-id="${esc(c.call_id)}" data-outcome="no_answer">No answer</button>` : '';
  return `<div class="scrim" data-act="close"></div><aside class="drawer" role="dialog" aria-label="Handoff Card">
    <div class="top"><div style="flex:1;min-width:0"><div class="muted" style="font-size:13px;font-weight:700">Handoff Card · arrived ${atClock(c.started_at)}${c.source === 'simulated' ? ' · simulated' : ' · live call'}</div>
      <h2>${esc(c.caller_name || 'Unknown caller')}</h2><div class="tab" style="font-weight:600;margin-top:2px">${phone(c.callback_number || c.from_number)}${c.neighborhood ? ' · ' + esc(c.neighborhood) : ''}</div>${c.language && c.language !== 'en' ? `<span class="chip purple" style="margin-top:6px">${esc(LANG[c.language] || c.language)} · translated live</span>` : ''}</div>
      <span class="chip ${c.lane === 'red' ? 'red' : c.lane === 'amber' ? 'amber' : 'green'}" style="font-size:13px;padding:6px 12px">${LANE[c.lane] || 'Classifying'}</span>
      <button class="pill sm" data-act="close" aria-label="Close">✕</button></div>
    <div class="scroll">
      <div class="sec"><h3>Why they called</h3><div style="font-size:16px;font-weight:700">${esc(c.intent || c.summary || '—')}</div></div>
      <div class="sec"><h3>Red-flag screen</h3>${flags.length ? flags.map((f) => `<span class="chip red" style="margin:0 6px 6px 0">${esc(FLAG[f] || f)}</span>`).join('') : '<span class="chip green">No red flags</span>'}</div>
      <div class="sec"><h3>Why this lane</h3><div class="why">
        <span class="muted">Rules</span><span><b>${esc(LANE[rr.lane] || '—')}</b>${rr.red_flags?.length ? ' · ' + esc(rr.red_flags.join(', ')) : ''}${rr.reason ? ' · ' + esc(REASON[rr.reason] || rr.reason) : ''}</span>
        <span class="muted">Model</span><span>${m.lane ? `<b>${esc(LANE[m.lane])}</b> · ${esc(m.label || m.source || '')} ${m.confidence != null ? `<span class="tag tab">${Math.round(m.confidence * 100)}%</span>` : ''}` : '—'}</span>
        <span class="muted">Final</span><span><b>${esc(LANE[c.lane] || '—')}</b> · the higher lane wins. Only a person can lower a lane.</span></div></div>
      ${transfer}
      ${CB[c.callback_status] ? `<div class="sec"><h3>AI callback</h3><div class="kv"><span class="muted">Status</span><span style="font-weight:700">${esc(CB[c.callback_status][1])}</span><span class="chip ${CB[c.callback_status][0]}">${c.callback_attempts} attempt${c.callback_attempts === 1 ? '' : 's'}</span></div><div class="muted" style="font-size:13px;margin-top:6px">The callback agent says it's an AI, asks "Do you need help?", and sends any red flag straight to a nurse.</div></div>` : ''}
      <div class="sec"><h3>Details</h3><div class="kv">${detail('caller_name', 'Name')}${detail('callback_number', 'Callback')}</div></div>
      <div class="sec"><h3>What was said</h3><div class="transcript">${(c.transcript || []).map((t) => `<div class="bubble ${t.role === 'user' ? 'user' : 'agent'}"><b style="font-size:11px;letter-spacing:.06em;color:#6B7280">${t.role === 'user' ? 'CALLER' : 'AI'}</b><br>${esc(t.content)}${t.en ? `<div style="margin-top:6px;padding-top:6px;border-top:1px dashed #C9D1DA;color:#374151"><b style="font-size:11px;color:#6B7280">ENGLISH</b> ${esc(t.en)}</div>` : ''}</div>`).join('') || '<span class="muted">No transcript yet.</span>'}</div></div>
      <div class="sec"><h3>Ladder</h3><div class="ladder">${ladder}</div></div>
      <div class="sec"><h3>Log</h3><div class="log">${events || '<span class="muted">No events.</span>'}</div></div>
    </div>
    <div class="foot">${amberActs}${lowerTo.map((l) => `<button class="pill sm" data-act="lower" data-id="${esc(c.call_id)}" data-lane="${l}">Lower to ${LANE[l]}…</button>`).join('')}</div></aside>`;
}

// ------------------------------------------------------------------ other views
function viewCalls() {
  const rows = S.calls.filter(match).map((c) => `<tr class="click" data-act="open" data-id="${esc(c.call_id)}"><td class="tab">${atClock(c.started_at)}</td>
    <td><span class="chip ${c.lane === 'red' ? 'red' : c.lane === 'amber' ? 'amber' : 'green'}">${LANE[c.lane] || '—'}</span></td><td style="font-weight:700">${esc(c.caller_name || 'Unknown')}</td>
    <td>${esc(c.intent || '')}</td><td>${esc(CLUSTER[c.cluster] || c.cluster || '')}</td><td>${c.transfer_status ? esc((TRANSFER[c.transfer_status] || [, c.transfer_status])[1]) : esc(c.callback_status || '')}</td></tr>`).join('');
  const seg = ['', 'red', 'amber', 'green'].map((l) => `<button aria-pressed="${S.callsLane === l}" data-act="callslane" data-lane="${l}">${l ? LANE[l] : 'All'}</button>`).join('');
  return header('All calls', 'Every call tonight, newest first. Click one for its Handoff Card.', `<div class="seg" role="group" aria-label="Lane">${seg}</div>`)
    + `<section class="card" style="overflow:hidden"><div style="overflow-x:auto"><table><thead><tr><th>Time</th><th>Lane</th><th>Caller</th><th>Why they called</th><th>Topic</th><th>Status</th></tr></thead><tbody>${rows || '<tr><td colspan="6" class="muted">No calls yet. Start a scenario from Demo controls.</td></tr>'}</tbody></table></div></section>`;
}

function donut(mix) {
  const tot = mix.red + mix.amber + mix.green;
  if (!tot) return '<div class="empty">No calls yet.</div>';
  const C = 2 * Math.PI * 62; let off = 0;
  const seg = (n, col) => { const len = (n / tot) * C; const s = `<circle cx="80" cy="80" r="62" fill="none" stroke="${col}" stroke-width="14" stroke-dasharray="${Math.max(0, len - 6)} ${C}" stroke-dashoffset="${-off}" stroke-linecap="round"/>`; off += len; return n ? s : ''; };
  return `<svg width="160" height="160" viewBox="0 0 160 160" role="img" aria-label="Lane mix: ${mix.red} now, ${mix.amber} a person soon, ${mix.green} can wait"><g transform="rotate(-90 80 80)">${seg(mix.green, '#74D47B')}${seg(mix.amber, '#D97706')}${seg(mix.red, '#DC2626')}</g>
    <text x="80" y="84" text-anchor="middle" font-size="30" font-weight="800" fill="#111827" font-family="Manrope">${tot}</text><text x="80" y="104" text-anchor="middle" font-size="12" fill="#6B7280" font-family="Manrope">calls</text></svg>`;
}

function viewAnalytics() {
  const a = S.data?.analytics; if (!a) return '';
  const card = (l, v, note) => `<section class="card kpi"><span class="l">${l}</span><span class="v tab">${v}</span><span class="muted" style="font-size:13px">${note}</span></section>`;
  return header('Analytics', 'Last 60 minutes. How the line, the rules and the model are doing.')
    + `<div class="row"><section class="card" style="flex:1 1 360px;padding:20px;display:flex;gap:24px;align-items:center;flex-wrap:wrap">${donut(a.lane_mix)}
      <div style="display:grid;grid-template-columns:auto 1fr auto;gap:10px 12px;align-items:center;font-size:14px;flex:1">
      <span style="width:14px;height:4px;border-radius:2px;background:#DC2626"></span><span>Now</span><b class="tab">${a.lane_mix.red}</b>
      <span style="width:14px;height:4px;border-radius:2px;background:#D97706"></span><span>A person soon</span><b class="tab">${a.lane_mix.amber}</b>
      <span style="width:14px;height:4px;border-radius:2px;background:#74D47B"></span><span>Can wait</span><b class="tab">${a.lane_mix.green}</b></div></section>
      <section class="accent kpi" style="flex:1 1 300px"><span class="l" style="color:#fff">Rules and model agree</span><span class="v tab">${pct(a.rules_model_agreement)}</span>
      <span style="font-size:13px;opacity:.95">${a.model_under_triage} calls where the model under-triaged and the rules raised the lane</span></section></div>
      <div class="row">${card('Red handoff, median', a.red_median_handoff_s == null ? '—' : a.red_median_handoff_s + ' s', 'red flag to transfer start · target 10 s')}
      ${card('Red callers told to call 911', pct(a.red_told_911_share), 'no nurse answered within 20 s')}
      ${card('Details confirmed', pct(a.detail_confirmation_rate), 'read back and confirmed from the transcript')}
      ${card('Hung up while waiting', pct(a.abandonment), 'falls when surge mode is on')}
      ${card('Rules misses', a.rules_miss, 'the model caught a red flag the rules missed')}</div>`;
}

function viewSetup() {
  const sg = S.data?.surge || {};
  const tpls = S.templates ? Object.entries(S.templates).map(([k, t]) => `<div class="cluster" style="grid-template-columns:1fr auto"><div><div class="nm">${esc(t.title)}</div><div class="muted" style="font-size:13px">${esc(t.text)}</div></div>
    ${sg.status_message === t.text ? '<span class="chip blue">Playing</span>' : `<button class="pill sm" data-act="usetpl" data-tpl="${k}">Activate</button>`}</div>`).join('') : '';
  const lines = S.nurse.map((n) => `<tr><td style="font-weight:700">${esc(n.label)}</td><td class="tab">${phone(n.number)}</td><td>${esc(n.role.replace('_', ' '))}</td><td class="tab">${n.priority}</td>
    <td><button class="toggle" aria-label="On duty: ${esc(n.label)}" aria-pressed="${!!n.on_duty}" data-act="duty" data-id="${n.id}" data-on="${n.on_duty ? 0 : 1}"></button></td></tr>`).join('');
  return header('Setup', 'Agreed on a calm day, so at 2 AM you approve instead of write.')
    + `<div class="row"><section class="card" style="flex:1.2 1 460px;min-width:0;overflow:hidden"><div class="card-h"><span class="ttl">Nurse lines for red transfers <span class="info">i</span></span></div>
      <table><thead><tr><th>Line</th><th>Number</th><th>Role</th><th>Priority</th><th>On duty</th></tr></thead><tbody>${lines}</tbody></table>
      <p class="muted" style="margin:0;padding:14px 20px;font-size:13px">The top on-duty line goes to Retell before each call through the inbound webhook. Changes apply from the next call.</p>
      <form id="addline" style="display:flex;flex-wrap:wrap;gap:10px;padding:0 20px 20px;align-items:flex-end"><label class="field" style="flex:1 1 180px">Label<input name="label" required placeholder="Night nurse · J. Park"></label>
      <label class="field" style="flex:1 1 150px">Number<input name="number" required placeholder="+12135550100"></label><label class="field" style="flex:0 1 90px">Priority<input name="priority" type="number" value="4"></label><button class="pill dark" type="submit">Add line</button></form></section>
      <section class="card" style="flex:1 1 420px;min-width:0;overflow:hidden"><div class="card-h"><span class="ttl">Status messages <span class="info">i</span></span><span class="grow"></span>${sg.status_message ? '<button class="pill sm" data-act="stopmsg">Stop current</button>' : ''}</div>${tpls}</section></div>
      <section class="card" style="padding:18px 20px;display:flex;flex-wrap:wrap;gap:24px;align-items:center"><div><div class="ttl">Surge mode</div><div class="muted" style="font-size:13px">Only a person can switch it on or off.</div></div>
      <button class="toggle" aria-label="Surge mode" aria-pressed="${!!sg.is_on}" data-act="surge" data-on="${sg.is_on ? 0 : 1}"></button>
      <div><div class="muted" style="font-size:13px">Routine callback window</div><b>${esc(sg.routine_window)}</b></div><div><div class="muted" style="font-size:13px">Priority callback window</div><b>${esc(sg.priority_window)}</b></div></section>`;
}

function viewDemo() {
  const sim = S.data?.sim || { scenarios: {} };
  const notes = { serious_earthquake: 'Collapsed buildings, regional outage. Volume ramps fast, so the surge prompt, the outage message and staffing suggestions fire on their own. Includes the chest-pain caller the model mislabels.',
    big_fire: 'Wildfire, evacuations, smoke. Breathing complaints are red flags even when they sound routine.', small_fire: 'Apartment fire, three patients. The system should not escalate: no surge prompt.',
    small_earthquake: 'Short spike, few red flags. Where "Not yet, ask in 2 min" earns its place.', tuesday: 'An ordinary night on the after-hours line: refills, rescheduling, one post-op bleed. The second customer.' };
  const cards = Object.entries(sim.scenarios).map(([k, l]) => `<section class="card" style="flex:1 1 300px;padding:20px;display:flex;flex-direction:column;gap:10px;${sim.scenario === k ? 'border-color:#1A87D6;background:#F5FAFE' : ''}">
    <div style="display:flex;align-items:center;gap:8px"><span class="ttl">${esc(l)}</span>${sim.scenario === k ? `<span class="chip blue">${sim.running ? 'Running · ' + sim.inserted + '/' + sim.total : 'Last run'}</span>` : ''}</div>
    <span class="muted" style="font-size:14px;line-height:1.5;flex:1">${esc(notes[k] || '')}</span><button class="pill ${sim.scenario === k && sim.running ? '' : 'dark'}" data-act="sim" data-scenario="${k}">${sim.scenario === k && sim.running ? 'Restart' : 'Start'} scenario</button></section>`).join('');
  return header('Demo controls', 'Team only. Simulated calls go straight into the database, so the board fills like a real night.',
    `<button class="pill" data-act="simstop">Pause drip</button><button class="pill" data-act="simreset">Reset board</button>`)
    + `<div class="row">${cards}</div><section class="card" style="padding:18px 20px;font-size:14px;line-height:1.6"><div class="ttl" style="margin-bottom:6px">Live phone calls</div>
    Point the Retell agent's webhook at <span class="tag">/retell/webhook</span> and the phone number's inbound webhook at <span class="tag">/retell/inbound</span>. Real calls appear on the board with a purple "Live call" chip, and the active status message and top on-duty nurse line go to Retell before each call.</section>`;
}

// ------------------------------------------------------------------ actions
document.addEventListener('click', async (e) => {
  const nav = e.target.closest('.side [data-view]');
  if (nav) { S.view = nav.dataset.view; if (S.view === 'setup') await loadSetup(); return poll(); }
  const el = e.target.closest('[data-act]'); if (!el) return;
  const { act, id } = el.dataset;
  try {
    if (act === 'open') { S.sel = id; S.detail = await api('/api/calls/' + encodeURIComponent(id)); render(); }
    else if (act === 'close') { S.sel = null; S.detail = null; render(); }
    else if (act === 'showred') { S.showAllRed = true; render(); return; }
    else if (act === 'brief') { S.brief = await api('/api/ic-brief'); render(); return; }
    else if (act === 'closebrief') { S.brief = null; render(); return; }
    else if (act === 'copybrief') { await navigator.clipboard.writeText(S.brief?.text || '').catch(() => {}); toast('Brief copied.'); return; }
    else if (act === 'sentbrief') { await api('/api/ic-brief/sent', { method: 'POST' }); S.brief = null; toast('Logged: brief sent to incident command.'); }
    else if (act === 'decide') {
      const body = { outcome: el.dataset.outcome || null };
      if (el.dataset.text) body.text = document.querySelector(`[data-edit="${id}"]`)?.value;
      await api(`/api/suggestions/${id}/${el.dataset.action}`, { method: 'POST', body });
      delete S.edits[id];
      toast({ accept: 'Done. Logged as your decision.', snooze: 'OK. I\'ll ask again in 2 minutes.', dismiss: 'Dismissed.', resolve: 'Alert closed and logged.' }[el.dataset.action]);
    }
    else if (act === 'surge') { await api('/api/surge', { method: 'POST', body: { on: el.dataset.on === '1' } }); toast(el.dataset.on === '1' ? 'Surge mode on.' : 'Surge mode off.'); }
    else if (act === 'stopmsg') { await api('/api/status-message', { method: 'POST', body: { text: null } }); toast('Status message stopped.'); }
    else if (act === 'usetpl') { const t = S.templates || (await api('/api/status-messages')).templates; S.templates = t;
      await api('/api/status-message', { method: 'POST', body: { text: t[el.dataset.tpl].text, cluster: el.dataset.tpl } }); toast('Status message now plays to every caller.'); }
    else if (act === 'cb') { await api(`/api/calls/${encodeURIComponent(id)}/callback`, { method: 'POST', body: { outcome: el.dataset.outcome } }); toast('Callback logged.'); }
    else if (act === 'lower') { const reason = prompt(`Why lower this caller to "${LANE[el.dataset.lane]}"? This is logged under your name.`); if (!reason) return;
      await api(`/api/calls/${encodeURIComponent(id)}/lane`, { method: 'POST', body: { lane: el.dataset.lane, reason } }); toast('Lane lowered and logged.'); }
    else if (act === 'callslane') { S.callsLane = el.dataset.lane; }
    else if (act === 'duty') { await api('/api/nurse-lines/' + id, { method: 'PATCH', body: { on_duty: el.dataset.on === '1' } }); await loadSetup(); }
    else if (act === 'sim') { S.sel = null; await api('/api/sim/start', { method: 'POST', body: { scenario: el.dataset.scenario, count: el.dataset.scenario === 'tuesday' ? 24 : 70 } }); S.view = 'board'; toast('Scenario started. Calls are arriving.'); }
    else if (act === 'simstop') { await api('/api/sim/stop', { method: 'POST' }); toast('Drip paused.'); }
    else if (act === 'simreset') { S.sel = null; await api('/api/sim/reset', { method: 'POST' }); toast('Board reset.'); }
  } catch (err) { toast(err.message); }
  poll();
});

document.addEventListener('input', (e) => {
  if (e.target.id === 'q') { S.q = e.target.value; const pos = e.target.selectionStart; $('#main').innerHTML = viewBoard(); const q = $('#q'); q.focus(); q.setSelectionRange(pos, pos); }
  if (e.target.dataset.edit) S.edits[e.target.dataset.edit] = e.target.value;
});
document.addEventListener('submit', async (e) => {
  if (e.target.id !== 'addline') return;
  e.preventDefault(); const f = new FormData(e.target);
  try { await api('/api/nurse-lines', { method: 'POST', body: { label: f.get('label'), number: f.get('number'), priority: Number(f.get('priority')) || 4 } }); await loadSetup(); toast('Nurse line added.'); poll(); }
  catch (err) { toast(err.message); }
});
document.addEventListener('keydown', (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); S.view = 'board'; render(); $('#q')?.focus(); }
  if (e.key === 'Escape' && (S.sel || S.brief)) { S.sel = null; S.detail = null; S.brief = null; render(); }
});
async function loadSetup() { S.nurse = await api('/api/nurse-lines'); S.templates = (await api('/api/status-messages')).templates; }

poll();
setInterval(poll, 1500);
