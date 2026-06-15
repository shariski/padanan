# Feedback Loop Design

This document explains **why** the feedback works the way it does. The mechanics live in [`product-spec.md`](product-spec.md) and the prompt construction lives in [`local-llm-setup.md`](local-llm-setup.md). This document is the rationale layer — read it before changing the output format or the prompt structure.

## The problem the feedback loop has to solve

The developer's main pain is **lexical retrieval**, not grammar. Retrieval failures show up as:

- Pauses while the brain searches for a word that exists in passive vocabulary but is not coming up
- Settling for a vague word ("make it faster") instead of the precise word that was almost there ("reduce tail latency")
- Producing a technically correct but flat answer that does not sound like a senior IC

Telling someone "you should have said tail latency" is **recognition**, not retrieval. The next time, the gap will be in a different place, and the lesson does not generalize.

The feedback design therefore aims for two things that recognition-only feedback does not give:

1. **Contextual contrast**: show the gap *inside the same answer*, not as an abstract rule. "Your answer said X. A senior-IC answer would say Y. The reason is Z." That's harder to skim past than a vocab card.
2. **Pattern visibility**: over many sessions, the same kinds of words should recur as gaps. Even without an SRS system in MVP, just seeing the same gap three sessions in a row is a strong signal to the developer's brain.

## Why "comparative output" instead of "list of errors"

Two reasons.

**First, errors framing is wrong.** At B2 upper, the speaker is not *making errors* most of the time. The answer is grammatical and intelligible. The issue is that it is one register below where it should be. "Errors" is the wrong word for register mismatch. "Upgrade" is the right word.

**Second, side-by-side reveals more than a list.** A list of gaps tells the speaker which words to swap. A side-by-side upgrade also reveals:

- Better sentence structures (replacing "the system is then doing X" with "the system then X-s")
- Discourse markers a senior IC reaches for ("to be precise", "the trade-off here is", "we'd want to instrument…")
- Where the speaker over-explained, where they under-explained, where they should have hedged

The lexical-gaps list is the headline. The full upgraded version is the textbook.

## Why a small `indonesian_isms` section, separately

At B2 upper, Indonesian-isms are subtle: maybe one or two per 90-second answer. Things like:

- Treating non-count nouns as count ("informations", "feedbacks")
- Subject drop that works in Bahasa but reads as ambiguous in English
- Direct translations of Indonesian discourse particles ("how if we…" for "what if we…")

Lumping these with general lexical gaps would bury them in noise. Calling them out separately gives the developer a faster signal — these are the cases where Indonesian is leaking through, and they're the ones that probably feel hardest to self-detect.

If the LLM doesn't find any, the section is hidden. No empty section as filler.

## Why a separate `content_feedback` section — and why it only flags, never grades

The original design above deliberately stopped at *how* the answer is phrased and assumed the *content* was roughly right. Dogfooding showed that wasn't enough: for interview prep the developer also needs to know what a strong answer would have covered that they missed, where their reasoning was thin, and which claims might be wrong. So a third dimension was added — `content_feedback`, a list of `{kind, note}` items:

- **missing** — an important point a strong senior answer to this prompt would cover that wasn't raised.
- **weak** — a point that was raised but left thin or unjustified.
- **check** — a specific claim that looks questionable, phrased as *"Verify whether…"*.

Two rules keep this from backfiring:

1. **It is separate from the lexical analysis.** The `upgraded_version` still preserves the speaker's content — it never silently rewrites their *ideas*. Content issues live only in `content_feedback`. Mixing the two would muddy both: you couldn't tell a vocabulary suggestion from a substance disagreement.
2. **It flags, it does not grade.** `check` items are framed as things to verify, never verdicts. Judging technical correctness is the single hardest thing for a small local model, and a *confidently wrong* correction right before an interview is worse than none — so the section prompts the developer's own judgment rather than asserting truth. If correctness depth ever proves insufficient, the lever is a larger MLX model, then cloud-for-content — not loosening this framing.

This is the one place the app crosses from "language coach" toward "mock interviewer" — and it does so cautiously, on purpose.

## Why no error counts, no scores, no progress meter

A few reasons:

- **Score-chasing changes behavior in the wrong direction.** Speakers start optimizing for the score (using fewer simple words to avoid being flagged) instead of for fluency.
- **Local model judgments are not stable enough to compare across sessions.** A "7 gaps last session, 4 this session" comparison would be noise.
- **It's not the bottleneck.** The bottleneck is the developer noticing the gap in context, not measuring himself.

This is a deliberate cut, not a "v2 feature." If it ever appears in the codebase, push back.

## Why no real-time / interrupt feedback

The temptation is "show feedback as the speaker pauses, in real time." Resisted for three reasons:

1. **Interrupting a speaker mid-answer kills the actual skill being practiced**, which is sustained answer delivery under time pressure.
2. **Real-time feedback requires streaming transcription and streaming LLM**, both of which are doable but expensive in scope. Out for week one.
3. **In a real interview, no one interrupts you with corrections.** Practicing in conditions less realistic than the real thing is a bad use of practice budget.

The feedback comes after Stop. The speaker gets the full uninterrupted answer, then the comparative output.

