# Architecture

How cadd is structured, what exists today, and where new work goes.

The README describes the product. This describes the system. Where they disagree, this file is the accurate one — see [Honest status](#honest-status).

---

## The shape

A request moves through five layers. Each one has a single job and hands a well-formed thing to the next.

```
Slack  ──►  L0 org profile ──►  L1 understand  ──►  L2 look  ──►  L3 decide  ──►  L4 act
            (config)            (model)             (code)        (model, when       (code)
                                                                   it earns it)
```

**L0 — org profile.** What a working day *is* for this org: timezone, working hours, default duration, what "EOD" resolves to. Pure config, no logic beyond date arithmetic. Everything above reads from it; nothing hardcodes an hour.

**L1 — understand.** Turn a Slack message into a `ParsedRequest`: intent, attendees, concrete times. This is where the model does its most valuable work, because natural language is genuinely fuzzy. Three exits: understood, needs confirmation, or impossible. Impossible requests never reach a calendar.

**L2 — look.** Query Google free/busy. Deterministic, no model, no judgment. Returns busy blocks.

**L3 — decide.** Graded by how hard the problem actually is:

| Level | Situation | Who decides |
|---|---|---|
| L3.0 | Everyone free at the asked time | Code. Book it. No model call. |
| L3.1 | Some conflict, small group | Model proposes options; organizer picks |
| L3.2 | Conflict across a large group | Model reasons about quorum and seniority; negotiates with holdouts |

**L4 — act.** Create the calendar event. **Always Python, never the model.** The model can propose a slot; it cannot write to a calendar.

---

## Two rules that shape everything

**1. Seal non-determinism at a boundary.**

Established in Session 6 with `BedrockTimeParser`. A model call lives inside one method with a strict contract — it returns a clean value object or raises a typed error. Callers never see JSON, never see model quirks. Every model call in the system follows this shape.

**2. The model proposes; code disposes.**

The model is allowed to interpret, suggest, and reason. It is not allowed to take destructive action. Session 10 shipped `create_meeting_tool` guarded by a docstring asking the agent not to book speculatively — prompt-level enforcement of a rule about a destructive action. Three separate sessions have now produced the same failure mode: a constraint that lived in a docstring or a variable name instead of in code.

The correction: the agent returns a proposed slot; Python books it. A tool the agent doesn't have is a tool it cannot misuse.

**Corollary — the model classifies, code computes.** The model may return `shorthand="eod"`. `OrgProfile` turns that into 01:30–02:30. Never ask the model to compute a working-hours boundary, a date offset, or whether a time is in the past.

---

## Package layout

```
backend/
├── core/           contracts and pure logic — no I/O, no SDKs
│   ├── org_profile.py       L0
│   ├── request_parser.py    L1 contract
│   ├── availability.py      L2/L3 pure functions (find_free_slots)
│   ├── onboarding_service.py
│   ├── config.py
│   └── logging.py
│
├── integrations/   one subpackage per external system
│   ├── bedrock/             model calls
│   ├── google_calendar/     freebusy, event creation
│   ├── slack/               web client, signature verification
│   ├── dynamodb/            repositories
│   └── tokens/              AgentCore credential lookup
│
├── agents/         Strands tools and agent factories
│   ├── availability.py      tool wrappers
│   └── orchestrator.py      build_agent(creds)
│
└── api/            FastAPI routes and handlers
    ├── webhooks.py          /slack/commands, /slack/actions
    └── main.py              app, OAuth callback
```

**The `core/` ↔ `integrations/` split is the load-bearing convention.** `core/` defines an abstract contract; `integrations/` provides a concrete implementation using a specific SDK. `TimeParser` (core) ↔ `BedrockTimeParser` (integrations). `UserRepository` ↔ `DynamoDBUserRepository`. Swapping Google for Outlook, or Bedrock for anything else, should touch `integrations/` only.

Integration classes take plain strings, never a `Settings` object. Config is read at the construction site, so the class stays ignorant of where config comes from.

---

## Agent tool conventions

Learned the hard way in Session 9. All of these are non-obvious and all of them cost tool calls when violated.

- **Tool signatures speak in primitives.** `str`, `int`, `bool`, `list`, `dict`, and combinations. The model writes JSON — a `datetime` or a custom dataclass has no schema for it to write. Unwrap at entry, rewrap at exit.
- **`@tool` goes on the inner function of a factory, never the factory itself.** Factory-level exposes `creds: Credentials` as a model-visible argument.
- **No underscore prefix on tool names.** Strands publishes the raw function name to the model, which expects verb-first and no prefix. Nesting inside a factory already prevents outside imports.
- **Docstrings are load-bearing.** Google-style `Args:` and `Returns:` become the JSON schema the model reads. The first sentence is the *what*; a "Use this when..." line is prompt engineering. Two audiences, same words.
- **Credentials cross the boundary via closure, never as an argument.** The factory builds the provider; the returned tool closes over it.

---

## Where state lives

| State | Home | Lifetime |
|---|---|---|
| User ↔ Google identity | DynamoDB `users` | Permanent |
| In-flight OAuth session | DynamoDB `pending_sessions` | Minutes |
| OAuth tokens | AgentCore Identity vault | Managed |
| In-flight request (ask-back, negotiation) | DynamoDB, keyed by Slack message `ts` | 1 hour TTL |
| Negotiation state machine | Step Functions | Hours to days |
| Meeting history | Google Calendar | Permanent |

Two deliberate absences. **There is no application database of meetings** — Google Calendar is the record. And **the negotiation state machine does not live in client code**: `backend/core/state_machine.py` was created empty and deleted in Session 9, because Step Functions owns that job at the outer layer. Two state machines competing for the same authority is a bug factory.

This is also why Strands was chosen over LangGraph — LangGraph's value is its internal state graph, which would duplicate Step Functions. See Session 9 for the full framework comparison.

---

## Honest status

The README describes a negotiation product. This is what exists.

**Working:**
- Slack `/cadd` with signature verification and background processing
- Just-in-time OAuth onboarding for organizers via AgentCore Identity
- `@mention` → email resolution
- Natural-language time parsing via Bedrock
- Free/busy queries against real Workspace calendars
- Conflict detection and free-slot finding
- Block Kit buttons for slot selection
- Real Google Meet creation
- A Strands orchestrator that chains availability → free slots → booking, behind `use_agent`

**Not built:**
- **Any message to an attendee.** Every Slack message the system sends goes to the organizer. Ashwin has never received anything from cadd.
- Therefore: no accept/decline tracking, no negotiation, no consensus, no rounds, no escalation.
- Multi-turn conversation state of any kind.
- The other five agents. Availability exists as tools inside the orchestrator; the rest are names in a diagram.
- Step Functions, AgentCore Runtime deployment, Teams/Outlook.

**The gap, stated plainly:** the scheduling half is real and works. The negotiation half — the thing that distinguishes this from Calendly — is at zero. The first step across that gap is not another agent. It is the bot sending one message to someone who is not the organizer, and remembering what they said.

**Not portable yet.** Working hours are hardcoded to 17:30–02:30 IST in `webhooks.py`. A 9-to-5 org cannot use this today. L0 fixes that and is the current priority.

---

## Build order

1. **L0 + L1** — org profile, intent classification, ask-back on vague input, rejection of impossible input. Unblocks "is X free?" and "what's on my calendar?" as first-class intents. *(Current.)*
2. **L3 grading** — split all-free from conflicted. All-free books with no model call; conflicted routes to the agent, which proposes a slot for Python to book. Removes `create_meeting_tool`.
3. **Attendee DMs + request state** — the bot's first message to a non-organizer, and a row that survives past the end of a request. This is where the product changes category.
4. **L3.2 — quorum and negotiation.** Required vs. optional attendees, seniority weighting, 1:1 negotiation with holdouts.
5. **Reschedule.** Needs `list_events`, `update_event`, `delete_event`, an ownership check, and an enforcement wrapper. First genuinely destructive action in the system — booking wrong is noise, moving someone else's meeting silently changes their day.

---

## Related docs

- `docs/negotiation-state-machine.md` — written when step 4 exists. Empty until then, deliberately.
- Session logs — the reasoning behind each decision, including the failures.
