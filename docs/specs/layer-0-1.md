# Layers 0 & 1 — org profile and request understanding

Build spec. Covers the two layers below everything else: what an org's working day *is*, and what the user actually asked for. Nothing here touches a calendar or books a meeting.

---

## Why these two first

Everything above them is currently guessing.

`webhooks.py` hardcodes `17:30`, `timedelta(hours=9)`, and `"Asia/Kolkata"` in four places, and writes the midnight-crossing check out twice. That means the product physically cannot serve a 9-to-5 team — not "hasn't been tested with," *cannot*. And "tomorrow EOD" is unanswerable without it: end of day is 1:00 AM at Consultadd and 5:00 PM at Google.

It also means every request is assumed to be a booking request. "Is Ashwin free at 12?" books a meeting. "What's on my calendar tonight?" isn't understood at all.

Both are the same root cause: the system has no representation of *the org* or *the ask*. It jumps straight to "parse a time, query a calendar."

---

## Layer 0 — `OrgProfile`

### Contract

`backend/core/org_profile.py` — a dataclass plus three methods. No I/O, no LLM, fully unit-testable with a fixed `now`.

```python
@dataclass(frozen=True)
class OrgProfile:
    timezone: str            # "Asia/Kolkata"
    work_start: time         # time(17, 30)
    work_end: time           # time(2, 30)  — may be < work_start
    default_duration: int    # 30
```

`work_end < work_start` is the signal that the day crosses midnight. Nothing else needs to know that — the profile handles it.

### Methods

**`working_window(self, on: date) -> tuple[datetime, datetime]`**

Returns the working window containing `on`. For a midnight-crossing org, a request at 12:00 AM Aug 14 belongs to the window that *started* Aug 13 at 5:30 PM. This is the logic currently duplicated in `process_cadd_command` as the `start_ist.hour < 3` check — one implementation, one place, tested once.

**`resolve_shorthand(self, phrase: str, on: date) -> tuple[datetime, datetime] | None`**

Maps org-relative phrases to concrete windows:

| Phrase | Consultadd (17:30–02:30) | 9–5 org |
|---|---|---|
| `eod` / `end of day` | 01:30 – 02:30 | 16:00 – 17:00 |
| `sod` / `first thing` | 17:30 – 18:30 | 09:00 – 10:00 |
| `lunch` | midpoint ± 30m | 12:00 – 13:00 |

Returns `None` for anything it doesn't recognise — the model handles those.

**`is_within_hours(self, start: datetime, end: datetime) -> bool`**

Used later by Layer 3, defined here because it's the profile's business.

### Where it comes from

For now, one profile constructed from `Settings` at module level. Not a DynamoDB table yet — you have one org. But the *shape* is per-org from day one, so adding a table later is a lookup change, not a redesign.

### What this deletes

- The `start_ist.hour < 3 or (start_ist.hour == 2 and start_ist.minute <= 30)` block, twice, in `process_cadd_command`
- `query_start` / `query_end` and `work_start` / `work_end` computing the same thing from the same inputs
- `timezone_str = "Asia/Kolkata"` in `process_cadd_command` and again in `handle_book_slot`

---

## Layer 1 — request understanding

### What it replaces

`BedrockTimeParser` today answers one question: *what datetime?* It assumes the answer to *what does the user want?* is always "book a meeting."

Layer 1 answers both, in one model call.

### Output contract

`backend/core/request_parser.py`:

```python
class Intent(str, Enum):
    BOOK = "book"              # "meet with @ashwin at 3pm"
    CHECK = "check"            # "is @ashwin free at 3?"
    MY_CALENDAR = "my_calendar" # "what's on my evening?"

@dataclass
class ParsedRequest:
    intent: Intent
    start: datetime | None
    duration_minutes: int
    confidence: Literal["exact", "vague"]
    shorthand: str | None       # "eod", if that's what was said
```

`confidence` is the load-bearing field. It's what makes the ask-back possible.

- **`exact`** — the user named a time. "3pm", "tomorrow at 12am". Proceed.
- **`vague`** — the user named a *region*. "EOD", "sometime tomorrow", "this evening". Confirm before proceeding.

### The three exits

Layer 1 has exactly three outcomes. Same discipline as `BedrockTimeParser`'s "returns `ParsedTime` or raises `TimeParseError`, three exits, no fourth."

