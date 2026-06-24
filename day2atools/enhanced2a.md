# Enhanced Currency Agent — What's New (Section 3 & 4)

This builds on `currencyconvtagent.py`. Everything from before (imports, dotenv, retry config, `get_fee_for_payment_method`, `get_exchange_rate`, the helper function, asyncio runner) is unchanged. This doc only covers what's genuinely new: **delegating math to a code-executing sub-agent**, and the conceptual tool taxonomy from Section 4.

---

## The problem being solved

```python
#The agent's instruction says "calculate the final amount after fees" 
# but LLMs aren't always reliable at math. 
# They might make calculation errors or use inconsistent formulas.
```

**First principle:** an LLM is a next-token predictor trained on text. When it "does math," it's not running an arithmetic algorithm — it's pattern-matching what a correct-looking calculation tends to read like. For small/simple numbers it's often right, but it has no guaranteed correctness, and errors compound across multi-step calculations (fee deduction → currency conversion). A real Python interpreter, on the other hand, executes deterministic arithmetic — `1250 * 0.01` is always exactly `12.5`, no matter how it's phrased. So instead of trusting the LLM to "do" the math, the fix is: have the LLM **write the code**, and have something else **run** that code. Code execution is deterministic; LLM mental math is not.

---

## The `calculation_agent` — a specialist that only writes code

```python
calculation_agent = LlmAgent(
    name="CalculationAgent",
    model=Gemini(model="gemini-2.5-flash-lite", retry_options=try_config),
    instruction="""You are a specialized calculator that ONLY responds with Python code. You are forbidden from providing any text, explanations, or conversational responses.

     Your task is to take a request for a calculation and translate it into a single block of Python code that calculates the answer.

     **RULES:**
    1.  Your output MUST be ONLY a Python code block.
    2.  Do NOT write any text before or after the code block.
    3.  The Python code MUST calculate the result.
    4.  The Python code MUST print the final result to stdout.
    5.  You are PROHIBITED from performing the calculation yourself. Your only job is to generate the code that will perform the calculation.

    Failure to follow these rules will result in an error.
       """,
    code_executor=BuiltInCodeExecutor(),
)
```

A few things to notice from first principles:

- **This is a *second*, separate `LlmAgent`**, not a tool function. It has its own name, own model instance, own instruction. It's a fully independent agent — it just happens to have a very narrow job.
- **The instruction is unusually strict and repetitive** ("ONLY", "forbidden", "PROHIBITED", "MUST", restated five times as numbered rules). This is deliberate prompt engineering: the entire point of this agent is to *never* fall back into "let me just answer in my head." Since the underlying problem is "LLMs are tempted to eyeball math," the instruction has to aggressively close off that escape hatch — generic phrasing like "please write code for this" wouldn't be a strong enough guardrail, because the model could still slip in a casual answer alongside the code.
- **`code_executor=BuiltInCodeExecutor()`** — this is a new constructor argument on `LlmAgent` that you haven't used before (previously you only used `tools=[...]`). This tells ADK: after this agent generates a block of Python, actually **run it in a sandboxed environment** (via Gemini's built-in code execution capability) and capture the printed output. Rule #4 in the instruction ("MUST print the final result to stdout") exists *because* of this — the executor only gets a result by capturing whatever the code prints; if the code computed a value but never printed it, there'd be nothing to return.
- Why `code_executor=` and not `tools=[...]`? Because code execution isn't "call this one Python function with these arguments" (like your fee/rate lookups) — it's "take arbitrary generated code and run it in a sandbox." That's categorically different machinery, so ADK exposes it as its own dedicated parameter on the agent rather than as a plain function tool.

---

## `AgentTool` — turning one agent into another agent's tool

```python
tools=[
    get_fee_for_payment_method,
    get_exchange_rate,
    AgentTool(agent=calculation_agent),  # Using another agent as a tool!
],
```

Recall: previously, everything in `tools=[...]` was a plain Python function, and ADK auto-built a schema from its type hints/docstring. `AgentTool(agent=calculation_agent)` is a *wrapper* that makes an entire other `LlmAgent` look like just another callable tool to the agent holding the list.

