# currencyconvtagent.py — Walkthrough

## Quick revision (you've seen this before)

```python
import asyncio
import os
from dotenv import load_dotenv
import google.generativeai as genai
from google.genai import types
from google.adk.agents import LlmAgent
from google.adk.models.google_llm import Gemini
from google.adk.runners import InMemoryRunner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import google_search, AgentTool, ToolContext
from google.adk.code_executors import BuiltInCodeExecutor

load_dotenv()
genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
```

- **Imports**: standard ADK boilerplate — `LlmAgent` (the agent class), `Gemini` (model wrapper), `InMemoryRunner`/`InMemorySessionService` (run + store conversation in RAM), plus a few unused leftovers (`google_search`, `AgentTool`, `ToolContext`, `BuiltInCodeExecutor`) from whatever template this was built off.
- **dotenv**: `load_dotenv()` reads your `.env` file into `os.environ`, so `os.environ["GOOGLE_API_KEY"]` doesn't crash.
- **genai.configure**: auths the older `google.generativeai` SDK. Not actually used by the ADK `Gemini` wrapper below — vestigial, but harmless. (This is also the line throwing your `FutureWarning` in the terminal — that package is deprecated.)
- **asyncio at the bottom**: ADK calls are network calls under the hood, so they're `async`. `asyncio.run(main())` just boots the event loop so `await currency_runner.run_debug(...)` can run.

That's the "seen it before" part. Now the new stuff.

---

## The helper function — why it looks defensive

```python
def show_python_code_and_result(response):
    for i in range(len(response)):
        if (
            (response[i].content.parts)
            and (response[i].content.parts[0])
            and (response[i].content.parts[0].function_response)
            and (response[i].content.parts[0].function_response.response)
        ):
            response_code = response[i].content.parts[0].function_response.response
            if "result" in response_code and response_code["result"] != "```":
                if "tool_code" in response_code["result"]:
                    print("Generated Python Code >> ", response_code["result"].replace("tool_code", ""))
                else:
                    print("Generated Python Response >> ", response_code["result"])
```

**First principle:** when ADK runs an agent, `response` is a list of *events* from that turn. An event isn't just plain text — `event.content.parts` is a list, and each "part" can be different things: a text chunk, a function **call** the model wants to make, or a function **response** (a tool's result being fed back in). Not every part has every attribute populated — a text-only part has no `function_response` at all.

That's why the `and` chain exists: each `and` is a guard that stops you from reaching into `None` and crashing with `AttributeError`. You're walking down `parts[0] → function_response → response`, and at every step you confirm "does this even exist" before going one level deeper.

The bit checking for `"tool_code"` is specific to the **code executor** tool (`BuiltInCodeExecutor`) — it's distinguishing "this is literally generated Python source" from "this is the printed result of running that code," so it can label the print accordingly.

**Why it's in this file at all:** this currency agent never uses a code executor — it has its own two custom function tools instead. This helper is leftover from the notebook's code-execution example earlier in the course and isn't called anywhere in `currencyconvtagent.py`. Good to recognize, not something to worry about.

---

## Retry config — first-principles reasoning

```python
try_config = types.HttpRetryOptions(
    attempts=5,
    exp_base=3,
    initial_delay=1,
    http_status_codes=[429, 500, 503, 504]
)
```

Any call to the Gemini API can transiently fail — rate-limited (429) or the server is briefly down (500/503/504). Rather than crash the whole agent on one bad network blip, you retry automatically with **exponential backoff**: wait `initial_delay` seconds, then `initial_delay × exp_base`, then `× exp_base²`, up to `attempts` tries total. Backing off exponentially (instead of retrying instantly in a loop) avoids hammering a server that's already struggling. This object gets handed to the `Gemini(...)` model wrapper later — it's purely a resilience layer around the network call, not agent logic.

---

## The custom tools — the actual core of this file

### Why a Python function can become a "tool" at all

An LLM can't execute code. What actually happens:

1. ADK reads the function's **name**, **type hints**, and **docstring**, and turns that into a schema (think: a JSON description of "here's a function called X, it takes a string called `method`, here's what it does").
2. That schema gets included in what's sent to the model. When the model decides it needs this capability, it doesn't run anything — it outputs a structured message saying "call `get_fee_for_payment_method` with `method="platinum credit card"`".
3. ADK intercepts that, actually runs your real Python function with those arguments, and feeds the **return value** back into the conversation so the model can read it and keep reasoning.

This is why the docstring isn't decoration — it's the only thing telling the model what the parameter means and what format to use.

### Tool 1: `get_fee_for_payment_method`

```python
def get_fee_for_payment_method(method: str) -> dict:
    """Looks up the transaction fee percentage for a given payment method.
    ...
    Args:
        method: The name of the payment method. It should be descriptive,
                e.g., "platinum credit card" or "bank transfer".
    Returns:
        Dictionary with status and fee information.
        Success: {"status": "success", "fee_percentage": 0.02}
        Error: {"status": "error", "error_message": "Payment method not found"}
    """
