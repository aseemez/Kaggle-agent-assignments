import os
from dotenv import load_dotenv
import google.generativeai as genai
from google.adk.agents import Agent
from google.adk.models.google_llm import Gemini
from google.adk.runners import InMemoryRunner
from google.adk.tools import google_search
from google.genai import types
import asyncio

load_dotenv()
genai.configure(api_key=os.environ["GOOGLE_API_KEY"])

try_config=types.HttpRetryOptions(
    attempts=5,  # Maximum retry attempts
    exp_base=7,  # Delay multiplier
    initial_delay=1, # Initial delay before first retry (in seconds)
    http_status_codes=[429, 500, 503, 504] # Retry on these HTTP errors
)

root_agent = Agent(
    name="helpful_assistant",
    model=Gemini(
        model="gemini-2.5-flash-lite",
        retry_options=try_config
    ),
    description="A simple agent that can answer general questions.",
    instruction="You are a helpful assistant. Use Google Search for current info or if unsure.",
    tools=[google_search],
)

print("✅ Root Agent defined.")

if __name__ == "__main__":
    question = input("Ask your agent something: ")

    runner = InMemoryRunner(agent=root_agent)

    async def main():
        response = await runner.run_debug(question)

    asyncio.run(main())

  