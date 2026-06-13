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
    "gemini-2.5-flash",
    "gemini-2.5-pro",
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

MUHIM QOIDALAR:
- Har bir "content" da kamida 5-7 ta fikr bo'lsin
- Har bir fikr 1-2 jumladan iborat bo'lsin (qisqa emas, ma'lumotli)
- Fikrlar orasida || belgisi bo'lsin
- Raqam, statistika, misol keltir
- O'zbek tilida yoz

{{
  "title": "{topic}",
  "sections": [
    {{
      "heading": "Kirish: Mavzuga umumiy nazar",
      "content": "Bu mavzu haqida 1-2 jumlali fikr || Tarixiy kelib chiqishi || Nima uchun dolzarb || Qanday sohalarda qo'llaniladi || Asosiy muammo va yechimlar || Dunyo miqyosidagi ahamiyati"
    }},
    {{
      "heading": "Asosiy tushunchalar va ta'riflar",
      "content": "Birinchi asosiy tushuncha va uning izohi || Ikkinchi muhim atama || Uchinchi tushuncha batafsil || To'rtinchi element || Beshinchi jihat || Oltinchi xususiyat"
    }},
    {{
      "heading": "Qo'llanish sohalari va misollari",
      "content": "Birinchi soha: batafsil misol || Ikkinchi soha: amaliy tatbiq || Uchinchi soha: real hayot misoli || To'rtinchi soha || Beshinchi qo'llanish || Jahon tajribasi"
    }},
    {{
      "heading": "Afzalliklari va kamchiliklari",
      "content": "Birinchi afzallik: batafsil || Ikkinchi ijobiy tomoni || Uchinchi yaxshi jihati || Birinchi kamchilik || Ikkinchi muammo || Yechim yo'llari"
    }},
    {{
      "heading": "Zamonaviy tendentsiyalar",
      "content": "Hozirgi holat || Rivojlanish tendentsiyasi || Yangi kashfiyotlar || Kelajak istiqboli || Texnologik o'zgarishlar || 2030-2050 yillar prognozi"
    }},
    {{
      "heading": "Xulosa va tavsiyalar",
      "content": "Asosiy xulosalar || Amaliy tavsiyalar || O'zbek uchun ahamiyati || Keyingi qadamlar || Umumiy baholash || So'nggi fikr"
    }}
  ]
}}""",

            "mustaqil": f"""Mustaqil ish uchun professional akademik kontent tayyorla.
FAQAT JSON format, boshqa hech narsa yozma.

MUHIM: Har bir bo'lim kamida 250-350 so'zdan iborat bo'lsin. To'liq jumlalar bilan yoz.

{{
  "title": "{topic}",
  "sections": [
    {{"heading": "Kirish", "content": "Mavzuning dolzarbligi va ahamiyati haqida 3-4 ta to'liq jumla. Muammo bayoni. Ishning maqsad va vazifalari. Tadqiqot metodlari. Ishning tuzilishi haqida qisqacha ma'lumot. Mavzuning O'zbekiston uchun ahamiyati."}},
    {{"heading": "Mavzuning nazariy asoslari", "content": "Asosiy tushunchalar va ilmiy ta'riflar batafsil keltiriladi. Turli olimlar va mutaxassislarning qarashlari. Mavzuning tarixiy rivojlanishi. Nazariy asoslar va metodologiya. Xorijiy va mahalliy tadqiqotchilar ishlari."}},
    {{"heading": "Asosiy tahlil va muhokama", "content": "Mavzuning asosiy jihatlari chuqur tahlil qilinadi. Turli yondashuvlar solishtirma tahlil qilinadi. Muammoning sabablari va oqibatlari. Amaliy misollar va statistik ma'lumotlar. O'zbekiston sharoitida tahlil."}},
    {{"heading": "Amaliy ahamiyati va qo'llanilishi", "content": "Mavzuning amaliy hayotda qo'llanilishi. Iqtisodiy, ijtimoiy va madaniy ahamiyati. Sohadagi muammolar va yechim yo'llari. Kelajak rivojlanish istiqbollari. Tavsiyalar va takliflar."}},
    {{"heading": "Xulosa", "content": "Barcha asosiy fikrlar qisqa xulosasi. Tadqiqot natijalari. Amaliy tavsiyalar. Kelajak tadqiqotlar uchun yo'nalishlar. Mavzuning umumiy baholash."}},
    {{"heading": "Foydalanilgan adabiyotlar", "content": "1. Karimov I.A. O'zbekiston XXI asr bo'sag'asida. — T.: O'zbekiston, 1997.\n2. Mirziyoyev Sh.M. Erkin va farovon, demokratik O'zbekiston davlatini birgalikda barpo etamiz. — T.: 2016.\n3. [Mavzu bo'yicha xorijiy manba]. — Moskva: Nauka, 2020.\n4. [Mavzu bo'yicha o'zbek muallifli manba]. — Toshkent: Fan, 2021.\n5. [Elektron manba]: www.ziyonet.uz"}}
  ]
}}""",

            "amaliy": f"""Amaliy ish uchun professional kontent tayyorla.