## Why short clips (60–120s) are the design point

Two reasons.

- **Interview answers are bursts.** A behavioral STAR answer is 90 seconds. A system design opening overview is 60–90 seconds. A whiteboard-walkthrough subsection is 60–120 seconds. Practicing in this range matches the actual unit of speech being practiced.
- **Local model latency.** Whisper large-v3 on M4 16GB transcribing 90 seconds of audio is acceptable (probably 5–15 seconds, to be measured). Qwen3.5 9B via MLX analyzing a 90-second transcript is acceptable (a short transcript measured ~44s end-to-end; 90s to be measured). 300-second clips would stretch this past the patience threshold.

The UI does not hard-cap at 120s — speakers sometimes need more — but the design point is short bursts.

## Why retry-same-prompt is a first-class button

Retrying the same prompt with the feedback fresh in mind is the **only** mechanism in MVP that approximates active recall. There is no SRS, no spaced re-prompting. But re-recording the same answer 30 seconds after seeing the upgrade is a tight loop that gives the developer something to do *immediately* with the feedback.

This is the most important UX detail in the app. Do not bury it in a menu.

## What "good feedback" looks like — worked example

Prompt: *"Walk me through how you'd design a URL shortener for a service expecting 100M URLs."*

Speaker's actual answer (simulated):

> "Okay so first we need a service that takes a long URL and returns a short one. We probably want a database to store the mapping. The short URL needs to be unique. We could use base62 encoding of an auto-incrementing ID. For scale, we'd need to make it fast — maybe a cache in front of the database. Also we need to handle the case where many people read the same short URL, so the cache helps with that too."

Useful feedback output:

```json
{
  "upgraded_version": "Right, so we're designing a write-light, read-heavy key-value mapping service. The core is a bidirectional mapping between a long URL and a short slug. To generate slugs, base62 encoding of a monotonically increasing ID is a reasonable starting point — it gives us roughly 3.5 trillion six-character slugs, which comfortably covers 100M. For the read path, we'd want an aggressive cache in front of the primary store; given the typical Zipfian access pattern for shortened URLs, a relatively small cache absorbs the vast majority of reads.",
  "lexical_gaps": [
    { "spoken": "make it fast", "suggested": "optimize the read path / reduce p99 latency", "reason": "specifying which dimension of 'fast' signals systems thinking" },
    { "spoken": "many people read the same short URL", "suggested": "the access distribution is Zipfian / hot keys dominate reads", "reason": "naming the access pattern is what senior engineers do — it shows you've seen this before" },
    { "spoken": "we need a database to store the mapping", "suggested": "we need a primary store for the bidirectional mapping", "reason": "'primary store' invites the follow-up 'and what about the secondary?' which lets you talk about caching naturally" },
    { "spoken": "an auto-incrementing ID", "suggested": "a monotonically increasing ID", "reason": "the term is the same idea but lives in the senior-IC vocabulary" }
  ],
  "indonesian_isms": [],
  "content_feedback": [
    { "kind": "missing", "note": "You never addressed how slugs stay unique under concurrent writes — a senior answer names the ID-generation or collision strategy." },
    { "kind": "check", "note": "Verify whether a single auto-increment counter holds at 100M-scale write rates; at high QPS that counter is often the bottleneck." }
  ],
  "overall_note": "The answer covers the right ground but reads as junior-mid because key technical terms ('Zipfian', 'p99', 'monotonic') are absent. The structure is sound — the upgrade is mostly vocabulary at the noun-phrase level."
}
```

That `overall_note` is the most actionable single sentence. Aim for it to be that pointed.

## What "bad feedback" would look like — anti-pattern

Avoid output like this:

```json
{
  "overall_note": "Good answer! You covered the main points. Consider using more technical vocabulary and being more specific. Practice will help.",
  "lexical_gaps": [
    { "spoken": "the", "suggested": "the", "reason": "no change needed" },
    { "spoken": "we need a service", "suggested": "we require a service", "reason": "more formal" }
  ]
}
```

Specifically wrong:

- **Empty praise** ("Good answer!"). Cut it.
- **Generic exhortation** ("Practice will help"). Cut it.
- **Trivial swaps** ("need" → "require"). These add noise. The prompt should explicitly instruct the model not to suggest swaps that don't change the register or precision meaningfully.
- **Padding the gap list**. If there are 3 real gaps, return 3, not 8.

The prompt in `local-llm-setup.md` is engineered to suppress these patterns. If the model produces them anyway, that's signal that the prompt needs to be tightened or the model is too weak — log it and surface it during dogfooding.

## What gets measured (manually) during dogfooding

No metrics dashboard. After every dogfooding session, the developer writes one line in `docs/dogfooding.md`:

- Did the comparative upgrade teach something? (yes / no / partial)
- Were the lexical gaps real, or did some feel forced? (real / forced / mix)
- Were any Indonesian-isms flagged, and were they accurate?
- One sentence on the most useful suggestion of the session

After 3–5 dogfooding sessions, the developer reads the file as a whole and decides if the feedback is good enough to keep the design, or if the prompt / model needs to change.
