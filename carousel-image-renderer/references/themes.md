# Themes

Set one theme in front matter:

```md
---
title: 一份公司研究
theme: finance
---
```

Both themes use the same Markdown syntax, components, pagination, fixed footer, and page-number behavior.

## Theme selection

- `finance` — Default. Use a professional financial-news look with cool paper, navy structure, restrained gold, and sharp information hierarchy. Use for market updates, company research, earnings, valuation, investment frameworks, industry narratives, and most AI-investment coverage.
- `tech` — Use a dark navy, cyan-highlighted, grid-based look for strongly technical AI topics such as models, chips, computing infrastructure, software architecture, and technical comparisons.

## Rules

- Keep one theme for the entire carousel.
- Use `finance` when the theme field is omitted.
- Do not infer `tech` merely because an article mentions AI; use it only when the subject and framing are explicitly technical or futuristic.
- Prefer `finance` whenever investment relevance, market impact, valuation, company performance, or industry economics drives the story, including technology-company coverage.
- Migrate legacy `classic` and `editorial` inputs to `finance`; do not preserve removed theme names.
- Reject unknown theme names instead of silently falling back.