1. **Understood and exact** → return `ParsedRequest`, continue to Layer 2.
2. **Understood but vague** → DM a confirmation, stop. *"Tomorrow EOD is 1:30–2:30 AM for your team. Book 1:30?"* Resolution comes from `OrgProfile.resolve_shorthand`, not from the model — the model only identifies *that* it was shorthand.
3. **Impossible** → DM the reason, stop. Never reaches a calendar.

### Impossible cases, rejected here

| Input | Response |
|---|---|
| "yesterday at 5pm" | Time has passed |
| "today at 9am", sent at 5pm | Time has passed |
| "next blursday" | Couldn't understand |
| "at 3pm" with no `@mention` | Who with? |
| mentions a bot or channel | Not a person |
| mentions self only | Can't meet yourself |

Past-time rejection is a Python check against `now`, not a model judgment. Layer 1 has `now` and `OrgProfile.timezone` — that's all it needs. Never ask the model to decide whether something is in the past.

### Prompt rules, carried forward from S6/S9/S10

Three sessions have produced the same failure: a constraint that lived in a variable name instead of the prompt.

- The stated time is the meeting's **start**, never its end (S6 trap #4)
- **Interpolate concrete values**, never describe relationships. `{now.isoformat()}` and the profile's actual hours go in the prompt as literals (S9 trap #4, S10)
- The model **classifies**; Python **resolves**. The model says `shorthand="eod"`. `OrgProfile` turns that into 01:30–02:30. The model never computes a working-hours boundary.

### Ask-back needs state — and this is where it starts

Confirming "1:30 works?" means the *next* Slack message has to know what was asked. That's the multi-turn state problem, open since Session 6.

Do the minimum version here: a DynamoDB row keyed by the Slack message `ts`, holding the `ParsedRequest` and the attendee list, with a TTL of one hour. Not a negotiation state machine — a scratchpad. It's the same row that later holds negotiation rounds, so building it now is not throwaway work.

---

## Test cases

**Layer 0**

1. `working_window(Aug 14)` for a request at 12:00 AM → Aug 13 17:30 to Aug 14 02:30
2. Same profile, request at 8:00 PM → Aug 14 17:30 to Aug 15 02:30
3. 9–5 profile, request at 11:00 AM → same-day 09:00 to 17:00, no rollback
4. `resolve_shorthand("eod")` differs correctly between the two profiles
5. `resolve_shorthand("blursday")` → `None`

**Layer 1**

6. "meet @ashwin at 3pm" → `BOOK`, `exact`
7. "is @ashwin free at 3?" → `CHECK`, `exact`
8. "what's on my evening?" → `MY_CALENDAR`, no attendees required
9. "meet @ashwin tomorrow eod" → `BOOK`, `vague`, `shorthand="eod"` → confirmation sent
10. "meet @ashwin yesterday at 5pm" → rejected, no calendar call
11. "meet @ashwin at 3pm" sent at 5pm → rejected as past
12. "meet at 3pm", no mention → asks who
13. "next blursday" → couldn't understand
14. Confirmation approved → proceeds with the resolved window
15. Confirmation ignored for an hour → row expires, no orphan state

---

## Definition of done

- `OrgProfile` exists; `webhooks.py` contains no hardcoded hour arithmetic and no `"Asia/Kolkata"` literal
- A second profile (9–5, non-crossing) passes tests 3 and 4 without code changes
- `/cadd is @ashwin free at 9pm?` reports availability and books nothing
- `/cadd what's on my evening?` answers without requiring an `@mention`
- `/cadd meet @ashwin tomorrow eod` asks for confirmation before touching a calendar
- Every impossible input in the table above is rejected before Layer 2

---

## Explicitly not in this spec

- Anything that DMs an attendee. Layer 1 is organizer-side only.
- Conflict grading (L0/L1/L2 routing) — that's Layer 3.
- Removing `create_meeting_tool` from the agent — separate, and easier once intent exists.
- Negotiation, quorum, seniority, required-vs-optional attendees.

The one-line summary: **after this, the system knows what an org's day looks like and what the user asked for. It still can't negotiate — that's the next foundation, and it starts with the bot sending its first message to someone who isn't the organizer.**


<img width="2720" height="2480" alt="cadd_request_pipeline_layers" src="https://github.com/user-attachments/assets/e07c2ec6-c95c-436b-8480-889d406df468" />
