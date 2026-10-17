# On the Line: Hospital Call Triage — Research Report for a Retell AI Hackathon Build

The gentlest useful response for an overnight hospital line under surge is not "alert everyone" and not "send everything to a nurse." It is an AI first layer that **watches** for clusters, **asks** two or three red-flag questions on every call, **slows** demand with honest wait and callback messaging, **holds** non-urgent callers in a callback queue, and **hands** life-threatening, mental-health, and confused calls to a human right away with a written summary. Every piece of that design already works somewhere on an ordinary day. What nobody has built is a single "surge mode" that ties the pieces together.

## TL;DR

- **Hospitals already run AI voice agents for routine calls, and the gains are real.** Hyro's case study on Tampa General, which names the hospital's Chief Digital and Innovation Officer Scott Arnold, reports that daily call abandonment fell 56%, from 34% to 14.9%, within two weeks of go-live. Starlink says its Grok voice agent handles 15,000+ calls a day.\[1\] But no published deployment lets AI make clinical urgency decisions at night or during a surge. That gap is the opening for a build.
- **The "bang" options cost a lot and are well documented.** "Call 911 / go to the ER" pushes load onto 911 systems that themselves broke during the January 2025 Eaton Fire.\[2\] "Alert everyone" backfired on Jan 9, 2025, when a Kenneth Fire evacuation alert was "mistakenly issued to nearly 10 million L.A. County residents," according to LA County OEM Director Kevin McGowan (ABC7). "Send everything to the nurse" fails because at night there may be one house supervisor, and sometimes a security guard covering the switchboard.\[3\]
- **What to build:** a surge-aware intake layer with five rungs (watch → ask → slow → hold → hand off). It should use Schmitt-Thompson-style red-flag screening, cluster detection, and warm handoffs with an auto-summary, and it should be useful on a normal Tuesday (overflow, after-hours, scheduling peaks). It must disclose that it is AI under California AB 3030, and it must never decide on its own that a caller does not need care.

---

## 1. Current solutions: how hospitals handle inbound calls today

Most US hospitals use a layered stack. A phone system (PBX) and call routing (ACD) sit under an IVR phone tree. A centralized "patient access" contact center handles scheduling. A nurse advice/triage line runs on licensed protocols. An after-hours answering service or outsourced nurse triage covers the gaps. The hospital switchboard (PBX operators) handles everything else, including overhead codes.\[4\] AI voice agents are now being added on top of the contact center, mainly for scheduling, billing, and refills.\[5\]

| Layer | What it does | Named vendors/products (verified in this research unless noted) |
|---|---|---|
| Contact-center platform (CCaaS, ACD, IVR) | Queues, routing, IVR menus, callback | Genesys, Five9, Talkdesk, Avaya, Cisco, NICE (well-known category leaders; specific hospital contracts not verified here) |
| AI voice agents for patient access (scheduling, refills, transfers) | Natural-language front door, Epic scheduling | **Hyro** (Tampa General, "Amy");\[6\] **SoundHound/Amelia** (MUSC Health, "Emily", Epic-integrated, 24/7); **Assort Health** (specialty practices);\[7\] **PolyAI**, **Kore.ai**, **Luma Health Navigator** (vendor-listed Epic support)\[8\]\[9\]\[10\] |
| AI voice for billing | Balance questions, payment plans | **Cedar "Kora"** (~400,000 calls since April 2025);\[11\] **Retell AI** customer Medical Data Systems (collections)\[12\] |
| Clinical outreach agents (non-diagnostic) | Post-discharge, prep coaching, care gaps | **Hippocratic AI** (WellSpan "Ana"); excludes mental health, hospice, children under two\[13\]\[14\] |
| Developer voice platforms | Build-your-own agents | **Retell AI** (Pine Park Health, GiftHealth, Medical Data Systems, Doxy.me), Bland, Telnyx-based builders such as Hello Patient\[14\] |
| Nurse triage protocols/software | Telephone triage decision support | **Schmitt-Thompson Clinical Content**, delivered via ClearTriage, Keona Health CareDesk, TriageLogic, IntellaTriage\[15\]\[16\]\[17\]\[18\]\[19\] |
| Patient messaging AI (not voice) | Sorting portal messages by urgency | Providence **Provaria** (3M+ MyChart messages);\[20\] Epic GPT-drafted replies (UCLA pilot)\[21\] |
| Disaster/EMS communications | Hospital-to-EMS status, MCI | **ReddiNet** (owned by Hospital Association of Southern California), satellite phones, VMED28 radio\[22\]\[23\]\[24\] |

