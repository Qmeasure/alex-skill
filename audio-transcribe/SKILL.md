---
name: audio-transcribe
description: 音频/视频转文字、逐字稿、说话人分离、时间戳。走火山引擎豆包录音文件识别模型 2.0（标准版），句级时间戳加说话人分离。只要用户提到转写、转文字、听写、字幕原文、逐字稿、会议录音、播客、语音备忘录，或提供音视频文件要求提取文字时使用。
---

# Audio Transcribe

把任意音频(或视频)文件转成文字。一个自包含脚本,直接运行:

```bash
python3 <skill-dir>/scripts/transcribe.py <音频文件> [输出.txt] [--plain]
```

不带输出路径时打到 stdout;带则写入文件。

## 引擎

火山引擎豆包录音文件识别模型 2.0 `bigmodel`(资源 ID `volc.seedasr.auc`,异步提交/查询),句级时间戳 + 说话人分离。中文识别准确度、标点、数字规整(ITN)都好。

走的是**标准版 2.0**(不是极速版 `auc_turbo`):该接口 `audio` 字段只接受公网 `url`,不支持 base64 直传本地文件,所以脚本会先把归一化后的音频上传到阿里云 OSS 中转桶(`audio-transcipt` / `oss-cn-shenzhen.aliyuncs.com`)拿到签名 URL,再提交任务、轮询查询接口,拿到结果后主动删除该 OSS 临时对象。整个上传/提交/轮询/清理都在 `volcengine_transcribe()` 里,无需额外操作。

## 凭证

按 `环境变量 → skill 目录下的 .env` 顺序解析,不依赖任何外部密钥管理服务:

- 豆包(标准版 2.0):`VOLCENGINE_ASR_APP_KEY`
- OSS 中转上传(必需):`ALIBABA_CLOUD_ACCESS_KEY_ID`、`ALIBABA_CLOUD_ACCESS_KEY_SECRET`,可选 `AUDIO_TRANSCRIBE_OSS_ENDPOINT`(默认 `oss-cn-shenzhen.aliyuncs.com`)、`AUDIO_TRANSCRIBE_OSS_BUCKET`(默认 `audio-transcipt`)

以上 key 已经写在 skill 根目录的 `.env` 里(权限 600),脚本启动时自动加载,不需要手动 export。要换 key 直接编辑该文件即可;`.env` 从不进版本控制、不回显到日志或对话。任何验证都只报告字段是否存在和 API 状态,不输出 AK/SK、签名 URL 或原始请求。

## 使用

```bash
# 带时间戳打印
python3 scripts/transcribe.py ~/Downloads/meeting.m4a

# 存文件
python3 scripts/transcribe.py 录音.mp3 转写结果.txt

# 只要纯文本(去掉时间戳和说话人)
python3 scripts/transcribe.py podcast.mp3 --plain
```

输出形态(多说话人时自动带 `S0`/`S1`):

```
[00:00:00] S0  这是一段测试音频。
[00:00:02] S1  今天我们聊一聊人工智能的三个趋势。
```

单说话人时省略 `S` 前缀;`--plain` 则是纯文本。

## 机制

- **格式**:一律先用 ffmpeg 转 16k 单声道 mp3,所以 m4a/flac/ogg/mp4/mkv 等都能直接喂,视频会自动抽音轨
- **OSS 中转**:归一化后的音频先传到中转桶拿签名 URL(有效期 4 小时),再提交任务、轮询查询接口,结果到手后立刻删除该 OSS 临时对象
- **时长上限**:标准版单文件最长 5 小时、512MB,不再需要为绕过体积限制而切块
- **轮询**:提交后每 `VOLC_POLL_INTERVAL`(默认 3s)查询一次,状态码 `20000001`/`20000002` 表示处理中/排队中继续等,超过 `VOLC_POLL_TIMEOUT`(默认 1800s)报超时
- **依赖**:`python3`(仅标准库)、`ffmpeg`/`ffprobe`、`oss2`(OSS 上传中转用)

## 转写之后

用户通常不只要原始文本。转写完主动看一眼结果:

- 转录稿本身不好读(没结构、说话人是 `S0`/`S1`、一个人的话被切成碎片)→ 用 `transcript-md` 整理成带章节和说话人标注的可读 Markdown
- 会议录音 → 可以顺手提出整理成纪要/要点
- 播客/访谈 → 有说话人标注时,可以按角色梳理观点
- 语音备忘录 → 可以整理成清晰的笔记
- 结果里的口语赘词、重复,如果用户要"整理好的文字",帮忙清理

但如果用户只说"转文字",给纯转写结果即可,不要过度加工。

## 故障排查

- `缺少 VOLCENGINE_ASR_APP_KEY`:见上面「凭证」,export 或写进 skill 目录下的 `.env`
- OSS 上传 `AccessDenied ... bucket acl`:AK/SK 本身有效,但没有该 bucket 的读写权限,或 bucket ACL 拒绝了这个账号 —— 需要去阿里云控制台检查这个 bucket 的授权策略/ACL,不是脚本能自己绕过的
- 火山引擎提交/查询返回 `45000131`:超过半小时提交音频总长上限(默认 500 小时),降低提交频率
- 火山引擎提交/查询返回 `45000132`:单个音频超过 512M
- 火山引擎提交/查询返回 `45000151`:音频格式不对,检查 ffmpeg 是否正常转出 mp3
- 结果为空:检查音频是否有人声(`ffprobe` 看时长、`ffmpeg -af volumedetect` 看音量)
- 长音频轮询超时:调大 `VOLC_POLL_TIMEOUT`(单位秒),标准版任务最长可能要等 3 小时
