from typing import Any, Dict

from google.adk.agents import Agent, LlmAgent
from google.adk.apps.app import App, EventsCompactionConfig
from google.adk.models.google_llm import Gemini
from google.adk.sessions import InMemorySessionService
from google.adk.sessions import DatabaseSessionService
from google.adk.runners import Runner
from google.adk.tools.tool_context import ToolContext
from google.genai import types
import google.genai as genai
import os
from dotenv import load_dotenv
import asyncio


load_dotenv()  # Load API keys from .env into os.environ before anything else.
client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])

async def run_session(
    runner_instance: Runner,
    user_queries: list[str] | str = None,
    session_name: str = "default",
):
    print(f"\n ### Session: {session_name}")

    # Get app name from the Runner
    app_name = runner_instance.app_name

    # Attempt to create a new session or retrieve an existing one
    try:
        session = await session_service.create_session(
            app_name=app_name, user_id=USER_ID, session_id=session_name
        )
    except:
        session = await session_service.get_session(
            app_name=app_name, user_id=USER_ID, session_id=session_name
        )

    # Process queries if provided
    if user_queries:
        # Convert single query to list for uniform processing
        if type(user_queries) == str:
            user_queries = [user_queries]

        # Process each query in the list sequentially
        for query in user_queries:
            print(f"\nUser > {query}")

            # Convert the query string to the ADK Content format
            query = types.Content(role="user", parts=[types.Part(text=query)])

            # Stream the agent's response asynchronously
            async for event in runner_instance.run_async(
                user_id=USER_ID, session_id=session.id, new_message=query
            ):
                # Check if the event contains valid content
                if event.content and event.content.parts:
                    # Filter out empty or "None" responses before printing
                    if (
                        event.content.parts[0].text != "None"
                        and event.content.parts[0].text
                    ):
                        print(f"{MODEL_NAME} > ", event.content.parts[0].text)
    else:
        print("No queries!")

retry_config = types.HttpRetryOptions(
    attempts=3,  # Maximum retry attempts
    exp_base=2,  # Delay multiplier
    initial_delay=1,
    http_status_codes=[429, 500, 503, 504],  # Retry on these HTTP errors
)

APP_NAME = "default"  # Application
USER_ID = "default"  # User
SESSION = "default"  # Session

MODEL_NAME = "gemini-2.5-flash-lite"


# Step 1: Create the same agent (notice we use LlmAgent this time)
chatbot_agent = LlmAgent(
    model=Gemini(model="gemini-2.5-flash-lite", retry_options=retry_config),
    name="text_chat_bot",
    description="A text chatbot with persistent memory",
)

# Step 2: Switch to DatabaseSessionService
# SQLite database will be created automatically
db_url = "sqlite+aiosqlite:///my_agent_data.db"  # Local SQLite file we chaneged the url
session_service = DatabaseSessionService(db_url=db_url)

# Step 3: Create a new runner with persistent storage
runner = Runner(agent=chatbot_agent, app_name=APP_NAME, session_service=session_service)

print("✅ Upgraded to persistent sessions!")
print(f"   - Database: my_agent_data.db")
print(f"   - Sessions will survive restarts!")

# Re-define our app with Events Compaction enabled
research_app_compacting = App(
    name="research_app_compacting",
    root_agent=chatbot_agent,
    # This is the new part!
    events_compaction_config=EventsCompactionConfig(
        compaction_interval=3,  # Trigger compaction every 3 invocations
        overlap_size=1,  # Keep 1 previous turn for context
    ),
)

db_url = "sqlite+aiosqlite:///my_agent_data.db"
session_service = DatabaseSessionService(db_url=db_url)


# Create a new runner for our upgraded app
research_runner_compacting = Runner(
    app=research_app_compacting, session_service=session_service
)


print("✅ Research App upgraded with Events Compaction!")

# Run a conversation with two queries in the same session
# Notice: Both queries are part of the SAME session, so context is maintained
if __name__ == "__main__":
    async def main():
        await run_session(research_runner_compacting, "What is the latest news about AI in healthcare?", "compaction_demo")
        await run_session(research_runner_compacting, "Are there any new developments in drug discovery?", "compaction_demo")
        await run_session(research_runner_compacting, "Tell me more about the second development you found.", "compaction_demo")
        await run_session(research_runner_compacting, "Who are the main companies involved in that?", "compaction_demo")

        # Get the final session state
        final_session = await research_runner_compacting.session_service.get_session(
            app_name="research_app_compacting",
            user_id=USER_ID,
            session_id="compaction_demo",
        )

        print("--- Searching for Compaction Summary Event ---")
        found_summary = False
        for event in final_session.events:
            # Compaction events have a 'compaction' attribute
            if event.actions and getattr(event.actions, "compaction", None):
                print("\n✅ SUCCESS! Found the Compaction Event:")
                print(f"  Author: {event.author}")
                print(f"\n Compacted information: {event}")
                found_summary = True
                break

        if not found_summary:
            print(
                "\n❌ No compaction event found. Try increasing the number of turns in the demo."
            )

    asyncio.run(main())