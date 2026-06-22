# ============================================================================
# WHY "SequentialAgent" SHOWS UP CROSSED-OUT (STRIKETHROUGH) IN MY EDITOR
# ============================================================================
#
# It's not an error. It means: "this class still works, but it's deprecated —
# a newer way to do the same job exists, and this one will eventually be
# removed." Code with a deprecation warning still runs fine today.
#
# WHAT REPLACED IT: a class called `Workflow`, introduced in ADK 2.0+.
# `Workflow` lets you build a graph of steps (nodes + edges) instead of a
# fixed list. Think of it like upgrading from a single hallway (one path,
# one direction, no doors) to a building with hallways AND doors that can
# branch, loop back, or split into multiple rooms running at once.
#
# ----------------------------------------------------------------------------
# WHY I DIDN'T MIGRATE TO Workflow HERE — FIRST PRINCIPLES
# ----------------------------------------------------------------------------
#
# Start with what my pipeline actually needs:
#   Outline -> Writer -> Editor
# One direction. No branching. No loops. No step needs to run twice or run
# at the same time as another step. It is, literally, a straight line.
#
# `SequentialAgent` is built to do exactly one thing: run a list of agents,
# one after another, in the exact order I give it — no exceptions, no model
# "deciding" anything about order. That's ALL my pipeline needs. So using
# the fancier `Workflow` class here would add complexity (defining nodes,
# wiring edges by hand) to solve a problem I don't have. It's like buying a
# multi-room house with hallways and doors when all I need is one hallway.
#
# `Workflow` earns its complexity ONLY when the shape of my pipeline stops
# being a straight line. Concretely, I'd reach for `Workflow` instead of
# `SequentialAgent` if I ever needed:
#
#   1. BRANCHING (if/else paths)
#      e.g. "If EditorAgent flags the draft as bad, send it BACK to
#      WriterAgent for another pass. If it's good, move on to publish."
#      A straight list can't express "go back" or "pick path A vs B" —
#      it only ever goes forward through the list.
#
#   2. LOOPS WITH A REAL EXIT CONDITION
#      e.g. "Keep refining the draft until a quality-check function
#      returns True" — not just "repeat exactly 3 times," but an actual
#      runtime decision based on code logic.
#
#   3. MIXING IN PLAIN PYTHON FUNCTIONS AS STEPS (no LLM call at all)
#      e.g. a step that's just `def word_count(text): return len(text.split())`
#      sitting between two agent steps, doing pure deterministic computation
#      with zero model involvement.
#
#   4. PARALLEL FAN-OUT / FAN-IN
#      e.g. running 3 independent agents AT THE SAME TIME, then merging
#      their three outputs into a single next step.
#
# None of these apply to Outline -> Writer -> Editor. So: keep using
# SequentialAgent. Revisit this ONLY if (a) ADK actually removes
# SequentialAgent in some future version I'm forced to upgrade past, or
# (b) I add real branching/looping logic to this specific pipeline.
# ============================================================================