# Why ADK Introduced Graph-Based `Workflow`

## The short answer

You *can* fake branching and loops by nesting `SequentialAgent`, `ParallelAgent`, and
`LoopAgent` inside a hand-written `CustomAgent`. The problem isn't that it's
*impossible* — it's that doing so forces you outside ADK's structured framework into
raw Python control flow, losing the benefits the framework gives you for free.

## What breaks down with the old templates

1. **No native branching.** None of the three templates has an `if/else` primitive.
   To route conditionally, you must drop into a `CustomAgent` and manually check
   `session.state`, then call the right sub-agent yourself.
2. **Shape becomes invisible.** Nesting templates inside a `CustomAgent` means the
   real flow only exists implicitly in code — you have to read it to reconstruct
   what the pipeline does. A real graph (explicit nodes + edges) is data ADK's
   tooling can visualize and inspect.
3. **Fixed-size composition.** `ParallelAgent`'s sub-agent list is fixed at
   construction time — dynamic fan-out (e.g. "however many topics the user
   mentions") needs a hand-rolled workaround every time.
4. **No built-in resumability.** A graph engine can checkpoint its exact position
   and resume after a crash or human-approval pause. A nested pile of templates has
   no uniform "current position" concept.

## Takeaway

Graph-based `Workflow` brings branching and loops *inside* the same inspectable,
observable, resumable system — instead of forcing you to abandon it the moment your
pipeline isn't perfectly linear, fixed-parallel, or a simple loop.

For a straight pipeline like `Outline -> Writer -> Editor`, `SequentialAgent` is
still the right, simplest tool. Reach for `Workflow` only when the shape itself
needs branching, dynamic fan-out, or loops with real exit conditions.

---

# Architecture: Story Writing & Critique Loop (`LoopAgent`)

```
Initial Prompt
      |
      v
 Writer Agent  <---------------+
      | story                  |
      v                        | Yes
 Critic Agent                  |
      | critique                |
      v                        |
 Iteration < Max AND Not Approved?
      | No
      v
 Final Story
```

**What's happening:** `Writer Agent` and `Critic Agent` are wrapped in a `LoopAgent`.
Each pass: Writer produces a story, Critic produces a critique, then a check decides
whether to loop back or stop.

**The exit condition is two things ANDed together:**
- `Iteration < Max` — a hard ceiling (e.g. 5 attempts), so the loop can never run
  forever even if the critic is never satisfied.
- `Not Approved` — the actual quality gate. If the critic is happy, this becomes
  false and the loop exits even if iterations remain.

If **either** condition fails — max iterations hit, or critic approves — the loop
exits ("No") and the story moves on as final. Otherwise ("Yes") control goes back to
Writer Agent with the critique in hand, and another pass begins.

**Why `LoopAgent` fits here, no `Workflow`/graph needed:** this is a repeating
two-step cycle with one exit condition, exactly what `LoopAgent` is built for —
deterministic iteration count plus an early-exit signal from a sub-agent. You'd only
reach for graph-based `Workflow` if you needed something `LoopAgent` can't express,
e.g. routing to a *different* agent depending on *why* the critique failed (tone vs.
plot vs. grammar), rather than just looping the same two agents.