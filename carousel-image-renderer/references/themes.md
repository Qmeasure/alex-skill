# Themes

Set one theme in front matter:

```md
---
title: 一份公司研究
theme: finance
---
```

Both themes use the same Markdown syntax, components, pagination, fixed author lockup, fixed footer, and page-number behavior.

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
- Keep the bundled 李菲特 avatar and fixed author name in the top-left of every page; theme only the outline and shadow, not the portrait.

## Typography

- Require locally installed `Source Han Sans SC` and `Source Han Serif SC`; do not declare fallback families.
- Use Source Han Sans SC for body copy, cover subtitles, metrics, tables, callouts, risks, sources, code, and footers in both themes.
- In `finance`, use Source Han Serif SC for the cover title, section headings, Markdown headings, and short lead blocks. This maps serif type to narrative turns and sans type to facts and analysis.
- In `tech`, use Source Han Sans SC for both display and body roles.
- Set body copy to 38px with 1.62 line height. Keep serif display copy short and use loaded SemiBold, Bold, or Heavy faces.
- Treat any missing required face as a render error; never continue with browser or operating-system substitution.
