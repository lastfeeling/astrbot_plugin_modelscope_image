import asyncio
import json

import aiohttp

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

# ModelScope API-Inference 默认基础地址（国际版）。可在配置中切换为国内版 .cn。
DEFAULT_API_BASE = "https://api-inference.modelscope.ai/"


@register(
    "astrbot_plugin_modelscope_image",
    "lastfeeling",
    "调用 ModelScope（魔搭）的文生图模型生成图片。",
    "v1.0.0",
    "https://github.com/lastfeeling/astrbot_plugin_modelscope_image",
)
class ModelScopeImagePlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config

    def _get_token(self) -> str:
        """读取并校验 ModelScope Token。"""
        token = (self.config.get("modelscope_token") or "").strip()
        return token

    def _get_api_base(self) -> str:
        """读取 API-Inference 基础地址，确保以 / 结尾。"""
        base = (self.config.get("api_base") or DEFAULT_API_BASE).strip()
        if not base.endswith("/"):
            base += "/"
        return base

    async def _generate_image(self, prompt: str, model: str, size: str) -> str:
        """
        调用 ModelScope 异步文生图接口，返回生成图片的 URL。

        流程：
        1. 以异步模式提交生成任务，拿到 task_id。
        2. 轮询任务状态直到 SUCCEED / FAILED 或超时。
        3. 返回第一张图片的 URL。

        失败时抛出带有可读信息的 RuntimeError。
        """
        token = self._get_token()
        if not token:
            raise RuntimeError(
                "未配置 ModelScope Token，请在插件配置中填写 modelscope_token。"
            )

        timeout_seconds = int(self.config.get("request_timeout", 60))
        poll_interval = int(self.config.get("poll_interval", 5))
        max_attempts = int(self.config.get("max_attempts", 60))
        api_base = self._get_api_base()

        common_headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        timeout = aiohttp.ClientTimeout(total=timeout_seconds)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            # 1. 提交异步任务
            submit_headers = {**common_headers, "X-ModelScope-Async-Mode": "true"}
            payload = {"model": model, "prompt": prompt, "size": size}
            logger.info(f"[ModelScope生图] 提交任务 model={model} size={size} prompt={prompt}")

            async with session.post(
                f"{api_base}v1/images/generations",
                headers=submit_headers,
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            ) as resp:
                body = await resp.text()
                if resp.status != 200:
                    raise RuntimeError(
                        f"任务提交失败 (HTTP {resp.status}): {body}"
                    )
                task_result = json.loads(body)

            task_id = task_result.get("task_id")
            if not task_id:
                raise RuntimeError(f"任务提交未返回 task_id: {task_result}")
            logger.info(f"[ModelScope生图] 任务已提交，task_id={task_id}")

            # 2. 轮询任务状态
            poll_headers = {
                **common_headers,
                "X-ModelScope-Task-Type": "image_generation",
            }
            for attempt in range(1, max_attempts + 1):
                await asyncio.sleep(poll_interval)
                async with session.get(
                    f"{api_base}v1/tasks/{task_id}",
                    headers=poll_headers,
                ) as resp:
                    body = await resp.text()
                    if resp.status != 200:
                        raise RuntimeError(
                            f"查询任务状态失败 (HTTP {resp.status}): {body}"
                        )
                    result_data = json.loads(body)

                status = result_data.get("task_status")
                logger.info(
                    f"[ModelScope生图] 任务状态 {status} ({attempt}/{max_attempts})"
                )

                if status == "SUCCEED":
                    images = result_data.get("output_images") or []
                    if not images:
                        raise RuntimeError("任务成功但未返回图片。")
                    return images[0]

                if status == "FAILED":
                    msg = result_data.get("message", "未知错误")
                    raise RuntimeError(f"图片生成失败：{msg}")

                # PENDING / RUNNING 继续等待

            raise RuntimeError(
                f"图片生成超时（约 {poll_interval * max_attempts} 秒），任务可能仍在处理。"
            )

    @filter.command("生图")
    async def draw(self, event: AstrMessageEvent):
        """调用 ModelScope 生成图片。用法：/生图 <描述提示词>"""
        # 提取提示词：去掉指令本身，保留其余文本
        prompt = event.message_str.strip()
        for prefix in ("生图", "draw"):
            if prompt.startswith(prefix):
                prompt = prompt[len(prefix):].strip()
                break

        if not prompt:
            yield event.plain_result("请提供描述提示词，例如：/生图 一只在花园里玩耍的金色猫咪")
            return

        if not self._get_token():
            yield event.plain_result(
                "尚未配置 ModelScope Token，请在 WebUI 插件配置中填写 modelscope_token。"
            )
            return

        model = self.config.get("default_model", "Qwen/Qwen-Image")
        size = self.config.get("default_size", "1024x1024")

        yield event.plain_result("正在生成图片，请稍候…")

        try:
            image_url = await self._generate_image(prompt, model, size)
        except Exception as e:  # noqa: BLE001 - 统一兜底，避免插件崩溃
            logger.error(f"[ModelScope生图] 生成失败: {e}")
            yield event.plain_result(f"生成失败：{e}")
            return

        yield event.image_result(image_url)

    @filter.command("生图模型")
    async def show_model(self, event: AstrMessageEvent):
        """查看当前 ModelScope 生图配置。"""
        model = self.config.get("default_model", "Qwen/Qwen-Image")
        size = self.config.get("default_size", "1024x1024")
        configured = "已配置" if self._get_token() else "未配置"
        yield event.plain_result(
            f"当前生图配置：\n接口地址：{self._get_api_base()}\n"
            f"Token：{configured}\n模型：{model}\n分辨率：{size}"
        )

    async def terminate(self):
        """插件被卸载/停用时调用。"""
        logger.info("[ModelScope生图] 插件已卸载。")
