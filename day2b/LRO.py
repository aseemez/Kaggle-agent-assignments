# =============================================================================
# LONG-RUNNING OPERATIONS (LRO) — SHIPPING COORDINATOR AGENT
# =============================================================================
#
# WHAT IS A "LONG-RUNNING OPERATION"?
# ------------------------------------
# A normal agent call looks like this:
#   You ask → Agent thinks → Agent responds. Done.
#
# But sometimes a tool the agent calls can't finish immediately.
# It needs to PAUSE, wait for something external (like a human saying yes/no),
# and then CONTINUE from exactly where it left off.
#
# That "pause → wait → resume" pattern is an LRO (Long-Running Operation).
#
# In this file: shipping small orders is instant (no pause needed),
# but large orders (>5 containers) require a human to approve before proceeding.
# The agent literally stops mid-execution and waits for that decision.
# =============================================================================


# =============================================================================
# IMPORTS — what each one is for
# =============================================================================

import os
import asyncio   # Python's standard library for writing async (non-blocking) code.
                 # We need this because talking to an LLM over a network takes time,
                 # and we don't want to freeze the whole program while waiting.

import uuid      # Universally Unique IDentifier. Generates random unique strings like
                 # "3f2a1b9c". We use it to give each session a unique ID so the runner
                 # can track multiple simultaneous conversations without mixing them up.

from dotenv import load_dotenv  # Reads a .env file and loads its contents as environment
                                # variables. Keeps secrets (API keys) out of source code.

from google import genai
from google.genai import types   # `types` contains the data structures ADK uses:
                                 # Content, Part, FunctionResponse, etc.

from google.adk.agents import LlmAgent        # The agent class. Wraps an LLM and gives
                                              # it tools + instructions.

from google.adk.models.google_llm import Gemini  # The specific LLM we're using inside
                                                 # the agent.

from google.adk.runners import Runner            # The Runner is the "engine" that drives
                                                 # the agent. It manages the conversation
                                                 # loop: send message → get events → repeat.

from google.adk.sessions import InMemorySessionService  # Stores session state (the
                                                        # conversation history, pending
                                                        # tool calls) in RAM. In a real
                                                        # system you'd use a database so
                                                        # state survives restarts.

from google.adk.tools.tool_context import ToolContext  # The object ADK injects into
                                                       # every tool function. It's how
                                                       # a tool communicates back to ADK
                                                       # (e.g., "I need approval before
                                                       # I can continue").

from google.adk.apps.app import App, ResumabilityConfig  # App wraps an agent and adds
                                                         # capabilities. ResumabilityConfig
                                                         # is what enables the LRO
                                                         # pause/resume mechanism.

from google.adk.tools.function_tool import FunctionTool  # Converts a plain Python
                                                         # function into a tool the
                                                         # agent can call.

load_dotenv()  # Load API keys from .env into os.environ before anything else.
client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])

# =============================================================================
# RETRY CONFIGURATION
# =============================================================================
# LLM APIs sometimes fail temporarily (rate limits, server blips).
# Instead of crashing, we retry automatically.
#
# exp_base=7 means the wait doubles on each retry:
#   attempt 1 → wait 1s, attempt 2 → wait 7s, attempt 3 → wait 49s ...
# http_status_codes: only retry on these specific error codes:
#   429 = rate limited, 500/503/504 = server-side errors

retry_config = types.HttpRetryOptions(
    attempts=5,
    exp_base=5,
    initial_delay=1,
    http_status_codes=[429, 500, 503, 504],
)


# =============================================================================
# BUSINESS LOGIC CONSTANT
# =============================================================================
LARGE_ORDER_THRESHOLD = 5  # Orders above this number require human approval.