**Verified vs. not verified:** I confirmed the deployments named above (Hyro–Tampa General, SoundHound–MUSC, Hippocratic–WellSpan, Cedar, Retell's healthcare customers). Infinitus (payer-side calls), Notable, Qventus, Syllable and Artera are real healthcare automation vendors, but I did not verify their specific hospital call deployments in this research. Treat them as candidates to check, not confirmed examples.

## 2. Gaps still left to solve

The basic access problem is still unsolved, and it gets worse at night and during surges. Some data points:

- **Abandonment is far above target.** HFMA's goal is under 5% abandonment, and under 2% is leading practice for hospital scheduling. The 2024 HCCT survey puts the typical center at 5–6%.\[25\] Hyro's 2023 survey of 200 call-center leaders reports an average of **16%**, with 31% of respondents at 20–30%, an average hold of **4.4 minutes** against HFMA's 50-second goal, and **52%** first-call resolution.\[26\] *Conflict note:* the benchmarks vary because the samples differ (surveyed leaders vs. contact-center conferences). The 16% figure comes from a vendor that sells the fix.
- **Bad nights are extreme.** Before automation, Peninsula Orthopaedic Associates was abandoning more than 75% of calls, with holds of up to 90 minutes (vendor case study, Assort Health).\[7\]\[25\]
- **After-hours coverage.** Vendors claim large after-hours volumes ("41% of calls outside 8–5", agentzap, unsourced).\[27\] But Hyro's analysis of 300,000 AI-handled calls found **88.71%** came during office hours.\[26\] *The after-hours share is disputed.* It probably depends on whether the line has after-hours service at all. Unanswered calls get no data.
- **Surge, outage, and cyberattack call floods.** No vendor I found offers a documented "surge mode." During the 2024 CrowdStrike outage, some 911 centers could take voice calls while their computers were down (Congressional Research Service).\[28\] That is the same split-brain state a hospital line enters.
- **Urgency detection and safety.** No generative-AI voice agent product is FDA-cleared (cited via PMC in a vendor stats roundup).\[29\] Patients themselves misjudge urgency. In the Schmitt-Thompson Clinical Content study "Comparison of Pre-Call Patient Intent to Telehealth Triage Nurse Recommended Disposition" (7,504 calls; 73% adult, 27% pediatric), caller intent and nurse disposition showed "poor agreement (weighted Kappa 0.140)." Nurses recommended a *higher* level of care than the caller planned in **30.5%** of calls and a lower one in 28.3%, so "either a higher or lower level of care in approximately 6 of 10 encounters."
- **Language, accent, and speech access.** In late 2025, South Yorkshire GP practices using an AI receptionist had patients who could not make it understand regional accents or speech impediments, and some hung up (BBC, via Kore.ai).\[30\]
- **Context lost at handoff.** Most IVRs and answering services pass on a callback number, not a summary. Vendors such as Hyro now sell "contextual transfer" as a feature, which shows it is not standard.\[6\]
- **Staffing and workload on clinicians.** Kaiser advice nurses told The Markup/CalMatters (Oct 2026) they are pushed to keep calls short and scored by an AI tone-of-voice tool. One said "AI did not understand our job and would grade us wrong all the time."\[31\]\[32\]
- **Disclosure and trust.** Retell's own customer survey found a third of Pine Park Health patients did not realize they were talking to AI.\[33\] In California, that is a compliance risk for clinical content (see §10).

## 3. Who is calling hospitals

**Key data gap:** I found no primary US source giving a percent-of-volume breakdown of hospital call reasons. The best available evidence:

- **Hyro 2023 survey (share of call centers naming each a *top driver*, not share of calls):** billing and payments 52%, insurance 41%, prescription refills/medication 34%, complaints 28%, **emergency calls 28%**, referrals/authorizations 26%, internal help desk 24%, scheduling 23%, IT support 20%, clinic info 11%, general FAQs 11%.\[26\]
- **Older peer-reviewed primary-care data ("Telephone medicine," J Gen Intern Med):** symptoms/medical complaints **45%** of calls, test results **16%**, medication questions **14%**; mean call length 3.4 minutes.\[34\]
- **Volume:** Johns Hopkins Medicine gets about **3 million scheduling calls a year**; cutting volume by 3% saved $1.4M.\[35\] Tampa General's AI agent answered almost **half a million calls in about two months**.\[6\] Hyro estimates an average-size center (350 agents × ~75 calls) handles about **26,250 calls a day**.\[26\]

| Caller type | Typical reasons | Night/surge relevance (inference) |
|---|---|---|
| Patients | Scheduling, refills, test results, billing, symptoms, portal/password help | Bulk of daytime volume; symptom calls are the safety risk |
| Family members/caregivers | Patient condition/status, visiting hours, directions, "is my relative there?" | Spike sharply in disasters (reunification) |
| Referring physicians/clinics | Transfers, consults, paging specialists | Must reach a human (transfer center/operator) fast |
| EMS/fire | Diversion status, incoming patients | Mostly via ReddiNet/radio, but may hit main line when systems fail\[36\] |
| Pharmacies | Prescription clarifications | Routine; can wait for callback |
| Insurers/payers | Authorizations, claims | Daytime; deferrable |
| Vendors/suppliers | Deliveries, orders | Cedars-Sinai says its supply chain team got about 300 calls a day from nurses before an AI tool\[37\] |
| Staff | Sick calls, internal help desk, IT | 24% name internal help desk a top driver\[26\] |
| Media | Incident inquiries | Surge-only; route to PIO |
| Worried public | "Is the ER open?", "Are you affected by the outage/fire?" | The classic surge cluster |
| Misdirected emergencies | Chest pain, overdose, suicidal callers on the main line | 28% of centers list emergency calls as a top driver\[26\] |

## 4. How many phone numbers a hospital maintains

There is no national count. The one hard data point is striking. **Nemours Children's Health (Florida) had "over 75 phone numbers in use across the state, each with its own phone tree,"** and 96 prompt options. A survey of more than 400 families found they "overwhelmingly prefer a single phone number." Nemours cut prompts from 96 to 24, and abandonment fell from about 8% (2019) to about 3% (2020).\[38\]

LA examples show the same pattern. LA County DHS funnels patients to one number, **(844) 804-0055**, with options for new patients (1), the nurse advice line (2, 7am–7pm daily), the portal (3), billing (6), and specialty appointments (7).\[39\] Behind it sit separate facility main lines (LA General: (323) 409-1000), medical records, a subpoena desk, cashier offices, and clinic appointment lines.\[40\]\[41\]\[42\]

**Estimate (inference, not measured):** a single acute-care hospital typically publishes about 10–30 numbers (main switchboard, ED, admitting, scheduling, billing, medical records, pharmacy, patient relations, security, transfer center, major department lines). A multi-hospital system can publish 75 or more, plus hundreds of internal extensions and direct-dial patient-room phones.

## 5. Who picks up the phone

| Role | What they handle | Day vs. night |
|---|---|---|
| Switchboard/PBX operators | Main number, routing, overhead paging, emergency codes, alarms\[4\]\[43\]\[44\]\[45\] | 24/7 but thin at night; one job posting says a **security guard assumes the switchboard operator role on the midnight shift (12am–8am)**\[3\] |
| Patient access/scheduling reps | Appointments, referrals, registration | Mostly business hours; overflow goes to voicemail/answering service |
| Nurse triage RNs | Symptom calls via Schmitt-Thompson protocols\[15\]\[18\] | Often 24/7 in large systems (Kaiser SoCal 24/7 at 1-833-574-2273); LA DHS nurse line only 7am–7pm\[39\]\[46\] |
| Unit clerks/ward secretaries | Calls to inpatient units, family status questions | 24/7 but busy with admissions |
| ED registration/charge nurse | ED-directed calls | 24/7; cannot give phone medical advice to the public as a rule |
| Administrative/house supervisor | Escalations, staffing, incident command until leaders arrive | Often the single most senior person overnight |
| Answering services/outsourced nurse triage | After-hours clinic calls | Night/weekend backbone for clinics |
| Transfer center | Physician-to-physician transfers | 24/7 in larger hospitals |

**Takeaway:** at night, the "human" in "hand to a human" may be one stretched house supervisor or a security guard. That is why blind escalation fails.

## 6. The "bang" solutions and what they cost

The blunt moves the scenario warns against are real and documented.

- **"Call 911 / go to the ER."** This is the default line on many hospital IVRs and AI tools. Cedars-Sinai's AI Digital Assistant says "If this is an emergency, seek emergency care or call 911" and notes it is "not monitored in real time by a person."\[47\] It is a safe legal line, but in a surge it pushes load onto 911 and EDs. During the Eaton Fire, Derek Alconis, lead investigator at UL Research Institutes (ULRI), said at a news briefing reported by NBC News that "the speed and scale of the event overwhelmed the 911 system" and "calls came in faster than dispatch could manage or assign them."
- **"Alert everyone."** On Jan 9, 2025, a Kenneth Fire evacuation alert was "mistakenly issued to nearly 10 million L.A. County residents," according to LA County OEM Director Kevin McGowan (ABC7), and a correction did not follow until 22 minutes later (The Conversation). Mass alerting without verification causes panic and inbound call floods, and it erodes trust in the next alert.
- **"Send everything to a human."** At night that human is one supervisor, or a guard at the switchboard.\[3\] Everything waits, including the real emergencies.
- **What hospitals formally do:** activate **downtime procedures** (paper charts, manual workflows), the **Hospital Incident Command System (HICS)**, and command centers. After CrowdStrike (July 19, 2024), the AHA said affected hospitals "implemented downtime procedures," and Kaiser activated its national command center.\[48\]\[49\] Providence reported **51 hospitals** affected across its Southern California umbrella and western states.\[50\] Externally, LA hospitals use **ReddiNet** for diversion status, MCI patient counts, and an "open MCI victim list" kept for 72 hours, with satellite phones as backup.\[22\]\[36\] ReddiNet also has a Family Reunification Center module.\[23\]
- **Costs of blunt moves:** ambulance diversion and cancelled appointments (Prospect Medical's 2023 ransomware attack forced diversions and closures in the Northeast),\[51\]\[52\] lost revenue, staff burnout, and patients who give up. Vendor data claims 85% of patients do not call back after an unanswered first attempt (Keona Health, unverified).\[53\]

## 7. Softer solutions along the ladder

| Rung | Concrete option | Already exists? |
|---|---|---|
| **Watch** | Real-time cluster detection: spot a jump in calls with the same intent/keywords ("outage," "fire," "my bill," "is the ER open") and alert the supervisor with one summary instead of 200 calls | Not as a hospital product (gap); 911 vendors like Prepared market spike prediction\[54\] |
| **Watch** | Caller-history lookup (known patient? recent discharge? repeat caller in the last hour?) | Partially, via EHR-integrated agents |
| **Ask** | AI first layer asks 2–3 red-flag questions before anything else; any "yes" goes straight to a human or 911 guidance | Aurelian does this for 911 non-emergency lines\[54\]\[55\] |
| **Ask** | Ask one clarifying question instead of guessing when transcription confidence is low | Recommended practice (Kore.ai)\[30\] |
| **Slow** | Dynamic IVR/agent banner: "We know about the outage; your appointment tomorrow is still on; press 1 for callback" | Manual today; Prospect posted website banners only\[56\]\[57\] |
| **Slow** | SMS deflection with a status page link; proactive outbound text to affected patients | Outbound reminder tech exists (NEJM Catalyst: automated calls + SMS cut no-shows 11.3% → 9.6%)\[29\] |
| **Hold** | Virtual hold/callback queue ranked by urgency tier, not arrival order | Callback exists; urgency-ranked queues are rare |
| **Hold** | Starlink-style "schedule a callback with a human" | Live at Starlink\[58\] |
| **Hand to a person** | Warm transfer with an auto-summary (who, why, red-flag answers, transcript) | Hyro "contextual transfer"; Retell warm transfers\[6\]\[33\] |
| **Hand to a person** | Confidence threshold: low model confidence or caller distress triggers a human | Hippocratic samples 0.5–1% of live calls and escalates to nurses\[14\] |

## 8. Ways to triage a call

**Established clinical methods:**
- **Schmitt-Thompson Clinical Content (STCC):** the de facto US standard. ClearTriage, an STCC vendor, says "over 95% of medical triage call centers in North America use them" for "over 25 million calls a year"; Keona Health puts the share at "more than 90%." Adult and pediatric protocols run in office-hours and after-hours versions (e.g., 363 adult after-hours topics, 245 pediatric).\[17\] The nurse picks a symptom protocol and asks the highest-acuity questions first.\[59\] The first "yes" sets the **disposition**: Call 911 now → Go to ED now → See provider today/within 24h → Within 3 days → Home care.\[15\] Nurses may upgrade the disposition based on judgment.\[16\]\[59\]
- **ESI (Emergency Severity Index):** a 5-level ED triage scale. It is not a phone protocol, but its idea (life-saving intervention needed? how many resources?) maps onto urgency tiers.
- **911 dispatch protocols (MPDS/EMD):** scripted questioning that leads to a determinant code. This shows the value of fixed-order key questions. I did not independently verify current MPDS specifics in this research.
- **Red flags that end the AI conversation:** chest pain/pressure; trouble breathing; stroke signs (face droop, arm weakness, speech trouble); severe bleeding; unresponsiveness or fainting; seizure; suicidal or homicidal thoughts; overdose/poisoning; severe allergic reaction; pregnancy with bleeding or severe pain; infant under 3 months with fever; anaphylaxis; a caller who cannot speak or is in danger.

**Automated approaches:** keyword plus intent classification (Aurelian flags words like "bleeding" or "can't breathe" and transfers instantly);\[54\] tone/voice-stress cues (use with care: Kaiser's AI tone grading of nurses was widely criticized);\[32\]\[60\] EHR history lookup; duplicate/cluster detection; and confidence thresholds with human fallback.

**Must NEVER be automated (go straight to a human):**
1. Any red-flag symptom above. The AI's only job is to connect immediately, or give "hang up and call 911" if no human is reachable.
2. Suicidal ideation, self-harm, abuse, or violence (route to a clinician or the 988/crisis line; Kaiser's mental-health line is 1-800-900-3277).\[46\]
3. Any final decision that a caller does *not* need care (downgrades).
4. Calls about a child under two, hospice/end of life, and mental health. Hippocratic AI itself excludes these.\[14\]
5. Physician-to-physician transfers, EMS, and code/alarm calls.
6. Callers who ask for a human, sound confused or impaired, or whom the system cannot understand.
7. Death notifications, sensitive results, and patient condition disclosures to family (identity verification plus HIPAA).

## 9. Los Angeles specifics

| System | Publicly known call setup | AI for calls? | Notes/incidents |
|---|---|---|---|
| **Cedars-Sinai** | Main line used by consumers: 800-233-2771 (third-party listing)\[61\] | **AI Digital Assistant** (vendor-powered, "not monitored in real time," 911 disclaimer);\[47\] **CS Connect** app by K Health, expanded in 2025 to children and Spanish speakers;\[62\] internal **Chain Insights** agent replaced some of ~300 daily supply calls\[37\] | Hit by the July 2024 CrowdStrike outage but kept facilities open\[63\] |
| **UCLA Health** | 24/7 Patient Help Desk 855-364-7052; patient experience line 310-267-9113 (weekdays)\[64\]\[65\] | Website chatbot with open scheduling (award entry says it reduced call-center strain);\[66\] Epic GPT-4 draft-reply pilot (2023);\[21\] conversational agents in research for geriatric pre-visit assessment\[67\] | No public AI *voice* agent for inbound calls found |
| **LA County DHS (LA General, Harbor-UCLA, Olive View-UCLA)** | Single number (844) 804-0055 with options; nurse advice line **7am–7pm only**; LA General main (323) 409-1000\[39\]\[40\] | None found | Safety-net system; nights rely on EDs and 911 |
| **Kaiser Permanente SoCal** | 24/7 advice/appointments 1-833-574-2273; mental-health crisis 1-800-900-3277\[46\] | Uses AI in advice-nurse call centers to evaluate nurses (tone tool), per The Markup/CalMatters, Oct 2026; Kaiser declined to list its AI systems\[32\] | Activated its national command center during CrowdStrike\[48\] |
| **Providence SoCal (St. John's, Tarzana, Little Company of Mary, etc.)** | Not researched in detail | **Provaria** AI triages MyChart messages (3M+); 12 Epic AI tools via "Project Pixel"\[20\]\[68\] | CrowdStrike: "51 hospitals" affected across Southern California/West; restored by July 22\[50\]\[69\] |
| **Dignity Health (incl. California Hospital Medical Center)** | Not verified | Not found | Eight LA-area-region hospitals; some affected by CrowdStrike\[63\] |
| **Prospect Medical (e.g., Southern California Hospital at Hollywood)** | — | — | Aug 2023 Rhysida ransomware; CA sites posted outage notices but no specific CA service interruptions were reported; filed for bankruptcy Jan 2025\[57\]\[70\]\[71\] |
| **Keck Medicine of USC, CHLA, Good Samaritan** | CHLA main (323) 660-2450 and Good Samaritan (213) 977-2121 appear in a 2017 state EMS document (may be outdated)\[72\] | **Could not verify** any AI call deployments | Research gap |

**County context:** the LA County EMS Agency runs the Medical Alert Center (MAC, (562) 378-1789).\[24\] ReddiNet carries diversion status, MCI polling, and resource requests, with satellite phones as backup.\[22\]\[73\] During the January 2025 Eaton and Palisades fires, 911 was overwhelmed and evacuation alerts for west Altadena were delayed for hours. Separately, on Jan 9, 2025, a mistaken Kenneth Fire alert went to "nearly 10 million L.A. County residents" (LA County OEM Director Kevin McGowan, via ABC7). I found no public report specific to hospital phone lines during the fires. *That is a research gap, not evidence that nothing happened.*

## 10. Are hospitals using AI agents for calls right now?

**Yes, for administrative calls at scale. Clinical urgency calls are not among them.**

- **Tampa General + Hyro:** almost half a million calls since September 2025. Hyro's press release, which names TGH CDIO Scott Arnold, reports that "within two weeks of the initial go-live date" appointments rose 21% and daily call abandonment fell 56%, from 34% to 14.9%. Wait times dropped from 6.2 to 2.4 minutes. Use cases are scheduling, refills, billing, MyChart support, and contextual transfer.
- **WellSpan + Hippocratic AI ("Ana"):** nearly **2 million** patient conversations, Sept 2024–Sept 2025 (arXiv study). A sobering detail: in a colonoscopy-prep pilot, only **30.8%** of 1,627 patients completed full conversations.\[13\]
- **MUSC Health + SoundHound/Amelia ("Emily"):** 24/7 Epic-integrated appointment agent.\[10\]
- **Cedar Kora (billing):** about 400,000 calls; at Gastro Health, handle time −24% and staffing −22%.\[11\]
- **Retell AI healthcare:** Pine Park Health (senior primary care, CA/AZ/NV), scheduling NPS +38%, agents "Ava" and "Jay," with Retell co-designing the escalation logic;\[9\]\[74\] GiftHealth (pharmacy), 4x efficiency, about 50% of incoming calls automated;\[75\] Medical Data Systems, $280K/month collections;\[12\] Doxy.me, AI as first contact for free users.\[76\] Retell says it handles 100M+ calls a month across 4,000+ businesses (vendor claim).\[9\]
- **Failures/problems:** UK GP AI receptionist accent failures;\[30\] low completion rates in outreach;\[13\] Kaiser nurse backlash ("Trust nurses, not AI").\[77\]

**Regulation:**
- **California AB 3030** (in force Jan 1, 2025; Health & Safety Code §1339.79): if generative AI produces patient communications about *clinical information*, the communication must say it was AI-generated (for audio, **at the start and the end**) and tell patients how to reach a human. It is exempt if a licensed provider reviewed it.\[78\]\[79\]\[80\] **California AB 489** bars AI from implying it is a licensed clinician.\[80\]
- **California SB 1120 (2024)** requires physicians, not algorithms, to make medical-necessity decisions in health plan utilization review. It is relevant by analogy, not directly to call lines. *(Stated from background knowledge; not re-verified in this research.)*
- **FCC Declaratory Ruling FCC 24-17 (Feb 8, 2024):** AI-generated voices count as "artificial" under the TCPA. **Outbound** AI calls need prior express consent.\[81\]\[82\]\[83\]\[84\] Inbound answering is not a "robocall," but proactive outbound surge messaging is covered.\[84\]
- **HIPAA:** vendors must sign a BAA. Retell offers a self-service BAA on paid plans (vendor claim).\[9\] Identity verification is needed before disclosing any patient information.
- **FDA:** no generative-AI voice agent is FDA-cleared,\[29\] so systems that make triage decisions risk being treated as medical devices. Keep the AI as a router, not a diagnostician.

## 11. The SpaceX claim, verified

**Verdict: TRUE.** SpaceX's Starlink uses an AI voice agent (xAI/SpaceXAI's **Grok Voice**) on its customer support and sales phone line.\[1\]\[85\]

**Documented facts:**
- PCMag called Starlink support in April 2026 and reached an AI that said: *"Hi there, I'm an AI assistant powered by Grok."* It troubleshoots, takes orders, and **can schedule a callback with a human agent**. The line is 888-GO-STARLINK.\[58\]\[86\]
- Text-based Grok reportedly replaced Starlink's FAQ chatbot around January 2026 (secondary sources).\[87\]
- SpaceXAI, April 2026 (Grok Voice Think Fast 1.0): the Starlink phone agent **resolved 70% of support inquiries autonomously** with "no human in the loop," converted 20% of sales inquiries, and used **28 tools** across hundreds of workflows (troubleshooting, replacements, service credits).\[1\]\[87\]
- July 2026 (Think Fast 2.0): improved "intelligence, transcription and tool-use reliability"; A/B tests on the Starlink line showed higher containment. It became the default on Aug 5.\[1\]
- **Aug 24, 2026:** SpaceXAI posted that Grok Voice resolves "over 15,000 inbound customer support and sales calls a day" and "fulfills over 3,000 orders a week." **Elon Musk** reposted: "Grok Voice is used by Starlink at scale for support & sales."\[1\]
- Musk is quoted (via secondary coverage) saying AI is "infinitely patient, so you can yell at it, and it's still going to be very nice."\[58\]

**What could NOT be verified:**
- I could not access X/Twitter directly. The posts above come from news coverage (Benzinga/Yahoo Finance, PCMag via PiunikaWeb) and a search snippet of Sawyer Merritt's post.
- **I found no public posts by SpaceX/Starlink *engineers* describing problems** (latency, hallucinations, interruptions). I will not invent any. The only "problem" signal is customer reports that written support tickets take days, and allegedly up to three weeks (satelliteinternet.com, anecdotal).\[86\]

**Lessons that transfer to hospitals (inference):**
1. **Report containment honestly.** "70% resolved" means 30% still need humans. At hospital scale (26,000 calls/day for a big center), that is still thousands of human calls.
2. **The way out is a scheduled human callback.** That maps directly onto the "hold" rung.
3. **Self-identification works.** Starlink's agent says it is AI, which AB 3030 already requires for clinical content in California.
4. **Tools matter more than talk.** Starlink's value comes from 28 tool actions (ship replacement, credit).\[1\] Hospital value comes from EHR actions (book, refill request, page on-call).
5. **Transcription and tool reliability were the stated upgrade targets.** These are the same failure modes (mishearing, wrong action) that are dangerous in medicine.
6. **The stakes differ.** A wrong Starlink answer costs a dish. A wrong hospital answer can cost a life. So the hospital version must invert the default: escalate when unsure.

## 12. Lessons from other industries

- **911 non-emergency AI (Aurelian, Hyper, Prepared).** Aurelian launched in May 2024 and runs in Snohomish County (WA), Chattanooga (TN), Kalamazoo (MI, per TechCrunch), and other centers. Its Aug 27, 2025 BusinessWire release for its $14M Series A says it "now serves nearly 5 million Americans" and "automates an average of 74% of non-emergency calls, saving each dispatcher an average of three hours per day." It also says it sent **10,000+ emergent calls** that would have sat on hold over to 911.\[88\] Aurelian's own Y Combinator page claims "the average emergency communications center is 30% understaffed nationwide"; that is a vendor figure, not an independent statistic. Key design: listen for emergencies and transfer instantly, before trying to resolve anything.\[55\] Hyper raised $6.3M; Fairfax County, VA piloted AI on its non-emergency line.\[89\] Dispatcher unions and privacy advocates are watching closely.\[55\]
- **The Eaton Fire after-action** showed agencies losing track of crews and 911 being overwhelmed.\[2\] Surge failures are mostly *communication-coordination* failures, not just capacity.
- **Utilities and telecom (inference):** proactive outage messaging ("we know, here's the estimated restore time") is the standard way to keep call floods down. The hospital version is a dynamic IVR/AI banner plus a status page.
- **Monoculture risk (CrowdStrike):** when every hospital in a region runs the same software stack, neighbors cannot cover for each other.\[90\] A surge-mode AI layer should run on separate infrastructure from the EHR and keep working when Epic is down.

---

## Opportunities for a hackathon build

**Ladder mapping:**
- **Watch:** cluster detection across live calls; a per-intent surge meter; outage/incident hypothesis cards for the supervisor ("62 calls in 20 min mention 'portal down'").
- **Ask:** fixed-order red-flag screen on every call (AI-disclosed, AB 3030-compliant), then intent capture.
- **Slow:** a dynamic message that is truthful about the known issue, with an SMS status link and outbound texts only to consented patients (TCPA).
- **Hold:** an urgency-tiered callback queue with a promised callback window.
- **Hand to a person:** a warm transfer or page with a 3-line summary card. Escalation is triggered by any red flag, low confidence, a caller's request, or distress.

**Project ideas (each dual-use):**

1. **SurgeSense, the "watch" dashboard for the night supervisor.** It clusters call transcripts in near real time and raises one alert ("likely incident: MyChart outage, 48 callers, 0 red flags"). The supervisor gets one-tap actions: post a banner, start callbacks, page IT.
   *Second customer on an ordinary Tuesday:* the patient access center manager who wants to know why volume jumped at 9am (a confusing billing statement mailing, a broken portal login, a clinic that closed early).

2. **RedFlag Front Door, the "ask" layer (built on Retell).** A Retell agent answers overflow and after-hours calls, discloses it is AI, asks three red-flag questions modeled on Schmitt-Thompson's "highest-acuity first" logic, and transfers in under 10 seconds on any yes. Otherwise it captures intent.
   *Second customer:* a specialty clinic or small hospital that pays an answering service for nights and weekends (the Pine Park/Assort use case).

3. **Honest Hold, the "slow + hold" engine.** It gives a dynamic status message, offers an SMS link and a callback promise, and ranks the callback queue by urgency tier and caller vulnerability (age, recent discharge) instead of arrival order.
   *Second customer:* the Monday-morning scheduling peak, when Hyro's data shows abandonment can reach 34% without help.

4. **Handoff Card, the "hand to a person" layer.** Every escalated call arrives at the nurse, house supervisor, or switchboard with a structured summary: caller type, identity confidence, red-flag answers, intent, transcript link, and suggested STCC protocol. The receiving human never re-asks the basics.
   *Second customer:* nurse triage lines and transfer centers on any day, where context lost between IVR, agent, and nurse wastes minutes.

5. **Family Line, a reunification and status line.** During an MCI or fire it answers "Is my relative there?" by collecting the caller's details and the description of the person they are looking for, matching against the reunification list (ReddiNet FRC-style) for a *human* to call back.\[23\] It never discloses status itself.
   *Second customer:* the daily visitor-info line (hours, parking, directions, "which room is my mom in"), a large and low-risk share of switchboard calls.

**What must stay human (non-negotiable):** emergency and red-flag calls; mental-health crises; any downgrade of care; pediatric under-two, hospice, and end-of-life calls; disclosure of patient condition or results; physician, EMS, and code calls; and the final decision to declare an incident or send mass alerts. The AI can recommend; only a person presses "alert everyone."

## Caveats

- Many performance numbers (abandonment, containment, savings) come from **vendors**: Hyro, Assort, Retell, Cedar, Aurelian, SpaceXAI. They are directionally useful but not independently audited.
- There is **no primary data on hospital call mix by volume**. The caller table combines a survey of call drivers, an older primary-care study, and inference.
- The phone-number counts for a "typical hospital" are an **estimate**. Only Nemours (75+) is a hard data point.
- LA coverage is uneven: Keck, CHLA, Dignity CHMC, Good Samaritan, Harbor-UCLA and Olive View call operations and AI use **could not be verified**.
- Starlink figures are company claims relayed through news coverage. X posts were not accessed directly, and no engineer commentary on problems was found.
- SB 1120 and MPDS details are from background knowledge, not re-verified here. Source links are attached separately by the citation pass.

## Sources

1. [Elon Musk Says Grok Is Taking Over Starlink Support: 15,000+ Calls a Day, 3,000+ Orders a Week](https://finance.yahoo.com/technology/ai/articles/elon-musk-says-grok-taking-220058142.html)
2. [Poor communication marred emergency response to deadly L.A. area fires, report finds](https://www.nbcnews.com/news/us-news/los-angeles-fires-report-communication-failures-emergency-response-rcna601022)
3. [Hospital Switchboard Operator Jobs in Newark, NJ](https://www.ziprecruiter.com/Jobs/Hospital-Switchboard-Operator/-in-Newark,NJ)
4. [Switchboard Operator - Myworkdayjobs.com](https://bhs.wd1.myworkdayjobs.com/careers/job/corbin-ky/switchboard-operator_r26103453)
5. [14 AI Voice Agents for Healthcare to Automate Patient Calls](https://www.bland.ai/blog/ai-voice-agents-for-healthcare)
6. [How Tampa General Hospital and startup Hyro rolled out AI voice agents in 3 months](https://www.fiercehealthcare.com/ai-and-machine-learning/how-tampa-general-hospital-and-startup-hyro-rolled-out-ai-voice-agents-3)
7. [AI Voice Agents in Healthcare: How to Handle Patient Calls 24/7](https://www.assorthealth.com/blog/ai-voice-agent-in-healthcare)
8. [AI Voice Agents in Healthcare: Top Patient Scheduling Agents in 2026](https://thelevel.ai/blog/ai-voice-agents-for-patient-scheduling)
9. [10 Best AI Voice Agents for Healthcare in 2026](https://www.retellai.com/blog/ai-voice-agent-for-healthcare)
10. [SoundHound AI Announces Partnership With MUSC Health To Transform Patient Access With AI Agents](https://businesswire.com/news/home/20240828064869/en/SoundHound-AI-Announces-Partnership-With-MUSC-Health-To-Transform-Patient-Access-With-AI-Agents/)
11. [Cedar’s voice AI agent has handled nearly 400K patient calls since April 2025 launch](https://www.fiercehealthcare.com/ai-and-machine-learning/cedars-voice-ai-agent-has-handled-nearly-400k-patient-calls-april-2025)
12. [How MDS Collects \$280K Monthly Using AI Voice Agents](https://www.retellai.com/case-study/how-medical-data-systems-scales-280-000-in-monthly-collections-with-ai-voice-agents-on-retell)
13. [Perfecting Human-AI Interaction at Clinical Scale. Turning Production Signals into Safer, More Human Conversations](https://arxiv.org/pdf/2603.29893)
14. [11 AI Voice Agents for Healthcare, Compared for 2026](https://telnyx.com/resources/11-best-voice-ai-agents-healthcare)
15. [Simplifying Nurse Telephone Triage](https://www.proxet.com/blog/simplifying-nurse-telephone-triage)
16. [The 5 levels of Telephone Nurse Triage - TriageLogic: Remote Nurse Triage Software and Services](https://triagelogic.com/the-5-levels-of-telephone-nurse-triage/)
17. [STCC Guidelines: Improve Nurse Triage Decision-Making Today](https://keonahealth.com/stcc-page/)
18. [Phone Triage Using Schmitt-Thompson Protocols](https://intellatriage.com/blog/phone-triage-using-schmitt-thompson-protocols/)
19. [Telephone Triage: Implementing Nurse Protocols with ClearTriage](https://www.cleartriage.com/)
20. [Provaria: Transforming care with AI patient message management](https://blog.providence.org/blog/provaria-transforming-care-with-ai-patient-message-management)
21. [Automating Patient Communication with AI](https://it.uclahealth.org/automating-patient-communication-with-ai)
22. [County of Los Angeles Emergency Medical Services Agency Communication Plan](https://file.lacounty.gov/SDSInter/dhs/206683_Communication.pdf)
23. [LA COUNTY AMBULATORY SURGERY CENTER (ASC) DISASTER NEWSLETTER](https://file.lacounty.gov/SDSInter/dhs/1057825_ASCNewsletterApril2019-3rdedition.pdf)
24. [DEPARTMENT OF HEALTH SERVICES COUNTY OF LOS ANGELES SUBJECT:](https://file.lacounty.gov/SDSInter/dhs/1179861_1108ChempackDeploymentforNerveAgentRelease.pdf)
25. [Call Abandonment Rate in Healthcare: How to Improve It](https://www.assorthealth.com/blog/call-abandonment-rate-healthcare)
26. <https://assets-002.noviams.com/novi-file-uploads/pac/PDFs-and-Documents/Industry_Partners/Hyro_-_The_State_of_Healthcare_Call_Centers_2023_Report-fa539649.pdf>
27. [Medical Practice Phone Statistics: 15 Numbers Every Healthcare Provider Should Know](https://agentzap.ai/blog/medical-practice-phone-statistics)
28. [CrowdStrike IT Outage: Impacts to Public Safety Systems and Considerations for Congress](https://www.congress.gov/crs-product/IF12717)
29. [Healthcare AI Voice Agent Statistics 2026: Adoption, ROI & Patient Access](https://www.cloudtalk.io/blog/healthcare-ai-voice-agent-statistic/)
30. [Voice AI agents in healthcare: Top use-cases](https://www.kore.ai/blog/top-use-cases-for-voice-ai-agents-in-healthcare)
31. [Nurses say technology is making their jobs and patient care worse](https://krdo.com/stacker-news/2026/10/16/nurses-say-technology-is-making-their-jobs-and-patient-care-worse/)
32. [Nurses say technology is making their jobs and patient care worse](https://www.northwestsignal.net/news/article_381bb25b-eaea-57ed-a4c5-0a3e6e8cf819.html)
33. [Medical](https://www.retellai.com/go/medical)
34. [Telephone medicine](https://link.springer.com/article/10.1007/BF02600541)
35. [Modernize Healthcare Contact Centers for Staff and Patients](https://healthtechmagazine.net/article/2025/11/modernize-healthcare-contact-centers-staff-and-patients)
36. [DEPARTMENT OF HEALTH SERVICES COUNTY OF LOS ANGELES (EMT, PARAMEDIC, MICN)](https://file.lacounty.gov/SDSInter/dhs/206267_5194-15-15.pdf)
37. [Cedars-Sinai Employees Harness AI to Create a Culture of Innovation](https://www.newswise.com/articles/cedars-sinai-employees-harness-ai-to-create-a-culture-of-innovation)
38. [Don’t Overlook Your Hospital’s Phone System](https://www.childrenshospitals.org/news/childrens-hospitals-today/2021/02/dont-overlook-your-hospitals-phone-system)
39. [Contact Us - Health Services Los Angeles County](https://dhs.lacounty.gov/contact-us/)
40. [Patient Services - LA General Medical Center](https://dhs.lacounty.gov/lageneral/our-services/patient-services/)
41. [Patient and Visitor Information - High Desert Regional Health Center](https://dhs.lacounty.gov/highdesert/patient-and-visitor-information/)
42. [Contact Us - Health Care Centers](https://dhs.lacounty.gov/health-care-centers/patient-information/records-and-forms/medical-record-request/contact-us/)
43. [Switchboard Operator - PRN in Sylva, NC](https://jobs.lifepointhealth.net/job/switchboard-operator-prn/sylva-nc/344303/)
44. [\$12-\$17/hr Hospital Switchboard Operator Jobs in Georgia](https://www.ziprecruiter.com/Jobs/Hospital-Switchboard-Operator/--in-Georgia)
45. [Switchboard Operator - Careers at Beth Israel Lahey Health](https://jobs.bilh.org/jobs/switchboard-operator-plymouth-ma-jr90666/)
46. [How to Find Care in Southern California](https://healthy.kaiserpermanente.org/southern-california/get-care)
47. [Digital Assistant - iOS](https://www.cedars-sinai.org/digital-assistant/ios.html)
48. [Tips for covering the aftermath of the CrowdStrike outage](https://healthjournalism.org/blog/2024/07/tips-for-covering-the-aftermath-of-the-crowdstrike-outage/)
49. [CrowdStrike technology outage causing global disruption across industries, including impacts on hospitals and health systems](https://www.aha.org/news/headline/2024-07-19-crowdstrike-technology-outage-causing-global-disruption-across-industries-including-impacts-hospitals)
50. [CrowdStrike and Microsoft respond to global IT outage that hit airlines, banks, hospitals](https://www.nbcnews.com/news/world/live-blog/live-updates-it-outage-flights-banks-businesses-microsoft-crowdstrike-rcna162669)
51. [Multi-hospital ransom attack in US claimed by Rhysida gang](https://cybernews.com/security/prospect-medical-holdings-ransom-attack-rhysida-gang/)
52. [Prospect Medical hospitals still recovering from ransomware attack](https://therecord.media/prospect-hospitals-still-recovering)
53. [Reduce Missed Calls & Boost ROI in Healthcare Centers](https://keonahealth.com/resources/missed-calls-healthcare-call-abandonment-roi/)
54. [AI Steps In to Support Understaffed 911 Centers Handling...](https://blog.getrentacar.com/ai-assisted-emergency-call-triage)
55. [AI 911 call centres stir debate amid staffing crisis](https://allaboutartificial.com/ai-911-call-centres/)
56. [Prospect Medical Holdings Suffers Cyberattack](https://drivestrike.com/prospect-medical-holdings-suffers-cyberattack/)
57. [Ongoing cyberattack on 16-hospital Prospect Medical interrupts services](https://www.fiercehealthcare.com/providers/ongoing-cyberattack-prospect-medical-holdings-forces-facilities-offline-disrupts-services)
58. [Grok-powered voice assistant is handling Starlink customer support calls at SpaceX](https://piunikaweb.com/2026/04/15/spacex-grok-voice-ai-starlink-customer-support/)
59. [Office-Hours Telehealth Triage Protocols User's Guide 2026](https://www.cleartriage.com/wp-content/uploads/STCC-OH-Users-Guide.pdf)
60. [Nurses say technology is making their jobs and patient care worse](https://www.rrdailyherald.com/news/national/nurses-say-technology-is-making-their-jobs-and-patient-care-worse/article_e10b7f6a-2b1e-58cc-9dd9-6b138f6f109f.html)
61. [Cedars - Sinai Medical Center Customer Service Phone Number 800-233-2771: Call Support](https://gethuman.com/phone-number/Cedars-Sinai-Medical-Center)
62. [Cedars-Sinai Strengthens AI Foundation for Strategic Growth](https://www.cedars-sinai.org/newsroom/cedars-sinai-strengthens-ai-foundation-accelerates-momentum/)
63. [Southern California hospitals impacted by worldwide software outage](https://www.cbsnews.com/amp/losangeles/news/southern-california-hospitals-impacted-by-worldwide-software-outage)
64. [Patient Experience](https://www.uclahealth.org/patient-resources/prepare-your-visit/patients/patient-experience)
65. [Online Medical Chart & Patient Portal - myUCLAhealth](https://www.uclahealth.org/patient-resources/myuclahealth)
66. [BEST USE OF ARTIFICIAL INTELLIGENCE IN ...](https://www.uclahealth.org/sites/default/files/documents/21/2022-uclah-ehealthcare-artificial-intelligence.pdf?f=bb1a7b0d)
67. [Thoughtfully incorporating AI into UCLA Health](https://www.uclahealth.org/news/article/thoughtfully-incorporating-ai-ucla-health)
68. [Providence Deploys 12 Epic AI Tools - DistilINFO Publications](https://distilinfo.com/2026/04/27/providence-deploys-12-epic-ai-tools/)
69. [Hospitals work through fallout from CrowdStrike outage](https://nutilelaw.com/hospitals-work-through-fallout-from-crowdstrike-outage/)
70. [Rhysida claims ransomware attack on Prospect Medical, threatens to sell data](https://www.bleepingcomputer.com/news/security/rhysida-claims-ransomware-attack-on-prospect-medical-threatens-to-sell-data/)
71. [Prospect Medical Holdings](https://en.wikipedia.org/wiki/Prospect_Medical_Holdings)
72. [Los Angeles County EMS Agency Agency Contact](https://emsa.ca.gov/wp-content/uploads/sites/71/2017/07/LosAngelesCountyEMSAgency.pdf)
73. [DEPARTMENT OF HEALTH SERVICES COUNTY OF LOS ANGELES (HEALTHCARE FACILITIES,](http://file.lacounty.gov/dhs/cms1_206177.pdf)
74. [Retell AI](https://www.retellai.com/case-study/how-pine-park-health-elevates-senior-care-with-intelligent-voice-automation)
75. [GiftHealth: 4x Operational Efficiency](https://www.retellai.com/case-study/how-gifthealth-achieved-4x-operational-efficiency-with-retell-ai)
76. [5 Useful AI Agent Case Studies, and What We Learned from Them](https://www.retellai.com/blog/5-useful-ai-agent-case-studies-and-what-we-learned-from-them)
77. [Nurses say technology is making their jobs and patient care worse](https://kioncentralcoast.com/stacker-news/2026/10/16/nurses-say-technology-is-making-their-jobs-and-patient-care-worse/)
78. [Duane Morris LLP - California Passes Novel Law Governing Generative AI in Healthcare](https://www.duanemorris.com/alerts/california_passes_novel_law_governing_generative_ai_healthcare_1224.html)
79. [California Enacts AB 3030: Transparency Rules for AI-Generated Patient Communications - Lengea](https://lengealaw.com/california-ab-3030-ai-patient-communications/)
80. [AB 3030 Healthcare Disclosure Mandates Explained (2026)](https://californiacompliancegroup.com/articles/ab-3030-healthcare-disclosure-mandates)
81. [FCC Issues Declaratory Ruling on AI-Generated Voice Robocalls](https://www.akingump.com/en/insights/ai-law-and-regulation-tracker/fcc-issues-declaratory-ruling-on-ai-generated-voice-robocalls)
82. [FCC Rules AI-Generated Voices Are “Artificial” Under the TCPA](https://www.wsgr.com/en/insights/fcc-rules-ai-generated-voices-are-artificial-under-the-tcpa.html)
83. [The FCC Did Not Ban All AI Robocalls - Elias Law](https://elias.law/client-alert/the-fcc-did-not-ban-all-ai-robocalls/)
84. [FCC Requires Consent for AI-Generated Cloned Voice Calls](https://www.mcdermottlaw.com/insights/fcc-requires-consent-for-ai-generated-cloned-voice-calls/)
85. [Sawyer Merritt on X: "SpaceX is now using a voice-based AI assistant to answer Starlink customer support calls. The result will put you in touch with a voice that sounds like a human, but is actually Grok. It can converse with you in real time to answer sales-related questions and troubleshoot" / X](https://x.com/SawyerMerritt/status/2043802223688200383?lang=en)
86. [How to Contact Starlink Customer Service: AI Grok Added to Support (2026)](https://www.satelliteinternet.com/providers/starlink/customer-service/)
87. [Grok Voice Is Now Running Starlink's Customer Support](https://www.basenor.com/blogs/news/grok-voice-is-now-running-starlinks-customer-support)
88. [ycombinator.com](https://ycombinator.com/companies/aurelian)
89. [AI Eases 911 Understaffing by Handling Non-Emergency Calls](https://www.webpronews.com/ai-eases-911-understaffing-by-handling-non-emergency-calls/)
90. [Consequences of Compliance: The CrowdStrike Outage of 19 July 2024](https://www.usenix.org/publications/loginonline/consequences-compliance-crowdstrike-outage-19-july-2024)
