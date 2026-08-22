# 🗓️ Cadd-Scheduler — Agentic Meeting Negotiation, Native to Slack & Teams

> Stop scheduling. Just @mention the bot.
> An agentic system that finds a meeting slot across a team, negotiates around conflicts person-by-person inside Slack/Teams DMs, and locks a final Google Meet — with zero email back-and-forth.

---

## The Problem

Scheduling a meeting with 4+ people is still "reply-all with your availability." Existing tools (Clara, Calendly, Reclaim) either automate the *first* proposal and dump the rest on email, or require everyone to open a booking page. Nobody negotiates conflicts *for* you, in the tool your team already lives in.

## The Idea

1. Someone @mentions the bot in a Slack/Teams channel: `@cadd schedule with @alex @jordan @sam next week`
2. Agents check everyone's calendar and propose a slot
3. Each person gets a **DM** with an interactive card — Accept / Suggest another time — not an email
4. If someone conflicts, a **Negotiation Agent** works that person 1:1 in their DM until they land on something that still works for everyone else
5. Once consensus is reached: Google Meet is created, the channel thread is updated, and *only then* does a calendar invite go out by email (because .ics invites are inherently email — that's fine, it's just the receipt, not the negotiation)

---

## Why AWS + Bedrock AgentCore (not just a bare CrewAI, LangGraph, Strands, or plain-code script)

[Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/) is AWS's managed platform for running production agents — it handles session isolation, memory, tool access, and observability so the project isn't "a Python script that happens to call an LLM," it's a real deployable multi-agent system. AgentCore is framework-agnostic (works with CrewAI, LangGraph, Strands, or plain code), so the agent logic itself can stay simple while AgentCore handles the production-grade plumbing.

| Need | AgentCore / AWS Service |
|---|---|
| Host & run each agent | **AgentCore Runtime** — session-isolated, up to 8-hour long-running executions per negotiation |
| Give agents tool access (Slack API, Google Calendar, Outlook, Teams) | **AgentCore Gateway** — exposes these as MCP tools instead of hand-rolled API glue |
| Let agents act on each user's behalf securely | **AgentCore Identity** — OAuth vault for Slack/Google/Microsoft tokens, per-user scoping |
| Remember negotiation history & preferences | **AgentCore Memory** — session + long-term memory per meeting/person |
| Trace & debug multi-agent runs | **AgentCore Observability** | 
| Model | **Bedrock (Llama 4, Mistral or DeepSeek)** — swap models without rebuilding the agent |
| Negotiation state machine | **Step Functions** — Proposed → Collecting Responses → Renegotiating → Locked, with round caps & human escalation |
| Per-meeting/session state | **DynamoDB** |
| Async fan-out to individual DMs | **SQS + Lambda** |
| Slack/Teams webhook ingress | **API Gateway + Lambda** |
| Final calendar invite | **SES** (only, not for negotiation) |
| Nudges / timeouts | **EventBridge Scheduler** |
| Auth for the web dashboard | **Cognito** |
| Frontend hosting | **Amplify** or **S3 + CloudFront** |

---

## Architecture

```
Slack / Teams
     │  (@mention, DM button click)
     ▼
API Gateway ──► Lambda (webhook verify) ──► SQS
                                              │
                                              ▼
                                   AgentCore Runtime
        ┌──────────────┬──────────────┬───────────────┬──────────────┐
        │ Orchestrator │ Availability │  Negotiation   │  Consensus  │
        │    Agent     │    Agent     │     Agent      │    Agent    │
        └──────┬───────┴──────┬───────┴───────┬────────┴──────┬──────┘
               │              │               │               │
               ▼              ▼               ▼               ▼
        Step Functions   Google/Outlook    Slack/Teams      DynamoDB
        (state machine)   Calendar API      DM + Cards     (round tracking)
               │              │                │               │
               └──────────────┴───────┬────────┴───────────────┘
                                      │
                                      ▼
                        ┌───────────────────────────────┐
                        │   Join: wait for all 4 agents │
                        │  Proceeds only if all succeed │
                        └───────────────┬───────────────┘
                                        │
                                        ▼
                        ┌──────────────┬──────────────┐
                        │  Meet Agent  │Notifier Agent│
                        └──────┬───────┴──────┬───────┘
                               ▼              ▼
                        Google Meet API      SES (.ics invite) + Slack/Teams thread update
```

