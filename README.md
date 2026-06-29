# astrbot_plugin_modelscope_image

调用 [ModelScope（魔搭）](https://modelscope.cn/) API-Inference 的文生图模型，在 AstrBot 中一键生成图片。

## 功能

- `/生图 <提示词>`：根据提示词生成图片并发送
- `/生图模型`：查看当前生效的 Token 状态、模型与分辨率
- 基于 ModelScope 异步任务接口，自动轮询直到出图或超时
- 全部配置可在 AstrBot WebUI 可视化修改，无需改代码

## 安装

1. 将本插件目录放入 `AstrBot/data/plugins/`。
2. 在 WebUI 插件管理页面找到本插件，确认依赖（`aiohttp`）已安装。
3. 填写配置（见下文），保存后重载插件。

## 配置说明

所有配置项在 WebUI 插件管理页面以可视化表单呈现，对应 `_conf_schema.json`。

| 配置项 | 类型 | 默认值 | 是否必填 | 说明 |
|--------|------|--------|---------|------|
| `modelscope_token` | string | `""` | ✅ 必填 | ModelScope 访问令牌，用于调用 API-Inference |
| `default_model` | string | `Qwen/Qwen-Image` | 否 | 默认使用的文生图模型 ID |
| `default_size` | string | `1024x1024` | 否 | 默认生成分辨率，格式 `宽x高` |
| `poll_interval` | int | `5` | 否 | 轮询任务状态的间隔（秒） |
| `max_attempts` | int | `60` | 否 | 最大轮询次数，超过判定为超时 |
| `request_timeout` | int | `60` | 否 | 单次网络请求的超时时间（秒） |

### 详细说明

**modelscope_token（必填）**

- 唯一必须配置的项，不填则插件无法工作。
- 获取方式：登录魔搭社区，访问 <https://modelscope.cn/my/myaccesstoken> 创建/复制令牌。
- 填好后保存配置并重载插件即可生效。

**default_model**

- 填写 ModelScope 上的模型 ID，例如 `Qwen/Qwen-Image`、`MusePublic/489_ckpt_FLUX_1` 等。
- 需要是支持 API-Inference 文生图（text-to-image）的模型，否则任务会返回失败。

**default_size**

- 格式为 `宽x高`，比如 `1024x1024`、`1280x720`。
- 不同模型支持的范围不同。以 `Qwen/Qwen-Image` 为例，支持区间是 `[64x64, 1664x1664]`，超出范围会报错。

**poll_interval 与 max_attempts（超时控制）**

- ModelScope 文生图是异步任务：先提交拿到 `task_id`，再轮询结果。
- 这两项共同决定最长等待时间：`总等待时间 ≈ poll_interval × max_attempts`。
- 默认 `5 × 60 = 300` 秒（约 5 分钟）。模型较慢或图较大时可适当调大 `max_attempts`。

**request_timeout**

- 单次 HTTP 请求（提交任务、查询状态、下载图片 URL）的超时秒数，与上面的轮询总时长是两个不同维度。
- 网络较差时可调大，避免单次请求过早超时。

### 最小配置示例

实际只需填一个 Token 即可运行，其余保持默认：

```json
{
  "modelscope_token": "ms-xxxxxxxxxxxxxxxxxxxxxxxx"
}
```

## 使用

```
/生图 一只在花园里玩耍的金色猫咪
```

机器人会先回复正在生成的提示，随后发送生成的图片。

查看当前配置：

```
/生图模型
```

## 工作原理

插件遵循 ModelScope API-Inference 的异步文生图流程：

1. 向 `v1/images/generations` 提交请求，携带请求头 `X-ModelScope-Async-Mode: true`，获取 `task_id`。
2. 轮询 `v1/tasks/{task_id}`，携带请求头 `X-ModelScope-Task-Type: image_generation`，直到任务状态为 `SUCCEED` / `FAILED` 或超时。
3. 任务成功后取第一张图片的 URL，通过 `event.image_result(url)` 发送。

## 常见问题

| 现象 | 可能原因 | 处理 |
|------|----------|------|
| 提示「尚未配置 ModelScope Token」 | 未填写 `modelscope_token` | 在配置中填写令牌并重载插件 |
| 「图片生成失败」 | 模型不支持文生图 / 分辨率超范围 / 提示词违规 | 更换模型、调整 `default_size`、修改提示词 |
| 「图片生成超时」 | 模型处理较慢 | 调大 `max_attempts` 或稍后重试 |
| 任务提交失败 (HTTP 401) | Token 无效或过期 | 重新生成令牌 |

## 许可证

MIT
