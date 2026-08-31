# Mobile Share Map 品牌配置

所有手机长图共用此目录的品牌文件；修改后重新运行渲染脚本即可同时更新 Internal 与 External。

## 最常用的两处修改

1. 替换二维码：直接覆盖 [assets/zhifujie-qr.png](assets/zhifujie-qr.png)。顶部右侧的交流群入口和底部右侧会自动使用同一张图，无需修改任何 JSON。
2. 修改文字：编辑 [assets/brand.json](assets/brand.json)。`masthead_text` 控制左上角；`footer_title` 与 `footer_intro` 控制底部介绍区；`footer_intro` 中的 `\n` 会按真实换行渲染；`qr_label` 同时控制顶部与底部的“扫码获取完整研报”说明。

## 品牌配置字段

| 字段 | 位置 | 用途 |
|---|---|---|
| `masthead_text` | 左上角 | 品牌短句 |
| `footer_title` | 底部左侧第一行 | 交流群引导标题 |
| `footer_intro` | 底部左侧 | 机构介绍 |
| `footer_points` | 底部左侧 | 可选的旧版分点文案；默认留空 |
| `footer_background` | 400px 高底栏 | 科技蓝背景图片路径，不包含文字和二维码 |
| `qr_image` | 顶部右侧交流群入口、底部右侧 | 同一张二维码资产路径 |
| `qr_label` | 两处二维码下方 | 扫码获取完整研报说明 |

`qr_image` 可以指向 skill 内相对路径，或改为绝对路径、`https://` URL、`data:` URL。若改为 PNG/JPG 文件，只需同步修改该字段；默认二维码文件名保持不变时，直接覆盖图片即可。

## 单张图临时覆盖

默认情况下渲染器优先读取 `assets/brand.json`，保证所有图片品牌一致。仅在某张图确需特殊文案时，在输入 JSON 的 `share` 中写入：

```json
{
  "override_brand": true,
  "masthead_text": "临时品牌短句",
  "footer_title": "临时关注标题",
  "footer_background": "C:/path/to/temporary-footer.png",
  "qr_image": "C:/path/to/temporary-qr.png"
}
```

## 验收

渲染后确认：顶部和底部二维码图案相同、两处均显示“扫码获取完整研报”、左上角品牌短句正确；正文与底栏之间保留 70px 白色间隔，底栏固定为 1080×400px，总占用 470px，科技蓝背景、标题、介绍、二维码均完整可见。真实二维码还应实测扫码。