---

## Negotiation State Machine

```
PROPOSED
   │
   ▼
COLLECTING_RESPONSES  (DM cards sent, tracking accept/decline per person)
   │
   ├── all accept ─────────────────► LOCKING ─► Meet created ─► DONE
   │
   └── someone declines
          │
          ▼
   Negotiation Agent DMs that person 1:1 for their free windows
          │
          ▼
   Availability Agent re-checks against everyone else's calendars
          │
          ▼
   New candidate slot ─► back to COLLECTING_RESPONSES
   (round counter++; after N rounds ─► escalate to organizer via DM)
```

---

## Tech Stack

### Language & Core
- **Python 3.12+** — agent logic, Lambda handlers
- **boto3 / AWS SDK for Python** — all AWS service calls
- **Pydantic** — request/response & tool schemas
- **TypeScript + React** — frontend dashboard

### AWS Bedrock AgentCore (agent runtime layer)
- **AgentCore Runtime** — hosts & executes each agent, session-isolated, long-running (up to 8h) negotiation sessions
- **AgentCore Gateway** — exposes Slack/Teams/Calendar APIs as MCP tools for agents, instead of hand-rolled integrations
- **AgentCore Identity** — OAuth vault for per-user Slack/Google/Microsoft tokens; agents act on a user's behalf securely
- **AgentCore Memory** — session memory (current negotiation) + long-term memory (a person's recurring preferences, e.g. "never before 10am")
- **AgentCore Observability** — traces & metrics for every multi-agent run
- **AgentCore Evaluations** — regression-test agent behavior in CI before shipping changes
- **Amazon Bedrock (Claude models)** — the LLM backing every agent

### Orchestration & Data
- **AWS Step Functions** — the negotiation state machine (Proposed → Collecting → Renegotiating → Locked)
- **Amazon DynamoDB** — meeting/session state, negotiation round tracking, Slack↔email↔calendar identity mapping
- **AWS Lambda** — webhook handlers, async fan-out workers
- **Amazon SQS** — decouples "person declined" events from the Lambda that re-runs negotiation for just that person
- **Amazon EventBridge Scheduler** — timeouts, nudges, follow-ups

### Integrations
- **Slack Bolt SDK (Python)** — bot, slash commands, Block Kit interactive DM cards, OAuth install
- **Microsoft Bot Framework SDK** — Teams bot, Adaptive Cards (Teams needs Azure Bot Framework registration for two-way interactivity, even with AWS-hosted logic)
- **Google Calendar API + Google Meet API** — free/busy lookup, meeting creation
- **Microsoft Graph API** — Outlook Calendar free/busy, Teams meeting creation

### Ingress, Auth & Delivery
- **Amazon API Gateway** — Slack/Teams webhook + interactivity endpoints
- **Amazon Cognito** — auth for the web dashboard
- **Amazon SES** — final `.ics` calendar invite email (not used for negotiation)

### Frontend & Hosting
- **AWS Amplify** or **S3 + CloudFront** — dashboard hosting

### Infra & Delivery
- **AWS CDK (Python)** — all infrastructure as code
- **GitHub Actions** — CI/CD: tests, AgentCore Evaluations, CDK deploy
- **pytest** — unit/integration tests for agent logic

---

## Repo Structure

```

cadd-scheduler-agent/
├── backend/                    # FastAPI app — agents, API, Slack/Teams/Calendar integrations
|
├── infra/                      # AWS CDK — AgentCore, Step Functions, DynamoDB, Lambda,
|                               # API Gateway, Cognito, SES, EventBridge
|                            
├── frontend/                   # React dashboard — meeting history, org settings
│
└── docs/
    ├── architecture.md
    └── negotiation-state-machine.md
```

---
## Status

🚧 **Actively building** — Slack slash-command surface accepts natural-language commands end-to-end (`@mention` attendees + spoken meeting times); Strands adopted as the agent framework; full agent booking pipeline live — orchestrator chains three tools (availability check → free slot finder → meeting creation) against real Workspace calendars with a single `/cadd` command.

**What's working end-to-end today:**
- AgentCore Identity USER_FEDERATION OAuth flow with session binding
- Real Google Calendar free/busy queries via vault-sourced credentials
- Real meeting creation with Google Meet links, delivered to attendee inboxes
- DynamoDB-backed user model (Slack ↔ email ↔ AgentCore user_id mapping)
- DynamoDB-backed pending sessions with TTL for concurrent-onboarding safety
- Slack app installed with `users:read.email` scope; email lookup verified
- `OnboardingService` — single entry point mapping `slack_user_id` → Google credentials
- Success DM to the Slack user on OAuth completion
- **`/slack/commands` webhook — signature-verified, wired to onboarding + calendar scheduling**
- **Slack HMAC-SHA256 signature verification (`SlackSignatureVerifier`), rejecting stale or forged requests**
- **Callback server merged into the main FastAPI app — single port, single ngrok tunnel**
- **Background-task pattern for Slack responses — acknowledges within Slack's 3s window, delivers real results (auth link or meeting confirmation) via DM**
- **Verified live through real Slack + ngrok + AgentCore + Google Calendar, for both a fresh unauthorized user and an already-authorized user**
- **`@mention` attendee parsing — resolves Slack mentions to emails via escape-encoded `<@ID>` tokens (multiple attendees supported)**
- **Natural-language meeting-time parsing via Bedrock (Converse API) — handles single times, stated durations, and explicit ranges; timezone-aware**
- **Both Session-5 hardcoded placeholders (attendees, meeting time) fully removed**
- **Conflict detection — checks all attendees' calendars before booking; blocks meeting creation if anyone is busy**
- **Free slot finder (`find_free_slots`) — merges busy blocks across all attendees, returns gaps within org working hours (5:30 PM – 2:30 AM IST)**
- **Friendly conflict message in Slack — shows who is busy, lists up to 3 alternative slots in IST**
- **`get_display_name` added to `SlackUserInfoProvider` — shows attendee names not emails in conflict messages**
- **Logging infrastructure (`core/logging.py`) — structured timestamps across all modules**
- **Time parser timezone fix — returns user's timezone offset (IST) not UTC**
- **Block Kit interactive buttons — conflict message now shows tappable slot buttons instead of plain text**
- **`/slack/actions` route — signature-verified endpoint receives button clicks and books meetings**
- **Full two-turn flow — `/cadd` command → conflict detected → buttons → user taps → real meeting booked with Google Meet link**
- **Midnight-crossing working hours fix — correctly identifies free windows for shifts spanning two calendar days**
- **`@mention` renders as tappable Slack mention in conflict messages instead of plain display name**
- **Strands adopted as the agent framework** — chosen over LangGraph and CrewAI because Step Functions owns the state machine (LangGraph's core value redundant), AgentCore Runtime is a hard requirement (Strands has first-class integration), and existing codebase philosophy ("seal non-determinism at boundaries") maps cleanly onto Strands' model-driven, tools-as-primitives approach
- **Two Strands tools wrapped and verified live** — `find_free_slots_tool` (thin adapter over the Session 7 pure function) and `get_availability_tool` (factory pattern that closes over per-user Google credentials from AgentCore Identity)
- **Orchestrator agent** — `build_agent(creds)` factory produces per-request Strands `Agent` instances with both tools available; LLM chains the tools end-to-end (get_availability → find_free_slots) via docstring-guided reasoning, no glue code
- **Verified against real Workspace calendars** — orchestrator correctly detects Ashwin's real busy blocks and proposes non-conflicting 30-minute meeting windows, matching the behavior of the existing hand-wired `/cadd` flow but without any imperative control flow
- **Existing `webhooks.py` untouched** — Sessions 1–8 code path still ships; agent path lives side-by-side, ready to be feature-flagged in the next session
- **`create_meeting_tool`** — third Strands tool wrapping `GoogleCalendarProvider.create_meeting`; factory pattern matching `get_availability_tool`; returns `{"join_url", "event_id"}` on success, `{"error": ...}` on failure; docstring guards against speculative booking
- **Orchestrator wired into `webhooks.py` behind `use_agent` feature flag** — `USE_AGENT=true` routes `/cadd` through the Strands agent; existing hand-wired path untouched and default; agent receives concrete ISO times and resolved emails, not raw text
- **Full agent booking pipeline verified live** — three-tool chain (get_availability → find_free_slots_tool → create_meeting) correctly detected Ashwin's busy block, found the next free window at or after the requested time, and booked a real Google Meet; confirmed in Google Calendar UI
- **`OrgProfile` + `Shift` models** — working hours moved out of hardcoded literals into pydantic models; `Shift.working_window()` owns the midnight-crossing arithmetic that was duplicated inline in `webhooks.py`; hours live on `Shift` rather than `OrgProfile` because one org can run several shifts
- **First unit tests** — `backend/tests/` with pytest, covering `working_window`'s three branches (non-crossing, crossing before midnight, crossing after midnight); previously all testing was manual smoke scripts against live services
- **Slot buttons book the requested duration** — buttons previously carried the whole free gap as the meeting, so a "12:45 AM–02:30 AM" button booked a 1h45m meeting instead of 30 minutes
- **Conflict check filtered to the requested window** — restored the interval-overlap test; without it any busy block anywhere in the 9-hour working day flagged a conflict even when the asked-for slot was free
- **Conflict messages show the date** — time-only formatting made wrong-day bookings invisible


**What's next:**
- Remaining agents in the crew: Negotiation agent (DMs a conflicting attendee 1:1, collects their free windows), Consensus agent (checks a proposed slot works for everyone remaining)
- Step Functions negotiation state machine — Proposed → Collecting → Renegotiating → Locked, with round caps and organizer escalation
- `login_hint` + `hd` param on auth URL — prevents wrong Google account during OAuth (deferred since Session 7, low effort, high correctness value)
- AgentCore Runtime deployment — local Bedrock is enough today; deploy after the multi-agent crew is proven locally
- `asyncio.to_thread` wrap — Bedrock and Google calls are sync inside async handlers; fix in one pass when it matters
- Relative date resolution moved into Python — Bedrock currently computes "coming monday" itself and gets it wrong; the model should identify the phrase, `OrgProfile` should compute the date

## Roadmap

**Foundations (done)**
- [x] AgentCore Identity USER_FEDERATION OAuth pipeline
- [x] Google Calendar + Google Meet integration
- [x] `UserCredentialsLookup` abstraction with AgentCore-backed implementation
- [x] `User` model + `UserRepository` (DynamoDB)
- [x] `PendingSession` model + `PendingSessionRepository` (DynamoDB, TTL, atomic pop)
- [x] Centralized config via pydantic Settings
- [x] Slack app registered with `users:read.email` scope verified

**Onboarding wiring (done)**
- [x] Callback server migrated from `.agentcore.json` to `PendingSessionRepository`
- [x] `SlackUserInfoProvider` for `slack_user_id → email` lookup
- [x] `OnboardingService` — the glue between Slack, User model, and AgentCore
- [x] Success DM to Slack user on OAuth completion

**Slack surface (done)**
- [x] Slash command `/cadd` — event handler, HMAC signature verification
- [x] Slash-command-triggered end-to-end meeting scheduling (onboarding + calendar)
- [x] Background-task response pattern to stay within Slack's 3s window
- [x] `@mention` attendee parsing (replacing hardcoded test attendee)
- [x] Natural-language meeting time parsing (Bedrock Converse — single time, duration, range; timezone-aware)
- [x] Conflict detection with free-slot alternatives (working hours scoped)
- [x] Organizer-side slot selection via Block Kit buttons
- [ ] DM-based negotiation cards (pick a time, propose alternative, confirm)

**Agent crew**
- [x] Framework decision — Strands (see What's working)
- [x] Orchestrator agent scaffolded with `get_availability` + `find_free_slots` tools
- [x] `create_meeting_tool` + orchestrator wired into `webhooks.py`
- [ ] Remaining crew members: Negotiation, Consensus, Meet, Notifier
- [ ] Step Functions negotiation state machine
- [ ] AgentCore Runtime deployment

**Multi-platform parity**
- [ ] Microsoft Teams (Bot Framework)
- [ ] Outlook Calendar integration

**Production readiness**
- [ ] ~~Callback server on Lambda + Function URL (retire ngrok)~~ → callback server merged into main app; still needs Lambda migration to retire ngrok entirely
- [ ] Real DynamoDB (retire DynamoDB Local for prod)
- [ ] Infrastructure-as-code (CDK) — workload identity, credential provider, tables, Lambda
- [ ] Organizer escalation flow after N failed negotiation rounds
- [ ] Web dashboard (meeting history, team settings)