FAQAT JSON format, boshqa hech narsa yozma.

MUHIM: Har bir bo'lim 200-300 so'zdan iborat, to'liq jumlalar bilan.

{{
  "title": "{topic}",
  "sections": [
    {{"heading": "Ishning maqsadi va vazifalari", "content": "Amaliy ishning asosiy maqsadi. Qo'yilgan vazifalar ro'yxati va har birining izohi. Kutilgan natijalar. Tadqiqot ob'ekti va predmeti. Ishning amaliy ahamiyati."}},
    {{"heading": "Nazariy asos", "content": "Mavzu bo'yicha asosiy nazariy ma'lumotlar. Ilmiy ta'riflar va tushunchalar. Mavjud metodlar va yondashuvlar. Xorijiy va mahalliy tadqiqotlar natijalari. Nazariy asoslanish."}},
    {{"heading": "Ishlatilgan metodlar va vositalar", "content": "Qo'llangan tadqiqot metodlari batafsil. Asbob-uskunalar va vositalar. Eksperiment yoki kuzatuv sharoitlari. Ma'lumotlar to'plash usullari. Tahlil metodologiyasi."}},
    {{"heading": "Amaliy qism: bajarilgan ishlar", "content": "Birinchi bosqich bajarilishi. Ikkinchi bosqich natijalari. Olingan ma'lumotlar tahlili. Jadvallar va grafiklar izohi. Kutilgan va real natijalar solishtirmasi."}},
    {{"heading": "Natijalar tahlili va muhokama", "content": "Olingan natijalarning tahlili. Musbat va manfiy tomonlar. Xatolar va ularning sabablari. Takomillashtirish yo'llari. Natijalarning amaliy ahamiyati."}},
    {{"heading": "Xulosa va tavsiyalar", "content": "Asosiy xulosalar. Maqsadga erishilganlik darajasi. Amaliy tavsiyalar. Keyingi tadqiqotlar uchun yo'nalishlar. Umumiy baholash."}}
  ]
}}""",

            "referat": f"""Referat uchun professional akademik kontent tayyorla.
FAQAT JSON format, boshqa hech narsa yozma.

MUHIM: Har bir bo'lim 250-400 so'zdan iborat, professional uslubda.

{{
  "title": "{topic}",
  "sections": [
    {{"heading": "Kirish", "content": "Mavzuning dolzarbligi va zamonaviy ahamiyati. Tadqiqot maqsadi va vazifalari. Mavzu bo'yicha ilmiy ishlar ko'rib chiqilishi. Ishning tuzilishi haqida ma'lumot. Metodologik asos."}},
    {{"heading": "Mavzuning tarixiy taraqqiyoti", "content": "Mavzuning paydo bo'lishi va rivojlanish tarixi. Turli davrlarda munosabat. Muhim kashfiyotlar va burilish nuqtalar. Taniqli olimlar va ularning hissasi. Rivojlanish bosqichlari."}},
    {{"heading": "{topic[:60]} mohiyati va xususiyatlari", "content": "Asosiy tushunchalar va ilmiy ta'riflar. Mohiyati va xarakterli belgilari. Turlari va tasnifi. Boshqa tushunchalar bilan bog'liqligi. Zamonaviy ta'riflar."}},
    {{"heading": "Zamonaviy holat va tendentsiyalar", "content": "Hozirgi vaqtdagi holat tahlili. Rivojlangan davlatlar tajribasi. O'zbekistondagi holat. Yangi tendentsiyalar va yo'nalishlar. Raqamli ma'lumotlar va statistika."}},
    {{"heading": "Muammo va yechim yo'llari", "content": "Mavjud muammolar tahlili. Hal qilinmagan masalalar. Xorijiy tajriba va yechimlar. O'zbekiston uchun tavsiyalar. Kelajak istiqbollari."}},
    {{"heading": "Xulosa", "content": "Asosiy xulosalar bayoni. Tadqiqot natijalari. Amaliy ahamiyati. Kelajak tadqiqotlar uchun tavsiyalar. Umumiy baholash."}},
    {{"heading": "Adabiyotlar ro'yxati", "content": "1. Mirziyoyev Sh.M. Yangi O'zbekiston strategiyasi. — T.: 2021.\n2. [Mavzu muallifi]. [Kitob nomi]. — Toshkent: Fan, 2022.\n3. [Xorijiy muallif]. [Xorijiy manba]. — Moskva, 2020.\n4. [Dissertatsiya yoki ilmiy maqola]. — T.: 2023.\n5. Elektron manba: www.edu.uz"}}
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
