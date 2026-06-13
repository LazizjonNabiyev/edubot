"""
Multi-AI Generator — Gemini Flash → Pro → fallback
Tiqilmaslik uchun bir nechta AI modeldan foydalanadi
"""

import os
import asyncio
import logging
import json
import aiohttp
from typing import Optional

logger = logging.getLogger(__name__)

GEMINI_KEYS = [
    os.getenv("GEMINI_API_KEY_1", ""),
    os.getenv("GEMINI_API_KEY_2", ""),
    os.getenv("GEMINI_API_KEY_3", ""),
]
GEMINI_KEYS = [k for k in GEMINI_KEYS if k]  # Bo'sh kalitlarni olib tashlash

OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")

GEMINI_MODELS = [
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
]


class AIGenerator:
    def __init__(self):
        self._key_index = 0
        self._model_index = 0

    def _next_key(self):
        """Navbatdagi API kalitni olish (round-robin)"""
        if not GEMINI_KEYS:
            return None
        key = GEMINI_KEYS[self._key_index % len(GEMINI_KEYS)]
        self._key_index += 1
        return key

    def _next_model(self):
        """Navbatdagi modelni olish"""
        model = GEMINI_MODELS[self._model_index % len(GEMINI_MODELS)]
        self._model_index += 1
        return model

    async def generate_content(self, topic: str, doc_type: str) -> dict:
        """
        Kontent generatsiya qilish.
        Qaytaradi: {
            "title": str,
            "sections": [{"heading": str, "content": str}, ...],
            "doc_type": str
        }
        """
        prompt = self._build_prompt(topic, doc_type)

        # Gemini bilan urinish
        if GEMINI_KEYS:
            for attempt in range(len(GEMINI_KEYS) * len(GEMINI_MODELS)):
                key = self._next_key()
                model = self._next_model()
                try:
                    result = await self._gemini_request(key, model, prompt)
                    if result:
                        logger.info(f"✅ Gemini {model} ishladi")
                        return result
                except Exception as e:
                    logger.warning(f"⚠️ Gemini {model} xato: {e}")
                    await asyncio.sleep(1)

        # OpenAI fallback
        if OPENAI_KEY:
            try:
                result = await self._openai_request(prompt)
                if result:
                    logger.info("✅ OpenAI ishladi")
                    return result
            except Exception as e:
                logger.error(f"❌ OpenAI xato: {e}")

        # Agar hamma AI ishlmasa — standart kontent
        logger.warning("⚠️ Hamma AI ishlmadi, standart kontent qaytarilmoqda")
        return self._fallback_content(topic, doc_type)

    def _build_prompt(self, topic: str, doc_type: str) -> str:
        type_instructions = {
            "pptx": f"""Mavzu bo'yicha prezentatsiya uchun kontent tayyorla.
FAQAT JSON format, boshqa hech narsa yozma.
{{
  "title": "Sarlavha",
  "sections": [
    {{"heading": "Kirish", "content": "2-3 ta asosiy fikr, har biridan keyin || belgisi. Masalan: Fikr 1 || Fikr 2 || Fikr 3"}},
    {{"heading": "Asosiy qism 1", "content": "..."}},
    {{"heading": "Asosiy qism 2", "content": "..."}},
    {{"heading": "Asosiy qism 3", "content": "..."}},
    {{"heading": "Xulosa", "content": "..."}}
  ]
}}
Har bir bo'lim 3-5 ta qisqa fikrdan iborat bo'lsin. || bilan ajrat.""",

            "mustaqil": f"""Mustaqil ish uchun kontent tayyorla.
FAQAT JSON format:
{{
  "title": "Sarlavha",
  "sections": [
    {{"heading": "Kirish", "content": "To'liq paragraf matn..."}},
    {{"heading": "Asosiy qism", "content": "..."}},
    {{"heading": "Tahlil va muhokama", "content": "..."}},
    {{"heading": "Xulosa", "content": "..."}},
    {{"heading": "Foydalanilgan adabiyotlar", "content": "1. ...\n2. ...\n3. ..."}}
  ]
}}
Har bo'lim 200-300 so'zdan iborat bo'lsin. O'zbek tilida.""",

            "amaliy": f"""Amaliy ish uchun kontent tayyorla.
FAQAT JSON format:
{{
  "title": "Sarlavha",
  "sections": [
    {{"heading": "Kirish va maqsad", "content": "..."}},
    {{"heading": "Nazariy asos", "content": "..."}},
    {{"heading": "Amaliy qism", "content": "..."}},
    {{"heading": "Natijalar va tahlil", "content": "..."}},
    {{"heading": "Xulosa", "content": "..."}}
  ]
}}""",

            "referat": f"""Referat uchun kontent tayyorla.
FAQAT JSON format:
{{
  "title": "Sarlavha",
  "sections": [
    {{"heading": "Kirish", "content": "..."}},
    {{"heading": "Mavzuning tarixiy taraqqiyoti", "content": "..."}},
    {{"heading": "Asosiy qism: {topic[:50]}", "content": "..."}},
    {{"heading": "Zamonaviy holat va tendentsiyalar", "content": "..."}},
    {{"heading": "Xulosa", "content": "..."}},
    {{"heading": "Adabiyotlar ro'yxati", "content": "1. ...\n2. ...\n3. ..."}}
  ]
}}"""
        }

        return f"""Siz O'zbekiston universiteti uchun akademik hujjat yozuvchi mutaxassissiz.

Mavzu: "{topic}"
Hujjat turi: {doc_type}

{type_instructions.get(doc_type, type_instructions['referat'])}

Matn o'zbek tilida, professional akademik uslubda bo'lsin."""

    async def _gemini_request(self, api_key: str, model: str, prompt: str) -> Optional[dict]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        headers = {"Content-Type": "application/json"}
        params = {"key": api_key}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 4096,
            }
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, headers=headers, params=params,
                json=payload, timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                if resp.status == 429:
                    raise Exception("Rate limit")
                if resp.status != 200:
                    raise Exception(f"HTTP {resp.status}")

                data = await resp.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                return self._parse_json_response(text)

    async def _openai_request(self, prompt: str) -> Optional[dict]:
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {OPENAI_KEY}"
        }
        payload = {
            "model": "gpt-3.5-turbo",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 4096,
            "temperature": 0.7
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, headers=headers,
                json=payload, timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                data = await resp.json()
                text = data["choices"][0]["message"]["content"]
                return self._parse_json_response(text)

    def _parse_json_response(self, text: str) -> Optional[dict]:
        """JSON javobni parse qilish"""
        # Markdown code block olib tashlash
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        try:
            data = json.loads(text)
            if "title" in data and "sections" in data:
                return data
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse xato: {e}")
            # Qisman parse
            try:
                start = text.find("{")
                end = text.rfind("}") + 1
                if start >= 0 and end > start:
                    data = json.loads(text[start:end])
                    if "title" in data and "sections" in data:
                        return data
            except:
                pass
        return None

    def _fallback_content(self, topic: str, doc_type: str) -> dict:
        """AI ishlmasa standart kontent"""
        return {
            "title": topic,
            "sections": [
                {"heading": "Kirish", "content": f"{topic} mavzusi hozirgi kunda dolzarb ahamiyatga ega. Ushbu ish mavzuning asosiy jihatlarini yoritishga qaratilgan."},
                {"heading": "Asosiy qism", "content": f"{topic} bo'yicha zamonaviy tadqiqotlar ko'p jihatlarni ochib beradi. Bu sohada muhim o'zgarishlar kuzatilmoqda."},
                {"heading": "Tahlil", "content": f"Mavzu tahlili shuni ko'rsatadiki, {topic} sohasida keng qamrovli yondashuv zarur. Turli metodlar va usullar qo'llaniladi."},
                {"heading": "Xulosa", "content": f"Xulosa qilib aytganda, {topic} mavzusi ko'p qirrali va amaliy ahamiyatga ega bo'lib, keyingi tadqiqotlar uchun asos bo'la oladi."},
            ]
        }
