# ============================================================================
# ARCHITECTURE: PARALLEL FAN-OUT / FAN-IN (ParallelAgent + Aggregator)
# ============================================================================
#
# WHAT THIS DIAGRAM SHOWS:
#
#   User Request: "Research 3 topics"
#            |
#            v
#     Parallel Execution
#       /      |       \
#      v       v        v
#   Tech     Health    Finance
#  Researcher Researcher Researcher
#      \       |        /
#       v      v       v
#         Aggregator
#            |
#            v
#      Combined Report
#
# ----------------------------------------------------------------------------
# HOW THIS IS DIFFERENT FROM SequentialAgent (the straight-line pipeline)
# ----------------------------------------------------------------------------
#
# In SequentialAgent, every step waits for the one before it to finish —
# A -> B -> C, strictly one at a time, like a relay race passing a baton.
#
# Here, that single-file line breaks into THREE lanes at once:
#   TechResearcher, HealthResearcher, and FinanceResearcher all start
#   AT THE SAME TIME, independently, with no dependency on each other's
#   output. None of them needs to wait for the others — they're researching
#   three completely separate topics, so there's no reason to force them
#   into a queue.
#
# This is "fan-out": one upstream trigger (the user request) splits into
# multiple parallel branches.
#
# ----------------------------------------------------------------------------
# WHY THERE'S AN "Aggregator" STEP AT THE END
# ----------------------------------------------------------------------------
#
# Once the three researchers finish (each at their own pace — they might not
# all complete at the exact same millisecond), their three separate outputs
# need to be merged back into ONE final result. That's the Aggregator's job:
# it waits for ALL three branches to complete, then combines their findings
# into a single "Combined Report."
#
# This merge-back-into-one-path step is called "fan-in" — the mirror image
# of fan-out. Fan-out splits one input into many; fan-in collects many
# outputs back into one.
#
# ----------------------------------------------------------------------------
# WHY USE THIS INSTEAD OF JUST RUNNING THEM SEQUENTIALLY?
# ----------------------------------------------------------------------------
#
# Speed. If each researcher takes ~10 seconds to run:
#   - Sequential (one after another): ~30 seconds total (10 + 10 + 10)
#   - Parallel (all at once):          ~10 seconds total (the slowest one)
#
# Since TechResearcher, HealthResearcher, and FinanceResearcher don't depend
# on each other's results (none of them needs another's output to do its own
# job), there's no reason to make them wait in line. Running them
# concurrently cuts total wait time roughly to the duration of the SLOWEST
# single branch, instead of the SUM of all branches.
#
# ----------------------------------------------------------------------------
# WHEN TO REACH FOR THIS PATTERN
# ----------------------------------------------------------------------------
#
# Use parallel fan-out/fan-in when:
#   1. You have multiple independent sub-tasks (no sub-task needs another
#      sub-task's output to begin).
#   2. You eventually need to combine/synthesize their results into one
#      final output.
#   3. Speed matters, and running things one-by-one would waste time
#      waiting on unrelated tasks.
#
# Do NOT use it when one step's output feeds directly into the next step's
# input (that's what SequentialAgent is for), or when only one path should
# ever execute depending on a condition (that's branching — Workflow/graph
# territory).
# ============================================================================