# =============================================================================
# THE TOOL: place_shipping_order
# =============================================================================
# This is the function the agent will call when a user wants to ship something.
#
# KEY DESIGN: This same function is called TWICE for large orders.
#   - Call 1: Agent calls it, it sees no approval yet → requests approval and pauses.
#   - Call 2: After the human decides, ADK resumes → function runs again, this time
#             with tool_context.tool_confirmation populated → it sees the decision.
#
# HOW DOES ADK KNOW TO CALL IT TWICE?
#   When you call tool_context.request_confirmation(), ADK emits a special
#   "adk_request_confirmation" event and halts execution. When you resume with
#   the human's answer (using the same invocation_id), ADK re-executes the tool
#   but this time injects the human's decision into tool_context.tool_confirmation.
#
# WHY `tool_context: ToolContext` AS A PARAMETER?
#   ADK detects this parameter by type annotation and automatically injects it.
#   You never pass it manually — ADK does. It's the tool's "back-channel" to the
#   framework.

def place_shipping_order(
    num_containers: int, destination: str, tool_context: ToolContext
) -> dict:
    """Places a shipping order. Requires approval if ordering more than 5 containers (LARGE_ORDER_THRESHOLD).

    Args:
        num_containers: Number of containers to ship
        destination: Shipping destination

    Returns:
        Dictionary with order status
    """

    # ------------------------------------------------------------------
    # SCENARIO 1: Small order — approve immediately, no human needed.
    # ------------------------------------------------------------------
    if num_containers <= LARGE_ORDER_THRESHOLD:
        return {
            "status": "approved",
            "order_id": f"ORD-{num_containers}-AUTO",
            "num_containers": num_containers,
            "destination": destination,
            "message": f"Order auto-approved: {num_containers} containers to {destination}",
        }

    # ------------------------------------------------------------------
    # SCENARIO 2 (FIRST CALL): Large order, no approval decision yet.
    #   tool_context.tool_confirmation is None/falsy on the first call.
    #   We request confirmation — this tells ADK to:
    #     1. Emit the "adk_request_confirmation" event.
    #     2. FREEZE execution here. The function returns immediately after
    #        this block, but ADK remembers it needs to re-enter this tool
    #        when a resume happens.
    # ------------------------------------------------------------------
    if not tool_context.tool_confirmation:
        tool_context.request_confirmation(
            hint=f"⚠️ Large order: {num_containers} containers to {destination}. Do you want to approve?",
            payload={"num_containers": num_containers, "destination": destination},
        )
        # This return value goes to the AGENT so it can tell the user
        # "hey, waiting for approval". The agent's response is then visible
        # in the events, but execution is paused — the runner won't proceed
        # until we explicitly resume it.
        return {  # This is sent to the Agent
            "status": "pending",
            "message": f"Order for {num_containers} containers requires approval",
        }

    # ------------------------------------------------------------------
    # SCENARIO 3 (SECOND CALL / RESUME): Human has made their decision.
    #   ADK re-calls this function with tool_context.tool_confirmation
    #   populated. We check .confirmed to see what the human decided.
    # ------------------------------------------------------------------
    if tool_context.tool_confirmation.confirmed:
        return {
            "status": "approved",
            "order_id": f"ORD-{num_containers}-HUMAN",
            "num_containers": num_containers,
            "destination": destination,
            "message": f"Order approved: {num_containers} containers to {destination}",
        }
    else:
        return {
            "status": "rejected",
            "message": f"Order rejected: {num_containers} containers to {destination}",
        }


print("✅ Long-running functions created!")


# =============================================================================
# THE AGENT
# =============================================================================
# LlmAgent = an LLM + a set of tools + instructions on how to use them.
# The agent decides WHEN to call which tool based on the user's message.
# Here, our agent has exactly one tool: place_shipping_order.
#
# FunctionTool(func=place_shipping_order) wraps our plain Python function
# so ADK can describe it to the LLM as a JSON schema (name, params, types).
# The LLM then knows "I can call place_shipping_order(num_containers, destination)".

shipping_agent = LlmAgent(
    name="shipping_agent",
    model=Gemini(model="gemini-2.5-flash-lite", retry_options=retry_config),
    instruction="""You are a shipping coordinator assistant.
  
  When users request to ship containers:
   1. Use the place_shipping_order tool with the number of containers and destination
   2. If the order status is 'pending', inform the user that approval is required
   3. After receiving the final result, provide a clear summary including:
      - Order status (approved/rejected)
      - Order ID (if available)
      - Number of containers and destination
   4. Keep responses concise but informative
  """,
    tools=[FunctionTool(func=place_shipping_order)],
)

