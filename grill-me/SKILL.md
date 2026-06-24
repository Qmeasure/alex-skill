---
name: grill-me
description: Interview the user relentlessly about a plan or design until reaching shared understanding, resolving each branch of the decision tree. Use when user wants to stress-test a plan, get grilled on their design, or mentions "grill me".
---

Interview me relentlessly about every aspect of this plan until we reach a shared understanding. Walk down the design tree, but batch independent questions so progress does not stall.

Use question packets:
- First round: ask 5 high-leverage questions covering goal, constraints, architecture, failure modes, and validation.
- Later rounds: ask 3 focused questions targeting the weakest remaining assumptions.
- Batch only independent or same-level decisions.
- If one unresolved decision blocks all useful follow-up questions, ask only that blocker and explain why.
- Ask questions with popup options whenever the environment provides a popup/user-input tool such as `request_user_input`.
- Each popup question must provide 2-3 meaningful mutually exclusive options and mark the recommended option with `(Recommended)`.
- If no popup/user-input tool is available, fall back to numbered text questions with the same option structure instead of stopping.

For each question, provide:
- your recommended answer
- why the question matters
- what risk appears if the answer is wrong
- how the answer changes the plan, design, or implementation

After each user answer:
- identify contradictions, vague answers, and weak assumptions
- state the conclusions now locked
- revise the plan/design/code direction concretely
- ask the next packet of questions

If the user answers only part of a packet, do not skip the missing parts. State which unanswered items still block the design and ask those next.

Never accept vague answers. Challenge ambiguity directly until the plan is decision-complete.

If a question can be answered by exploring the codebase, explore the codebase instead.
