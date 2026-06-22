---
name: strategic-prompt-writer
description: Write prompts at the strategic/methodology level instead of the prescriptive task level. Use this skill ONLY when the user is explicitly asking you to write, draft, generate, design, or improve a prompt that will be given to another AI model (Claude, GPT, etc.) to execute a task. Trigger phrases include "帮我写个 prompt", "写一段提示词", "写一个让 Claude/GPT 做 X 的 prompt", "draft a prompt for…", "write a system prompt that…", "design a prompt to make the model…", or any request where the explicit deliverable is a prompt for an AI executor. Do NOT trigger for general instruction-writing, workflow documentation, role descriptions for humans, or tasks where "prompt" is not the explicit deliverable — only when the user is clearly asking for AI-executor prompt text.
---

# Strategic Prompt Writer

## Why this skill exists

The default failure mode when an AI writes prompts for another AI is **over-specification**. The author tries to be helpful by spelling out exactly what each section should say, what bullet points to include, what examples to use, what tone each paragraph should hit. The result looks thorough but is actually fragile: it collapses the moment the input doesn't match the imagined input, and it strips the executing model of the judgment it was supposed to apply.

A good prompt does the opposite. It tells the executor **where to aim** — the goal, the audience, the constraints, the methodology, the success criteria — and trusts the executor to figure out **what to actually write** given the specific input in front of it.

The mental model: you are writing a **briefing for a competent professional**, not a **fill-in-the-blank template**.

## The two-line test

Before delivering any prompt, check it against these two lines. If it fails either, rewrite.

1. **Generality test** — If the input situation changes (different topic, different user, different data), does this prompt still produce a sensible output? Or does it only work for one narrow imagined input?
2. **Direction-vs-content test** — Does the prompt tell the executor *where to write toward* (goals, methodology, constraints, criteria) rather than *what specifically to write in each section* (exact headings, exact bullet points, exact phrasings)?

If a prompt only works because the author guessed the exact input correctly, it's brittle. If a prompt prescribes the content of every section, it's not a prompt — it's a fill-in-the-blank form, and you should just write the output directly instead.

## What to include in a prompt

Include things that **shape direction without dictating content**:

- **Role / persona** — who the executor is acting as, and what stance/expertise that implies
- **Goal** — what success looks like for the end user, in one sentence
- **Audience** — who reads the output and what they need from it
- **Methodology** — the *approach* to use (first principles, comparative analysis, working backward from the user, etc.), not the *steps* to follow
- **Constraints** — hard limits (length, format, things to avoid, things that are out of scope)
- **Quality bar** — what distinguishes a good output from a mediocre one in this domain
- **Failure modes to avoid** — common traps the executor should sidestep

## What to leave out

Deliberately omit things that **belong to the executor's judgment**:

- Section-by-section content lists ("the intro should mention X, then Y, then Z")
- Exact phrasings, sentence templates, or example sentences the executor should reproduce
- Specific examples of the answer (these anchor the executor and reduce variance, which is usually bad)
- Word-by-word tone instructions when "tone: [adjective]" would do
- Step counts ("write exactly 5 bullet points") unless the count is a real constraint, not a guess

When in doubt, ask: *is this a property of the goal, or a property of one imagined answer?* Goal-properties belong in the prompt. Answer-properties don't.

## The two failure modes, illustrated

**Failure mode 1: Prescriptive content spec (too specific)**

> Write a market analysis. Start with "The market for X has grown significantly in recent years." Then add a paragraph about market size citing IDC and Gartner. Then list the top 5 players: Company A, Company B, Company C, Company D, Company E. Then write about growth drivers including AI, cloud, and regulation. Then conclude with a recommendation to invest.

This isn't a prompt; it's a draft with blanks. It only works if the market is actually growing, if IDC/Gartner cover it, if those 5 companies are actually the top players, and if investment is the right conclusion. Change any of those and the prompt produces nonsense.

**Failure mode 2: Strategic brief (what we want)**

> You are an industry analyst writing a market analysis for an investor deciding whether to allocate capital to this sector. Goal: give them enough structural understanding of the market to make a go/no-go judgment, not a complete encyclopedia.
>
> Methodology: work from market structure outward — who are the players, what does the value chain look like, where does margin pool, what's changing. Prioritize structural facts over headline numbers.
>
> Constraints: assume the reader knows public-equity investing but not this specific industry. Length: whatever the analysis genuinely needs, but don't pad. Avoid vague growth language ("rapidly evolving", "transformative") unless backed by a specific mechanism.
>
> Quality bar: an investor reading this should be able to name the two or three structural questions that determine whether this sector is investable, and should know what evidence would resolve them.

Notice what this prompt does *not* do: it doesn't tell the executor which companies to mention, what the conclusion should be, what the market size figure is, or what section headers to use. Those are the executor's job, conditional on the actual research.

## Process when writing a prompt

1. **Understand the actual goal.** What does the end user of the prompt's output actually need? Not "an essay" — what decision or action does the output enable? If you can't answer this in one sentence, ask the user before writing the prompt.

2. **Identify the methodology.** What's the *right way to think* about this kind of task? Frame the prompt around that thinking process, not around an imagined output shape.

3. **Draft strategically.** Write role, goal, audience, methodology, constraints, quality bar. Resist the urge to add "section 1 should say…".

4. **Apply the two-line test.** Read your draft. Would it survive a different input? Does it direct rather than prescribe? Cut anything that fails.

5. **Prefer underspecification to overspecification.** When uncertain whether to include a detail, leave it out. The executor's judgment will fill the gap better than your guess will.

## A note on format

Default to plain prose paragraphs grouped under short headings (Role, Goal, Methodology, etc.). Heavy XML scaffolding and elaborate templates are usually a sign of over-engineering — they make the prompt look serious without making it more effective. Use structure only where it genuinely helps the executor parse the brief.

Match the language of the user's request: if they wrote to you in Chinese, write the prompt in Chinese; if English, English.