print("✅ Shipping Agent created!")


# =============================================================================
# THE APP (wraps the agent with LRO support)
# =============================================================================
# An App is a thin wrapper around an agent that adds framework-level features.
# The CRITICAL part here is ResumabilityConfig(is_resumable=True).
#
# Without this, the Runner treats every call to run_async() as a brand-new
# conversation. With it, the Runner understands that a call can be PAUSED
# and RESUMED later using the same invocation_id.
#
# Think of it like this:
#   is_resumable=False → "Every run_async() is a fresh phone call."
#   is_resumable=True  → "run_async() can put a call on hold; I'll resume it later."

shipping_app = App(
    name="shipping_coordinator",
    root_agent=shipping_agent,
    resumability_config=ResumabilityConfig(is_resumable=True),
)

print("✅ Resumable App created")


# =============================================================================
# SESSION SERVICE
# =============================================================================
# A "session" is the full state of one conversation: message history, pending
# tool calls, temporary variables. InMemorySessionService stores all of this
# in RAM (a Python dict, essentially).
#
# Why do we need it explicitly?
#   Because the LRO pause means our workflow SPANS multiple run_async() calls.
#   The session service is what connects them — when we resume with the same
#   session_id, ADK looks up the stored state and continues from where it stopped.
#
# In production you'd replace InMemorySessionService with a DB-backed one so
# state survives restarts and can be shared across server instances.

session_service = InMemorySessionService()


# =============================================================================
# THE RUNNER
# =============================================================================
# The Runner is the execution engine. You give it a message, it drives the
# agent's conversation loop and yields events back to you.
#
# Why pass `app` here instead of `agent` directly?
#   Because the App carries the ResumabilityConfig. The Runner needs that
#   config to know it should handle pause/resume rather than fresh-start.

shipping_runner = Runner(
    app=shipping_app,
    session_service=session_service,
)

print("✅ Runner created")


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================
    # """
    # Scans the list of events from a run_async() call looking for the
    # special "adk_request_confirmation" function call.

    # WHY DO WE SCAN EVENTS?
    # The runner doesn't give us a single return value — it gives us a STREAM
    # of events (text chunks, tool calls, tool results, etc.). If the tool
    # requested approval, that request is buried in one of these events as a
    # function_call part with name="adk_request_confirmation".

    # We need to find it because it contains two things we need to resume:
    #   - approval_id: identifies which specific tool-call checkpoint to resume.
    #   - invocation_id: identifies the entire agent-run to resume.

    # Returns:
    #     A dict with approval_id and invocation_id if approval is needed.
    #     None if no approval event was found (small order, no pause needed).
    # """

def check_for_approval(events: list) -> dict | None:
    """Check if events contain an approval request.

    Returns:
        dict with approval details or None
    """
    for event in events:
        if event.content and event.content.parts:
            for part in event.content.parts:
                if (
                    part.function_call
                    and part.function_call.name == "adk_request_confirmation"
                ):
                    return {
                        "approval_id": part.function_call.id,
                        "invocation_id": event.invocation_id,
                    }
    return None  # No approval event found → it was a small order, already done.


def print_agent_response(events: list) -> None:
    # """
    # Extracts and prints all text parts from the agent's events.

    # The agent's final response to the user is a `part.text` inside
    # an event. We loop all events and print every text part we find.
    # (There could be multiple if the agent streamed its response in chunks.)
    # """
    """Print agent's text responses from events."""

    for event in events:
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    print(f"Agent > {part.text}")


