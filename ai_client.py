import base64
import json
import logging
from dataclasses import dataclass
from typing import List, Optional

import aiohttp

logger = logging.getLogger("VetBot.AI")


@dataclass(frozen=True)
class ModelConfig:
    model: str
    temperature: float = 0.3
    max_tokens: int = 800


class VseGPTClient:
    """
    OpenAI-compatible Chat Completions client for vsegpt.ru.
    """

    def __init__(self, api_key: str, base_url: str = "https://api.vsegpt.ru/v1"):
        self.api_key = (api_key or "").strip()
        self.base_url = (base_url or "").rstrip("/")

    @property
    def enabled(self) -> bool:
        return bool(self.api_key) and "placeholder" not in self.api_key and len(self.api_key) >= 10

    async def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        history: List[dict],
        cfg: ModelConfig,
        image_bytes: Optional[bytes] = None,
    ) -> str:
        if not self.enabled:
            return "❌ VseGPT API key не настроен. Добавьте VSEGPT_API_KEY в .env"

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        messages: List[dict] = [{"role": "system", "content": system_prompt}]
        messages.extend(history or [])

        if image_bytes:
            b64 = base64.b64encode(image_bytes).decode("utf-8")
            # OpenAI multimodal format (most OpenAI-compatible gateways support it)
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    ],
                }
            )
        else:
            messages.append({"role": "user", "content": user_prompt})

        payload = {
            "model": cfg.model,
            "messages": messages,
            "temperature": cfg.temperature,
            "max_tokens": cfg.max_tokens,
            "stream": False,
        }

        timeout = aiohttp.ClientTimeout(total=180)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as sess:
                async with sess.post(url, headers=headers, json=payload) as r:
                    raw = await r.text()
                    if r.status != 200:
                        logger.error("VseGPT error %s: %s", r.status, raw[:2000])
                        return f"❌ Ошибка модели: {r.status}\n{raw[:1500]}"
                    try:
                        data = json.loads(raw)
                    except Exception:
                        return raw
        except Exception as e:
            logger.exception("VseGPT request failed: %s", e)
            return "❌ Ошибка подключения к VseGPT. Проверьте интернет/ключ/доступ."

        try:
            return (data["choices"][0]["message"]["content"] or "").strip()
        except Exception:
            return raw[:2000]


