# 项目与接口约定

本地服务是项目状态、剪辑区间和导出结果的唯一来源。网页只负责收集操作并展示服务端返回的数据。

## 项目数据

`project.json` 至少包含：

```json
{
  "schemaVersion": 1,
  "id": "项目 ID",
  "mode": "mixed",
  "durationMs": 120000,
  "sources": [
    {"id": "source-1", "speakerId": null, "path": "D:\\audio\\mix.mp3", "durationMs": 120000}
  ],
  "speakers": [
    {"id": "speaker-1", "name": "嘉宾一"}
  ],
  "utterances": [
    {
      "id": "utterance-1",
      "speakerId": "speaker-1",
      "startMs": 0,
      "endMs": 860,
      "words": [
        {
          "id": "word-1",
          "text": "大家",
          "startMs": 0,
          "endMs": 420,
          "punctuationAfter": "，"
        }
      ]
    }
  ]
}
```

`mode` 只能是 `mixed` 或 `multitrack`。时间统一使用整数毫秒。`speakerId`、`utterance.id` 和 `word.id` 建立后不得因改名或重新打开页面而变化。

`punctuationAfter` 是可选显示字段，只能保存标点。它不是词条，不可选中，也不改变剪辑边界。

`review-state.json` 保存用户操作：

```json
{
  "revision": 3,
  "selectedWordIds": ["word-8", "word-9"],
  "speakerNames": {"speaker-1": "主持人", "speaker-2": "小李"},
  "speakerOverrides": {"utterance-3": "speaker-2"},
  "cutOverrides": {
    "del-2c87f189d4d29c184a91": {"startMs": 8120, "endMs": 9360}
  }
}
```

`speakerOverrides` 只修正审核显示中的说话人归属，不改写 `project.json` 的原始识别结果。键是稳定的句段 ID，值是已有说话人 ID。

`cutOverrides` 保存用户在波形上调整过的删除边界。键是稳定的删除段 ID，值是实际删除的起止时间。删除段 ID 由项目、删除范围和适用轨道确定；只要首尾词和适用轨道不变，重新打开页面后仍使用同一 ID。取消手动调整时，从 `cutOverrides` 删除该项，后端恢复声学分析得到的边界。

手动边界必须包含原始选词范围，且不能越过相邻未选词的安全边界。有效删除段 ID 对应的边界越界或倒序时返回 `400`，不会悄悄修正用户提交的数值。增删选词造成删除段拆分或合并后，旧 ID 已经无法对应当前删除段；后端自动丢弃这些 `cutOverrides`，并在保存结果中返回清理后的映射。

保存时先写临时文件，再原子替换正式文件。客户端提交旧 `revision` 时返回 `409`，避免后打开的旧页面覆盖新操作。

`cutPlan` 是一次审核状态对应的唯一切割结果：

```json
{
  "revision": 3,
  "planId": "plan-3417a73c04dc8ea76019",
  "deletions": [
    {
      "id": "del-2c87f189d4d29c184a91",
      "firstWordId": "word-8",
      "lastWordId": "word-9",
      "rawStartMs": 8200,
      "rawEndMs": 9280,
      "startMs": 8120,
      "endMs": 9360,
      "minStartMs": 7800,
      "maxEndMs": 9600,
      "boundaryMode": "manual",
      "scope": "global",
      "speakerId": null,
      "canCut": true,
      "needsReview": false,
      "boundaryWarning": null
    }
  ],
  "timeline": {
    "revision": 3,
    "durationMs": 118760,
    "segments": [
      {
        "sourceStartMs": 0,
        "sourceEndMs": 8120,
        "targetStartMs": 0,
        "targetEndMs": 8120
      }
    ]
  },
  "globalDeletions": [{"startMs": 8120, "endMs": 9360}],
  "speakerDeletions": {},
  "tracks": [
    {
      "sourceId": "source-1",
      "speakerId": null,
      "name": "主持人、小李",
      "segments": [
        {
          "sourceStartMs": 0,
          "sourceEndMs": 8120,
          "targetStartMs": 0,
          "targetEndMs": 8120
        }
      ]
    }
  ]
}
```