def create_approval_response(approval_info: dict, approved: bool) -> types.Content:
    # """
    # Packages the human's yes/no decision into the exact message format
    # that ADK expects when resuming a paused tool call.

    # WHY THIS SPECIFIC FORMAT?
    # ADK paused on a "function call" (adk_request_confirmation). To resume,
    # it needs a matching "function response" that references the same call ID.
    # This is the standard tool-call → tool-response protocol that LLMs use,
    # just hijacked here for the human-in-the-loop pause.

    # The `id` field ties the response to the exact checkpoint that's waiting.
    # The `confirmed` field is what the tool reads in Scenario 3 above.

    # Args:
    #     approval_info: The dict returned by check_for_approval().
    #     approved: True if the human approved, False if rejected.

    # Returns:
    #     A types.Content object — the same structure used for any user message —
    #     but containing a FunctionResponse instead of text.
    # """
    """Create approval response message."""

    confirmation_response = types.FunctionResponse(
        id=approval_info["approval_id"],      # Match this response to the paused call.
        name="adk_request_confirmation",      # Must match the name of the paused call.
        response={"confirmed": approved},     # The human's decision.
    )
    return types.Content(
        role="user",
        parts=[types.Part(function_response=confirmation_response)],
    )


print("✅ Helper functions defined")


# =============================================================================
# THE MAIN WORKFLOW
# =============================================================================
#
# WHY `async def`?
# ----------------
# When you call run_async(), it talks to Google's servers over the network.
# That round-trip might take 1–5 seconds. During that wait, `async def` lets
# Python do other work instead of freezing. It's cooperative multitasking.
#
# The `async/await` pattern works like this:
#   - `await some_coroutine()` means "start this, and while waiting for it
#     to finish, let other things run. Resume here when it's done."
#   - `async def` marks a function as one that CAN be awaited.
#
# WHY `async for event in shipping_runner.run_async(...)`?
# --------------------------------------------------------
# run_async() doesn't return all events at once. It's an async GENERATOR:
# it yields events one-by-one as the agent produces them (streaming).
# `async for` is how you iterate over an async generator — it awaits each
# yielded value before moving to the next, and handles all the awaiting
# machinery for you automatically.
#
# Analogy: Imagine a reporter filing updates from an event live, not all
# at once. `async for` is how you read each update as it arrives.