```

- `method: str` and `-> dict` are **type hints**. ADK uses these to build the function's schema — it tells the model exactly what kind of value to pass in and what shape to expect back.
- The `Args:` section in the docstring is literally what the model reads to know *what* `method` is supposed to contain and *how* to phrase it (descriptive strings like `"bank transfer"`, not arbitrary codes).
- The `Returns:` section documenting both a success and an error shape is the **contract** for the response. Since the model has to *read and interpret* the output, returning a plain number (`0.02`) would give it no way to tell "fee is 2%" apart from "this errored." Wrapping everything in `{"status": ..., ...}` is a deliberate design pattern: it lets the agent's instructions say "check the status field" and branch accordingly.

```python
    fee_database = {
        "platinum credit card": 0.02,
        "gold debit card": 0.035,
        "bank transfer": 0.01,
    }

    fee = fee_database.get(method.lower())
    if fee is not None:
        return {"status": "success", "fee_percentage": fee}
    else:
        return {
            "status": "error",
            "error_message": f"Payment method '{method}' not found",
        }
```

- `fee_database` is a stand-in for "in production this would be a real database/API call." Hardcoded here just to simulate the lookup.
- `.lower()` on the input: you don't control exactly how the model will phrase what it passes in (`"Platinum Credit Card"` vs `"platinum credit card"`), so you normalize on the receiving end instead of relying on the model to match case exactly.
- `.get(...)` instead of `fee_database[...]`: `.get()` returns `None` on a missing key instead of throwing `KeyError`. That lets you turn "not found" into a clean `{"status": "error", ...}` response instead of crashing the agent mid-run.

### Tool 2: `get_exchange_rate`

```python
def get_exchange_rate(base_currency: str, target_currency: str) -> dict:
    """...
    Args:
        base_currency: The ISO 4217 currency code ... (e.g., "USD").
        target_currency: The ISO 4217 currency code ... (e.g., "EUR").
    Returns:
        Success: {"status": "success", "rate": 0.93}
        Error: {"status": "error", "error_message": "Unsupported currency pair"}
    """
    rate_database = {
        "usd": {
            "eur": 0.93,
            "jpy": 157.50,
            "inr": 83.58,
        }
    }

    base = base_currency.lower()
    target = target_currency.lower()

    rate = rate_database.get(base, {}).get(target)
    if rate is not None:
        return {"status": "success", "rate": rate}
    else:
        return {
            "status": "error",
            "error_message": f"Unsupported currency pair: {base_currency}/{target_currency}",
        }
```

Same pattern, one extra wrinkle: this is a **two-key lookup** (you need a base *and* target currency), so `rate_database` is nested — `{base: {target: rate}}`. The chain `rate_database.get(base, {}).get(target)` is doing the same "don't crash on a missing key" trick twice in a row:

- `.get(base, {})` — if `base` (e.g. `"gbp"`) isn't in the outer dict, return an empty dict `{}` instead of `None`.
- `.get(target)` — call `.get()` on whatever the first step returned. If the first step *had* returned `None` instead of `{}`, this second `.get()` would crash (`None` has no `.get()`). That's exactly why the empty-dict default matters — it keeps the chain safe even when the outer key is missing.

---

## The agent itself

```python
currency_agent = LlmAgent(
    name="currency_agent",
    model=Gemini(model="gemini-2.5-flash-lite", retry_options=try_config),
    instruction="""You are a smart currency conversion assistant.
    ...
    """,
    tools=[get_fee_for_payment_method, get_exchange_rate],
)
```

- `model=Gemini(...)` is where `try_config` (the retry settings from earlier) actually gets used — it's passed in here, not applied globally.
- `instruction="""..."""` is the system prompt. Note it explicitly references the tools **by their exact function names** (`` `get_fee_for_payment_method()` ``, `` `get_exchange_rate()` ``) and tells the model the *order* of operations (fee lookup → exchange rate → calculate → report), and explicitly tells it to check the `"status"` field — directly exploiting the dict contract you built into the tools above.
- `tools=[...]` — this is the actual hookup. Just listing the function objects here is what tells ADK "these are available for the model to call"; ADK auto-generates the schemas from their type hints/docstrings as discussed above. No manual JSON schema writing required.

---

## Tying it together

The full loop, end to end:
1. User asks something like *"Convert 500 USD to EUR using my Platinum Credit Card."*
2. The model reads the instruction + tool schemas, decides it needs both tools, and emits function-call requests.
3. ADK runs your real `get_fee_for_payment_method` and `get_exchange_rate` Python functions, gets back status-tagged dicts.
4. Those dicts are fed back to the model as context.
5. The model does the arithmetic itself (fee deduction → conversion) and writes the final answer, following the structure your instruction prescribed (state result first, then show the breakdown).

Nothing here is doing currency math in Python for you — the **tools only fetch data** (fee %, exchange rate); the **model does the calculation** based on what your instruction tells it to compute and how to explain it.