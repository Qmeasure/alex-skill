# Structure Map JSON Schema

Use this schema as the handoff between document analysis and visual rendering. Keep the JSON valid and complete before rendering.

## Minimal Shape

```json
{
  "title": "文档核心主题",
  "subtitle": "一句话说明这张图回答什么问题",
  "meta": {
    "source": "文件名或来源",
    "date": "YYYY-MM-DD",
    "analyst": "可选"
  },
  "style": {
    "preset": "reference",
    "show_title": false
  },
  "sections": [
    {
      "title": "一级主题",
      "tag": "左侧彩色章节标签，通常直接使用一级主题",
      "heading": "",
      "tone": "blue",
      "cards": [
        {
          "label": "核心结论",
          "text": "一句话结论，包含关键证据或约束。"
        }
      ],
      "blocks": []
    }
  ]
}
```

`style.preset` 固定使用 `reference` 或省略；该 skill 专注于文档插入/打印版。需要生成手机转发长图时，使用 `$long-image`。

Allowed `tone` values: `blue`, `amber`, `green`, `pink`, `cyan`, `purple`, `orange`, `gray`. If omitted, the renderer cycles colors.

For the reference screenshot style:

- Set `style.preset` to `reference` or omit it; the renderer defaults to the reference style.
- Keep `style.show_title` false unless the user asks for a visible document title.
- Put the full visible section heading in `tag`. The renderer places `tag` directly over the timeline rail.
- Use `heading` only for a right-column subheading. Most reference-style outputs should leave it empty.
- Prefer tone order: `blue` -> `amber` -> `green` -> `pink` -> `cyan` -> `purple` -> `orange`.

## Card

Use cards for sequential claims.

```json
{
  "label": "技术判断",
  "text": "CPO 把光电转换进一步靠近计算芯片，降低链路损耗，但提高封装与散热复杂度。"
}
```

## Table Block

Use when comparing dimensions across entities.

```json
{
  "type": "table",
  "title": "技术路径对比",
  "headers": ["路径", "封装位置", "集成度", "主要约束"],
  "rows": [
    ["传统光模块", "设备外部", "低", "功耗和信号损耗较高"],
    ["NPO", "PCB 板附近", "中", "布线和热管理"],
    ["CPO", "芯片/封装附近", "高", "制造、良率、散热"]
  ]
}
```

## Matrix Block

Use when the document implies a two-axis position map.

```json
{
  "type": "matrix",
  "title": "路径成熟度与损耗不确定性",
  "x_axis": "损耗/集成不确定性",
  "y_axis": "当前技术市场渗透率",
  "points": [
    {"label": "传统光模块", "x": 25, "y": 78, "tone": "gray"},
    {"label": "NPO", "x": 58, "y": 44, "tone": "green"},
    {"label": "CPO", "x": 76, "y": 22, "tone": "amber"}
  ]
}
```

`x` and `y` are 0-100 positions. Higher `x` moves right; higher `y` moves up.

## Ecosystem Block

Use for supply chains, product stacks, system modules, or stakeholder maps.

```json
{
  "type": "ecosystem",
  "title": "产业链核心硬件体系",
  "items": [
    {"title": "光发送单元", "details": ["激光芯片", "调制器"]},
    {"title": "光接收单元", "details": ["探测器", "TIA"]},
    {"title": "光处理单元", "details": ["DSP", "驱动芯片"]},
    {"title": "外部配套部件", "details": ["光纤连接器", "散热/电源管理"]}
  ]
}
```

## Source Notes

If the output needs explicit traceability, add source notes at section or card level:

```json
{
  "label": "证据",
  "text": "2026Q1 收入同比增长 18%，主要由企业客户扩张驱动。",
  "source": "10-Q, 2026-05-03"
}
```

Keep source notes short. Do not paste long quotes into the map.

## Extraction Heuristics

- A good section title names the logic, not the document heading verbatim.
- A good card compresses one claim plus its support; it is not a paragraph.
- If a table has more than 6 columns, split it or convert it into cards.
- If a section has more than 5 cards, merge weaker cards or create a table/ecosystem block.
- If a point is interesting but not central to the thesis, omit it or put it in a final `待验证` section.
- Preserve uncertainty: use `待验证`, `分歧`, `风险`, or `反例` where the document is not conclusive.
