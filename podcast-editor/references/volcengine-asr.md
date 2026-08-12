# 火山引擎转录约定

使用[火山引擎录音文件识别标准版](https://www.volcengine.com/docs/6561/1354868)。鉴权头为 `X-Api-Key`，资源标识为 `volc.bigasr.auc`。提交和查询地址以火山引擎当前官方文档为准；修改客户端前先核对文档，不试探其他接口路径。

## 固定请求参数

```json
{
  "model_name": "bigmodel",
  "enable_itn": true,
  "enable_punc": true,
  "enable_ddc": false,
  "show_utterances": true,
  "enable_channel_split": false
}
```

- `show_utterances=true`：保留分句和字级时间信息。
- `enable_ddc=false`：不让转录服务先清掉口语词，口误判断留给 Codex 和用户。
- `enable_channel_split=false`：一条文件始终按一条合成音轨处理，不能拆左右声道。
- `enable_itn=true`：保留常用数字和文本规范化。
- `enable_punc=true`：读取 `utterance.text` 中的自动标点，对齐到现有词条的 `punctuationAfter`。标点只显示，不参与剪辑。参数说明见[官方文档](https://www.volcengine.com/docs/6561/1354871?lang=zh)。

标点转录写入项目前，必须去掉新增标点并与原逐字内容逐字比较。字词不一致时停止，不替换原文、时间戳、词条 ID 或说话人。

合成音轨启用说话人识别。服务返回的说话人编号不直接展示；按第一次出现的顺序映射为 `speaker-01`、`speaker-02`、`speaker-03` 等，默认名称依次为“嘉宾一”“嘉宾二”“嘉宾三”等。不预设人数，也不能把额外声纹簇并入前两个。自动识别不是身份认证，短发言、相近音色和连续抢话都可能分错。审核页允许按发言轮次修正，修正保存在 `speakerOverrides`，原始返回和 `project.json` 不改。

多人分轨逐文件提交，每个文件固定映射到一个 `speakerId`。即使转录结果包含其他说话人编号，也不能据此把单个文件继续拆轨。

脚本使用 base64 直传本地音频，单个上传文件上限为 100 MiB。首次建立项目时，超过上限就停止并说明原因。`retranscribe` 会先生成与原文件等时长的 16kHz、64kbps 单声道 MP3，再提交识别；这个文件只用于转录，播放、波形、切点和导出仍读取原音频。

## 密钥与失败处理

先读进程环境变量 `VOLCENGINE_API_KEY`，没有再读 Skill 根目录 `.env`。不读取其他未约定位置。

提交和轮询都要有超时。网络超时和服务端错误只重试有限次数；限流、鉴权和参数错误直接停止并说明原因。日志只保留请求 ID、状态码和可安全展示的错误摘要，不打印鉴权头。
