#!/bin/bash
# EduBot o'rnatish skripti

echo "🤖 EduBot o'rnatilmoqda..."

# Python paketlari
echo "📦 Python paketlari o'rnatilmoqda..."
pip install -r requirements.txt

# Node.js paketlari (PPTX va DOCX uchun)
echo "📦 Node.js paketlari o'rnatilmoqda..."
npm install pptxgenjs docx

# .env faylini tekshirish
if [ ! -f .env ]; then
    cp .env.example .env
    echo "⚠️  .env fayli yaratildi. Iltimos to'ldiring!"
    echo "   nano .env"
    exit 1
fi

echo "✅ O'rnatish tugadi!"
echo "🚀 Ishga tushirish: python bot.py"
