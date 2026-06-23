

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