**Why this works conceptually:** from `enhanced_currency_agent`'s point of view, it doesn't need to know that `calculation_agent` internally writes code and runs it in a sandbox. It just sees "a tool I can call with a calculation request, which gives me back a number." `AgentTool` is the adapter that hides all of `calculation_agent`'s internal complexity behind the same simple call/response interface as `get_fee_for_payment_method`.

This is the same idea as function composition in plain programming — wrapping a complex subroutine behind a simple function signature — except here the "subroutine" is itself a full LLM-driven agent with its own instruction and execution loop.

---

## The updated `enhanced_currency_agent` instruction

```python
instruction="""You are a smart currency conversion assistant. You must strictly follow these steps and use the available tools.

  For any currency conversion request:

   1. Get Transaction Fee: Use the get_fee_for_payment_method() tool to determine the transaction fee.
   2. Get Exchange Rate: Use the get_exchange_rate() tool to get the currency conversion rate.
   3. Error Check: After each tool call, you must check the "status" field in the response. If the status is "error", you must stop and clearly explain the issue to the user.
   4. Calculate Final Amount (CRITICAL): You are strictly prohibited from performing any arithmetic calculations yourself. You must use the calculation_agent tool to generate Python code that calculates the final converted amount. ...
   5. Provide Detailed Breakdown: ...
"""
```

Compare this to the original agent's instruction, which just said "calculate the final amount after fees... and provide a clear breakdown." The new version replaces that vague instruction with an explicit, numbered, sequential protocol — and step 4 is marked **CRITICAL** and explicitly **prohibits** the agent from doing arithmetic itself, redirecting it to the `calculation_agent` tool instead.

This matters because instructions are the only lever you have over how an LLM agent behaves — there's no compiler enforcing "don't do mental math here." So the fix for the unreliable-math problem isn't just *adding* a calculation tool; it's *also* rewriting the instruction to explicitly forbid the shortcut the model would otherwise take (computing it inline instead of delegating).

---

## Agent Tools vs. Sub-Agents — a conceptual distinction worth internalizing

This wasn't code, but it's an important mental model from Section 3.3:

| | Agent Tool (what's used here) | Sub-Agent (a different pattern) |
|---|---|---|
| Who calls whom | Agent A calls Agent B *as a tool* | Agent A *transfers control* to Agent B entirely |
| What happens to the result | B's response goes back to A; A keeps going | B takes over; A is out of the loop for the rest of the interaction |
| Use case | Delegating a specific sub-task (e.g. "go calculate this number for me") | Handing off the whole conversation (e.g. routing to a specialist support tier) |

In this file, `enhanced_currency_agent` needs the calculated number back so it can keep building its breakdown explanation — it doesn't want to disappear and let `calculation_agent` take over the conversation. That's exactly why `AgentTool` (delegate-and-return) is the right pattern here, not a sub-agent handoff.

---

## Section 4: the ADK tool taxonomy (conceptual — no new runnable code)

This section wasn't executable, but it's useful as a map of where the things you've actually built fit in:

**Custom Tools** (you build the logic yourself):
- **Function Tools** — what `get_fee_for_payment_method` and `get_exchange_rate` are: a plain Python function ADK turns into a tool automatically.
- **Long Running Function Tools** — same idea, but for tasks that take a while (e.g. waiting on a human approval) — not used in this file, but conceptually: the agent can kick off the task and keep doing other things instead of blocking on it.
- **Agent Tools** — what `AgentTool(agent=calculation_agent)` is: an entire other agent wrapped to look like a tool.
- **MCP Tools / OpenAPI Tools** — ways to plug in tools from external protocol servers or auto-generate them from an API spec, instead of hand-writing the Python function yourself. Not used in this file.

**Built-in Tools** (ADK/Gemini ship these ready-made):
- **Gemini Tools** — `BuiltInCodeExecutor()` is one of these (the other example being `google_search`, which is imported in this file but never actually used). These need zero custom code — you just attach them.
- **Google Cloud Tools / Third-party Tools** — pre-built integrations for things like BigQuery or GitHub. Not used here, just listed for awareness.

The throughline across all of Section 3: your two original functions are "Custom Function Tools," your new `calculation_agent` is wrapped as an "Agent Tool," and the code execution underneath it is a "Built-in Gemini Tool" (`BuiltInCodeExecutor`) — three different tool categories, composed together inside one `tools=[...]` list.