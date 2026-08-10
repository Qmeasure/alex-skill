# Themes

Set one theme in front matter:

```md
---
title: 一份公司研究
theme: finance
---
```

All themes use the same Markdown syntax, components, pagination, fixed footer, and page-number behavior.

## Theme selection

- `classic` — Warm ivory, gold marker accents, and hand-drawn details. Use by default, for general explainers, case studies, GEO/AI education, and existing carousels that must retain the established identity.
- `finance` — Cool paper, navy structure, restrained gold, and sharper rules. Use for company research, earnings, valuation, IPO, markets, and investment frameworks.
- `editorial` — Warm paper, vermilion accents, serif display type, and magazine-like section treatments. Use for opinion, interviews, brand stories, industry narratives, and long-form editorial posts.
- `tech` — Dark navy, cyan highlights, a subtle grid, and luminous data accents. Use for AI, chips, software, infrastructure, model comparisons, and technical explainers.

## Rules

- Keep one theme for the entire carousel.
- Do not infer `tech` merely because the article mentions AI; prefer `classic` for approachable education and `tech` for explicitly technical or futuristic positioning.
- Prefer `finance` for investment research even when the company is a technology company.
- Preserve `classic` when revising an existing input without a theme field.
- Reject unknown theme names instead of silently falling back.