async def run_shipping_workflow(query: str, auto_approve: bool = True) -> None:
    # """
    # End-to-end shipping workflow, implementing the diagram's flow:

    # User Query
    #     ↓
    # STEP 1: run_async() — agent calls place_shipping_order
    #     ↓ (events stream back)
    # STEP 2: check_for_approval() — did the tool pause?
    #     ↓
    # PATH A (Found): Large order → pause → human decides → resume
    # PATH B (None):  Small order → already done → print response

    # Args:
    #     query: What the user wants to ship. Natural language.
    #     auto_approve: Simulates the human decision in this demo.
    #                   In real usage, this would be a UI prompt.
    # """
    """Runs a shipping workflow with approval handling.

    Args:
        query: User's shipping request
        auto_approve: Whether to auto-approve large orders (simulates human decision)
    """
    print(f"\n{'=' * 60}")
    print(f"User > {query}\n")

    # -------------------------------------------------------------------
    # SESSION SETUP
    # Each shipping request gets its own session so they don't interfere.
    # uuid4().hex[:8] gives us 8 random hex chars — enough uniqueness for a demo.
    # -------------------------------------------------------------------
    session_id = f"order_{uuid.uuid4().hex[:8]}"

    # `await` here because create_session() is async — it might write to a DB
    # in a real implementation. Even with InMemorySessionService, the interface
    # is async so it's compatible with both.
    await session_service.create_session(
        app_name="shipping_coordinator",
        user_id="test_user",
        session_id=session_id,
    )

    # Package the user's text into the Content/Part structure ADK expects.
    # All messages — user and agent — use this same format internally.
    query_content = types.Content(
        role="user",
        parts=[types.Part(text=query)],
    )

    # Collect all events from STEP 1 into a list so we can scan them in STEP 2.
    # We don't process them inside the loop because we need ALL events before
    # we can know whether an approval was requested.
    events = []

    # -------------------------------------------------------------------
    # STEP 1: Send the user's message to the agent.
    #
    # run_async() drives the full agent loop:
    #   1. Sends the message to the LLM.
    #   2. LLM decides to call place_shipping_order.
    #   3. ADK calls place_shipping_order.
    #   4a. Small order → tool returns approved → LLM writes final reply → yields events → done.
    #   4b. Large order → tool calls request_confirmation → ADK yields the
    #       "adk_request_confirmation" event → run_async() STOPS yielding (pauses).
    #
    # `async for` collects every event as it streams out.

    # STEP 1: Send initial request to the Agent. If num_containers > 5, 
    # the Agent returns the special `adk_request_confirmation` event
    # -------------------------------------------------------------------
    async for event in shipping_runner.run_async(
        user_id="test_user",
        session_id=session_id,
        new_message=query_content,
    ):
        events.append(event)

    # -------------------------------------------------------------------
    # STEP 2: Inspect the collected events.
    # Did the tool pause and request approval, or did it finish?
    # STEP 2: Loop through all the events generated and check 
    # if `adk_request_confirmation` is present.
    # -------------------------------------------------------------------
    approval_info = check_for_approval(events)

    # -------------------------------------------------------------------
    # PATH A: Approval was requested (large order).
    # STEP 3: If the event is present, it's a large order - HANDLE APPROVAL WORKFLOW
    # -------------------------------------------------------------------
    if approval_info:
        print(f"⏸️  Agent paused — waiting for human decision...")
        print(f"🤔 Human Decision: {'APPROVE ✅' if auto_approve else 'REJECT ❌'}\n")

        # Resume the paused run_async() by calling it AGAIN with:
        #   1. The SAME session_id → ADK loads the stored conversation state.
        #   2. The human's decision packaged as a FunctionResponse.
        #   3. The SAME invocation_id → this is what tells ADK "resume this
        #      specific paused run" rather than starting a new one.
        #      Without invocation_id, ADK would start fresh and lose context.

        #PATH A: Resume the agent by calling run_async() again with the approval decision

        async for event in shipping_runner.run_async(
            user_id="test_user",
            session_id=session_id,
            new_message=create_approval_response(approval_info, auto_approve),
            # Send human decision here
            invocation_id=approval_info["invocation_id"],  # ← THE RESUME KEY # Critical: same invocation_id tells ADK to RESUME
        ):
            # This time we print directly because we don't need to scan for approval again.
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        print(f"Agent > {part.text}")

    # -------------------------------------------------------------------
    # PATH B: No approval needed (small order). Already completed in STEP 1.
    # Just print whatever the agent said.
    # -------------------------------------------------------------------
    else:
        # PATH B: If the `adk_request_confirmation` is not present 
        # - no approval needed - order completed immediately.

        print_agent_response(events)

    print(f"{'=' * 60}\n")


print("✅ Workflow function ready")


# =============================================================================
# ENTRY POINT
# =============================================================================
#
# WHY `async def main()` + `asyncio.run(main())`?
# -------------------------------------------------
# `run_shipping_workflow` is async, so we can only `await` it from inside
# another async function. `main()` is that wrapper.
#
# `asyncio.run(main())` is the bridge between the normal (synchronous) Python
# runtime and the async world. It:
#   1. Creates an event loop (the scheduler that manages all async tasks).
#   2. Runs main() inside it until completion.
#   3. Cleans up the event loop when done.
#
# You only call asyncio.run() ONCE, at the top level. Everything async
# inside uses `await` instead.

if __name__ == "__main__":

    async def main():
        # Demo 1: 3 containers — below threshold, auto-approved, no pause.
        await run_shipping_workflow("Ship 3 containers to Singapore")

        # Demo 2: 10 containers — above threshold, pauses, human APPROVES.
        await run_shipping_workflow("Ship 10 containers to Rotterdam", auto_approve=True)

        # Demo 3: 8 containers — above threshold, pauses, human REJECTS.
        await run_shipping_workflow("Ship 8 containers to Los Angeles", auto_approve=False)

    asyncio.run(main())