# Understanding `agent.py`: From `__main__` to Image File

This walks through exactly what happens when you run `python3 agent.py` and ask for a tiny image — from the `__name__ == "__main__"` guard, through the event loop, to the final `subprocess.run()` call.

---

## 1. Why `if __name__ == "__main__":` is there at all

Python sets the built-in `__name__` variable differently depending on **how a file got launched**:

| How the file runs | `__name__` value | Result |
|---|---|---|
| `python3 agent.py` (run directly) | `"__main__"` | block **runs** |
| `adk web` imports it (`import agent`) | `"agent"` | block **skipped** |

`adk web` doesn't execute your script — it **imports** it just to grab the `root_agent` (or `image_agent`) variable out of it. If your terminal-testing code (`input()`, running the agent, etc.) weren't wrapped in this guard, it would fire the moment `adk web` imported the file — freezing on `input()` while waiting for terminal input that would never come.

So this guard means: *"only run this block when I launch this file myself — stay silent if something else just imports me."*

```python
if __name__ == "__main__":
    question = input("Ask your agent something: ")
    ...
```

`question` is just a plain string — your input *into* the agent. It is **not** part of the response/event structure below; it gets consumed immediately by `run_debug()`.

---

## 2. The runner and the `async` requirement

```python
runner = InMemoryRunner(agent=image_agent)

async def main():
    response = await runner.run_debug(question, verbose=True)
```

- `InMemoryRunner` is the engine that actually drives the agent: sends your question to the LLM, executes any tool calls the LLM decides to make, feeds the results back, and repeats until a final text answer comes out.
- `run_debug()` is `async` because it involves waiting on network round-trips (to Gemini's API, and to the MCP server process). `async def main()` just **defines** this behavior — it doesn't run anything by itself.
- `await` pauses execution right there until the **entire** agent run finishes, and only then returns `response` — a **list of events**, one per step the agent took.

---

## 3. The three events, concretely

For an image request, the agent typically produces exactly three events:

### Event 1 — model decides to call a tool
```python
event.content.parts = [
    Part(function_call=FunctionCall(name="getTinyImage", args={}))
]
```
A *request*, not a result. Has `function_call`, **not** `function_response`.

### Event 2 — the tool's result comes back
```python
event.content.parts = [
    Part(function_response=FunctionResponse(
        name="getTinyImage",
        response={
            "content": [
                {"type": "text", "text": "Here's the image you requested:"},
                {"type": "image", "data": "<base64 bytes>", "mimeType": "image/png"}
            ]
        }
    ))
]
```
This is the **only** event that contains the data we actually want.

### Event 3 — the model's final reply to you
```python
event.content.parts = [
    Part(text="Here's the image you requested: The image above is the MCP logo.")
]
```
Plain text. No function call, no function response — this is what shows up as the chat bubble.

---

## 4. Walking the nested loop against these 3 events

```python
for event in response:
    if event.content and event.content.parts:
        for part in event.content.parts:
            if hasattr(part, "function_response") and part.function_response:
```

| Event | Has `function_response`? | Outcome |
|---|---|---|
| 1 (function call) | No (`None`) | skipped |
| 2 (function result) | **Yes** | enters the block |
| 3 (final text) | No | skipped |

Only Event 2 survives this filter — that's the entire purpose of checking `function_response`: ignore the call itself and the final text, find only the tool's actual returned data.

### Inside Event 2

```python
for item in part.function_response.response.get("content", []):
```
- `.response` is the dict `{"content": [...]}`.
- `.get("content", [])` defensively returns an empty list if `"content"` were ever missing, instead of crashing with a `KeyError`.
- The list holds MCP's **typed content blocks** — here, one `"text"` block and one `"image"` block.

```python
    if item.get("type") == "image":
```
- The `"text"` block → `False` → skipped.
- The `"image"` block → `True` → **this is the one piece of data, out of the entire 3-event response, that the rest of the code acts on.**

---

## 5. Decoding and saving the image

```python
image_bytes = base64.b64decode(item["data"])
```
MCP sends images as base64 **text**, since raw binary can't travel inside JSON. Decoding converts that text back into actual raw image bytes.

```python
output_path = "output.png"
with open(output_path, "wb") as f:
    f.write(image_bytes)
```
Plain file I/O — write the bytes to disk as a real `.png` file. This works identically in a notebook, a terminal, or anywhere else — unlike `IPython.display()`, which only renders inside a Jupyter/Colab frontend and does nothing silently elsewhere.

```python
print(f"✅ Image saved to {output_path}")
```

---

## 6. `subprocess.run(["open", output_path])` — what this actually does

This line asks the **operating system**, not Python, to open the file — equivalent to double-clicking it in Finder.

- `subprocess` is Python's module for launching other programs as separate OS processes.
- `"open"` is a macOS command-line utility whose job is "open this file with whatever app is registered for its type" — for `.png`, that's Preview.
- The argument is passed as a **list** (`["open", output_path]`) rather than one combined string. This bypasses the shell entirely and avoids issues if the filename ever contained spaces or special characters — the safer, recommended way to call subprocesses.
- `open` hands off to Preview and returns immediately itself — it does **not** wait for you to close the image window. Your script isn't blocked; Preview keeps running as its own independent process afterward.

---

## 7. Starting the async machinery

```python
asyncio.run(main())
```
`async def main()` only *defines* a coroutine — it does nothing on its own. `asyncio.run(...)` is what actually creates an event loop and executes `main()` inside it, blocking here until `main()` fully completes.

---

## Full annotated script

```python
if __name__ == "__main__":
    # Runs only when this file is launched directly (python3 agent.py).
    # Skipped when adk web imports this file to grab root_agent/image_agent.

    question = input("Ask your agent something: ")
    # Your input. NOT part of the event loop below — consumed by run_debug().

    runner = InMemoryRunner(agent=image_agent)
    # Drives the agent: sends your question, executes tool calls, loops until
    # a final text answer is produced.

    async def main():
        # async because run_debug() involves network round-trips.

        response = await runner.run_debug(question, verbose=True)
        # Pauses here until the ENTIRE run finishes. Returns a list of events:
        #   Event 1: function_call  -> model requests getTinyImage
        #   Event 2: function_response -> tool's actual result comes back
        #   Event 3: plain text -> model's final reply to you

        for event in response:
            if event.content and event.content.parts:
                for part in event.content.parts:

                    if hasattr(part, "function_response") and part.function_response:
                        # Only Event 2 passes this check.
                        # Event 1 has function_call (not function_response) -> skipped
                        # Event 3 has plain text (no function_response)     -> skipped

                        for item in part.function_response.response.get("content", []):
                            # content = [{"type": "text", ...}, {"type": "image", ...}]

                            if item.get("type") == "image":
                                # Only the image block passes; the text block is skipped.

                                image_bytes = base64.b64decode(item["data"])
                                # base64 text -> real binary image bytes

                                output_path = "output.png"
                                with open(output_path, "wb") as f:
                                    f.write(image_bytes)
                                # Write bytes to an actual file (works anywhere,
                                # unlike IPython's notebook-only display())

                                print(f"✅ Image saved to {output_path}")

                                subprocess.run(["open", output_path])
                                # Ask macOS to open the file with Preview.
                                # List form avoids shell-parsing issues.
                                # Returns immediately — doesn't block the script.

    asyncio.run(main())
    # Actually starts the event loop and runs main() to completion.
```