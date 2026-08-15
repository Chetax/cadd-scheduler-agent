from strands import Agent, tool
from strands_tools import calculator, current_time
from backend.core.config import settings

# Create an agent with tools from the community-driven strands-tools package
agent = Agent(tools=[calculator, current_time],model=settings.bedrock_model_id)

# Ask the agent a question that uses the available tools
message = """
can you greet
"""
agent(message)