`rawStartMs` 和 `rawEndMs` 是首尾选中字的原始范围；`startMs` 和 `endMs` 是实际切割边界。`boundaryMode` 为 `raw`、`acoustic`、`acoustic-review` 或 `manual`。`minStartMs` 和 `maxEndMs` 是页面允许手动调整的范围。`scope` 为 `global` 时整条时间线删除，为 `speaker` 时只处理 `speakerId` 对应的轨道。

`canCut` 表示安全范围能否完整覆盖 `rawStartMs` 至 `rawEndMs`。只有 `canCut: true` 的删除段才进入 `globalDeletions`、`speakerDeletions` 和 `tracks` 的实际切割结果，其 `startMs` 至 `endMs` 必须完整覆盖原始选词范围。

`canCut: false` 表示相邻保留词的发声范围重叠，无法安全切掉全部选中文字。这时实际时间轴保持原声，上方字幕也保留这些词，页面禁用切点手柄。`needsReview` 表示自动分析无法确认安全切点，`boundaryWarning` 说明具体原因，例如“右侧没有可靠的低能量间隔”或“所选内容与后一个保留词连读”。页面必须提示人工查看波形，后端仍保护相邻未选词。

`globalDeletions` 是所有轨道一起删除的区间，`speakerDeletions` 按说话人 ID 列出只在单轨静音的区间。`tracks` 是各来源音频的最终片段；每项包含稳定的 `sourceId`、对应 `speakerId`、轨道名和连续保留片段。合成音轨只有一项，且 `speakerId` 为 `null`。

`planId` 由项目内容、审核版本、选词、说话人修正、手动切点、音频文件指纹和声学分析版本共同确定。任何一项变化都会生成新的 `planId`。即时播放、精确试听和导出必须使用同一个 `planId`。

`Timeline` 位于 `cutPlan.timeline`，由后端生成：

```json
{
  "revision": 3,
  "durationMs": 115300,
  "segments": [
    {
      "sourceStartMs": 0,
      "sourceEndMs": 8200,
      "targetStartMs": 0,
      "targetEndMs": 8200
    }
  ]
}
```

每个片段表示一段连续保留的声音。页面用它在原音频时间和剪后时间之间转换，不自行推导删除区间。

## HTTP 接口

### `GET /api/project`

返回 `project`、`state`、`reviewTurns` 和 `playback`。`playback.strategy` 固定为 `dual-audio-preload-v1`，`revision`、`planId`、`timeline` 和 `cutPlan` 必须属于同一版本。为兼容现有页面，`playback.timeline` 与 `playback.cutPlan.timeline` 内容相同。返回的 `project` 已应用 `speakerOverrides`，磁盘上的原始项目不变。`reviewTurns` 只在说话人变化时新建一轮，通过 `utteranceIds` 引用原始转录句段。

`playback.sources` 为每个输入文件提供独立地址：

```json
[
  {"sourceId": "source-1", "speakerId": "speaker-1", "url": "/api/audio/source?sourceId=source-1"},
  {"sourceId": "source-2", "speakerId": "speaker-2", "url": "/api/audio/source?sourceId=source-2"}
]
```

合成音轨只有一个来源。多人分轨页面逐项加载 `playback.sources`，再按 `cutPlan.tracks` 同步播放；临时混音只用于兼容旧的单播放器入口，不是逐轨切割结果。

`playback.runs` 由 `cutPlan.timeline` 的保留片段生成。每个 run 是一次全局 Deck 切换，ID 同时绑定 `planId` 和该段时间范围：

```json
{
  "id": "run-9e9fd84e7b9c8dd04db1",
  "sourceStartMs": 0,
  "sourceEndMs": 8120,
  "targetStartMs": 0,
  "targetEndMs": 8120,
  "sources": [
    {
      "sourceId": "source-1",
      "streamUrl": "/api/audio/source?sourceId=source-1",
      "sourceStartMs": 0,
      "sourceEndMs": 8120
    }
  ]
}
```

多人分轨的每个 run 含全部等长来源，来源区间与全局区间一致。`speakerDeletions` 只通过 `playback.tracks` 的片段空档做单轨静音，不新增全局 run，也不压缩全局时间。相邻保留段只有在来源和目标时间都连续、间隔不超过 2ms，且中间没有全局删除区间时才可合并；不得跨越删除内容。

