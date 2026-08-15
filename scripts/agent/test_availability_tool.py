from strands import Agent
from backend.core.config import settings
from backend.agents.availability import find_free_slots_tool


agent=Agent(
     model=settings.bedrock_model_id,
     system_prompt="You help schedule meetings by finding free time windows. Use your tools when asked about availability.",
     tools=[find_free_slots_tool],
)
message = """
Alice is busy from 09:00 to 10:00 and from 14:00 to 15:00 on 2026-08-20 IST (+05:30).
Bob is busy from 10:00 to 11:00 on the same day.

Find 30-minute meeting windows for Alice and Bob between 09:00 and 17:00 IST on 2026-08-20.
Alice's email is alice@example.com and Bob's is bob@example.com.
"""

agent(message)