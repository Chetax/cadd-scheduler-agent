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

🚧 Early build — architecture defined, integrations in progress.

## Roadmap

- [ ] Slack app: OAuth install + DM negotiation cards
- [ ] AgentCore Runtime deployment of the 6-agent crew
- [ ] Step Functions negotiation state machine
- [x] Google Calendar + Google Meet integration
- [ ] Microsoft Teams (Bot Framework) parity
- [ ] Outlook Calendar integration
- [ ] Organizer escalation flow after N failed rounds
- [ ] Web dashboard (meeting history, team settings)