`/api/audio/source` 返回 `ETag` 和 `Cache-Control`。不带 Range 的请求命中 `If-None-Match` 时返回 `304`；带 Range 的请求仍返回 `206` 和相同 `ETag`。

### `PUT /api/state`

请求体：

```json
{"revision": 3, "selectedWordIds": ["word-8"], "speakerNames": {"speaker-1": "主持人"}, "speakerOverrides": {"utterance-3": "speaker-2"}, "cutOverrides": {}}
```

成功返回新的 `state`、应用修正后的 `project`、`reviewTurns`、`revision`、`savedAt`、`cutOverrides`、`cutPlan`、同版本 `timeline` 和完整 `playback`。`playback` 的字段和生成规则与 `GET /api/project` 相同。字段类型或手动切点错误返回 `400`，版本冲突返回 `409`。

### `GET /api/waveform`

查询参数为 `startMs`、`endMs` 和 `points`。多人分轨再传 `sourceId`，指定要查看的来源文件；合成音轨可以省略 `sourceId`，固定使用唯一来源。返回指定范围内的真实波形峰值，不返回整条 PCM：

```json
{
  "sourceId": "source-1",
  "startMs": 7800,
  "endMs": 9600,
  "points": [
    {"startMs": 7800, "endMs": 7810, "peak": 0.1823}
  ]
}
```

时间范围无效、点数超限或 `sourceId` 不存在时返回 `400`。接口只读取声学分析缓存，不修改审核状态。

### `POST /api/preview`

请求体必须包含当前 `revision` 和 `planId`。服务端只使用对应 `cutPlan` 生成审核音频，返回 `url`、`revision`、`planId`、同一份 `timeline` 和按剪后时间重排的 `utterances`。相同 `planId` 可直接返回缓存；修改选择不会自动调用本接口。缺少或格式错误的 `revision`、`planId` 返回 `400`；版本过期、切割结果不一致或存在 `canCut: false` 的删除段时返回 `409`。服务端不得用最新状态替换旧请求后继续生成。

### `POST /api/export`

请求体必须包含当前 `revision` 和 `planId`，可选 `draftName`。服务端使用对应 `cutPlan` 生成剪映草稿，返回 `draftName`、`draftPath`、`revision` 和 `planId`。缺少或格式错误的 `revision`、`planId` 返回 `400`；版本过期、切割结果不一致或存在 `canCut: false` 的删除段时返回 `409`。

### `POST /api/cancel`

取消正在生成的试听或草稿。请求体是空 JSON 对象，返回值如下：

```json
{
  "cancellationRequested": true,
  "status": {"phase": "cancelling", "message": "正在取消操作。"}
}
```

没有正在执行的任务时，`cancellationRequested` 为 `false`。取消同时作用于当前任务和当时已经排队的任务；取消后新发起的请求可以正常执行。被取消的试听或导出请求返回 `409`，错误码为 `operation_cancelled`。取消、超时或页面关闭后，前端必须结束等待状态；后端负责终止仍在运行的音频处理进程并清理临时文件。

## 错误格式

所有接口使用同一格式：

```json
{
  "error": {
    "code": "revision_conflict",
    "message": "审核内容已在另一个页面更新，请刷新后再试。",
    "details": {}
  }
}
```

不得把 API 密钥、完整外部响应或本机隐私路径写进面向浏览器的错误信息。

声学分析无法执行时使用 `audio_analysis_failed`，HTTP 状态为 `500`；不能降级为“精确切点”继续返回。有效删除段的手动切点无效时使用 `invalid_cut_override`，`planId` 缺失或格式错误时使用 `invalid_plan_id`，`revision` 缺失或格式错误时使用 `invalid_revision`，这些请求错误返回 `400`。试听或导出的 `revision` 过期时使用 `revision_conflict`，`planId` 与当前结果不一致时使用 `plan_conflict`，存在无法安全切除的选词时使用 `uncuttable_selection`，这三类冲突返回 `409`。页面只展示后端说明并重新获取项目状态。
