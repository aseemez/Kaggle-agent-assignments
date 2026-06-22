# ============================================================================
# ARCHITECTURE: BLOG POST CREATION PIPELINE (SequentialAgent, straight line)
# ============================================================================
#
# WHAT THIS DIAGRAM SHOWS:
#
#   User Input: "Blog about AI"
#         |
#         v
#   Outline Agent --[blog_outline]--> Writer Agent --[blog_draft]--> Editor Agent --[final_blog]--> Output
#
# This is the simplest possible shape: ONE path, ONE direction, no branches,
# no loops, no parallel lanes. Each box is a single agent. Each label on an
# arrow (blog_outline, blog_draft, final_blog) is the `output_key` that
# agent writes its result to — and that's exactly the variable name the
# NEXT agent reads back via the {placeholder} syntax in its instruction.
#
# ----------------------------------------------------------------------------
# HOW DATA ACTUALLY MOVES BETWEEN BOXES (THE PART THAT'S EASY TO MISS)
# ----------------------------------------------------------------------------
#
# The arrows in this diagram aren't just "then this runs" — they represent
# real data being handed off through ADK's shared session state:
#
#   1. OutlineAgent runs first. It writes its result into state under the
#      key "blog_outline" (because output_key="blog_outline" on that agent).
#
#   2. WriterAgent runs next. Its instruction string contains the literal
#      text "{blog_outline}" somewhere — ADK automatically swaps that
#      placeholder out for whatever OutlineAgent just wrote to state. The
#      WriterAgent never "asks" for it explicitly; ADK does the substitution
#      before the prompt even reaches the model.
#
#   3. WriterAgent then writes ITS result to state under "blog_draft".
#
#   4. EditorAgent's instruction contains "{blog_draft}" — same automatic
#      substitution happens, and EditorAgent polishes that draft, writing
#      the final result to "final_blog".
#
#   5. "final_blog" is what gets shown to the user as Output.
#
# This output_key -> {placeholder} relay is THE mechanism that makes a
# sequential pipeline actually useful — without it, each agent would run
# in total isolation with no memory of what the previous agent produced.
#
# ----------------------------------------------------------------------------
# WHY THIS IS A GOOD FIT FOR SequentialAgent (no Workflow/graph needed)
# ----------------------------------------------------------------------------
#
# Every single step here STRICTLY depends on the one before it:
#   - WriterAgent can't write anything until it has an outline.
#   - EditorAgent can't edit anything until a draft exists.
# There's no independent work happening anywhere (compare this to the
# Tech/Health/Finance researcher diagram, where three agents had NO
# dependency on each other and could run at once). Because every step here
# genuinely needs the previous step's exact output before it can start,
# forcing them into a strict one-after-another order isn't a limitation —
# it's just an accurate description of how the work actually has to happen.
#
# That's the test for "do I need SequentialAgent (or eventually Workflow)
# vs. ParallelAgent": ask whether step N actually needs step N-1's result
# to do its job. If yes for every step -> sequential. If some steps don't
# need each other's results at all -> consider parallel fan-out instead.
# ============================================================================