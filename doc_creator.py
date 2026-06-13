"""
Hujjat yaratuvchi modul
PPTX va DOCX fayllarni generatsiya qiladi
"""

import os
import asyncio
import subprocess
import json
import tempfile
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

OUTPUT_DIR = "/tmp/edubot_files"
os.makedirs(OUTPUT_DIR, exist_ok=True)


async def create_pptx(topic: str, content: dict) -> str:
    """PptxGenJS yordamida prezentatsiya yaratish"""
    safe_name = "".join(c for c in topic[:30] if c.isalnum() or c in " _-").strip()
    output_path = os.path.join(OUTPUT_DIR, f"pptx_{safe_name}_{datetime.now().strftime('%H%M%S')}.pptx")

    js_code = _build_pptx_js(topic, content, output_path)

    js_file = tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False)
    js_file.write(js_code)
    js_file.close()

    try:
        proc = await asyncio.create_subprocess_exec(
            "node", js_file.name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)

        if proc.returncode != 0:
            logger.error(f"PPTX xato: {stderr.decode()}")
            raise Exception(f"PPTX yaratish xatosi: {stderr.decode()}")

        return output_path
    finally:
        os.unlink(js_file.name)


def _build_pptx_js(topic: str, content: dict, output_path: str) -> str:
    sections = content.get("sections", [])
    title = content.get("title", topic)

    # Rang palitrasini tanlash
    palette = {
        "primary": "1A3C5E",    # To'q ko'k
        "secondary": "2D7DD2",  # Yorqin ko'k
        "accent": "F0A500",     # Oltin
        "light": "EAF2FB",      # Och ko'k
        "white": "FFFFFF",
        "dark": "1A1A2E",
        "text": "2C3E50",
    }

    slides_js = []

    # 1. TITLE SLIDE
    slides_js.append(f"""
    // ===== SARLAVHA SLAYDI =====
    let slide1 = pres.addSlide();
    slide1.background = {{ color: "{palette['primary']}" }};
    
    // Yuqori dekoratsiya
    slide1.addShape(pres.shapes.RECTANGLE, {{
        x: 0, y: 0, w: 10, h: 0.08,
        fill: {{ color: "{palette['accent']}" }}, line: {{ color: "{palette['accent']}" }}
    }});
    
    // Pastki dekoratsiya
    slide1.addShape(pres.shapes.RECTANGLE, {{
        x: 0, y: 5.545, w: 10, h: 0.08,
        fill: {{ color: "{palette['accent']}" }}, line: {{ color: "{palette['accent']}" }}
    }});
    
    // Fon shakli
    slide1.addShape(pres.shapes.ROUNDED_RECTANGLE, {{
        x: 0.5, y: 1.0, w: 9, h: 3.2,
        fill: {{ color: "{palette['secondary']}", transparency: 85 }},
        line: {{ color: "{palette['secondary']}", width: 1.5, transparency: 60 }},
        rectRadius: 0.15
    }});
    
    // Sarlavha
    slide1.addText({json.dumps(title)}, {{
        x: 0.7, y: 1.3, w: 8.6, h: 1.8,
        fontSize: 36, bold: true, color: "{palette['white']}",
        align: "center", valign: "middle",
        fontFace: "Calibri", wrap: true
    }});
    
    // Mavzu
    slide1.addText("Mavzu: {topic[:60].replace(chr(34), chr(39))}", {{
        x: 0.7, y: 3.2, w: 8.6, h: 0.5,
        fontSize: 16, color: "{palette['accent']}",
        align: "center", fontFace: "Calibri"
    }});
    
    // Sana
    let today = new Date().toLocaleDateString('uz-UZ', {{year:'numeric', month:'long', day:'numeric'}});
    slide1.addText(today, {{
        x: 0.7, y: 4.8, w: 8.6, h: 0.4,
        fontSize: 12, color: "AABBCC",
        align: "center", fontFace: "Calibri"
    }});
    """)

    # 2. MUNDARIJA SLAYDI
    toc_items = [s["heading"] for s in sections]
    toc_bullets = []
    for i, item in enumerate(toc_items, 1):
        toc_bullets.append(f'{{ text: "{i}. {item}", options: {{ bullet: false, breakLine: true, fontSize: 16, color: "{palette["text"]}" }} }}')

    slides_js.append(f"""
    // ===== MUNDARIJA =====
    let slide_toc = pres.addSlide();
    slide_toc.background = {{ color: "{palette['white']}" }};
    
    // Header bg
    slide_toc.addShape(pres.shapes.RECTANGLE, {{
        x: 0, y: 0, w: 10, h: 1.1,
        fill: {{ color: "{palette['primary']}" }}, line: {{ color: "{palette['primary']}" }}
    }});
    
    slide_toc.addText("📋 Mundarija", {{
        x: 0.5, y: 0.15, w: 9, h: 0.8,
        fontSize: 28, bold: true, color: "{palette['white']}",
        fontFace: "Calibri", align: "left"
    }});
    
    slide_toc.addText([{", ".join(toc_bullets)}], {{
        x: 0.8, y: 1.3, w: 8.4, h: 4,
        fontSize: 16, color: "{palette['text']}",
        fontFace: "Calibri", valign: "top",
        paraSpaceAfter: 8
    }});
    """)

    # 3. KONTENT SLAYDLARI
    icons = ["💡", "📌", "🔬", "📊", "📖", "⭐", "🎯", "🔑"]
    for idx, section in enumerate(sections):
        heading = section.get("heading", f"Bo'lim {idx+1}")
        raw_content = section.get("content", "")
        bullet_points = [p.strip() for p in raw_content.split("||") if p.strip()]
        if not bullet_points:
            bullet_points = [raw_content[:200]]

        icon = icons[idx % len(icons)]
        # Juft/toq slaydlar uchun ranglar
        bg_color = palette['white'] if idx % 2 == 0 else palette['light']

        bullet_js = []
        for bp in bullet_points[:5]:
            safe_bp = bp.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")[:150]
            bullet_js.append(f'{{ text: "{safe_bp}", options: {{ bullet: true, breakLine: true, fontSize: 15, color: "{palette["text"]}" }} }}')

        slides_js.append(f"""
    // ===== BO'LIM: {heading[:30]} =====
    let slide_{idx+2} = pres.addSlide();
    slide_{idx+2}.background = {{ color: "{bg_color}" }};
    
    // Header
    slide_{idx+2}.addShape(pres.shapes.RECTANGLE, {{
        x: 0, y: 0, w: 10, h: 1.1,
        fill: {{ color: "{palette['primary']}" }}, line: {{ color: "{palette['primary']}" }}
    }});
    
    // Raqam doirasi
    slide_{idx+2}.addShape(pres.shapes.OVAL, {{
        x: 0.3, y: 0.2, w: 0.7, h: 0.7,
        fill: {{ color: "{palette['accent']}" }}, line: {{ color: "{palette['accent']}" }}
    }});
    slide_{idx+2}.addText("{idx+1}", {{
        x: 0.3, y: 0.2, w: 0.7, h: 0.7,
        fontSize: 22, bold: true, color: "{palette['primary']}",
        align: "center", valign: "middle", fontFace: "Calibri"
    }});
    
    // Sarlavha
    slide_{idx+2}.addText("{icon} {heading[:50]}", {{
        x: 1.2, y: 0.12, w: 8.4, h: 0.9,
        fontSize: 24, bold: true, color: "{palette['white']}",
        fontFace: "Calibri", valign: "middle"
    }});
    
    // Kontent
    slide_{idx+2}.addText([{", ".join(bullet_js) if bullet_js else f'{{ text: "{raw_content[:200].replace(chr(34), chr(39))}", options: {{ fontSize: 15, color: "{palette["text"]}" }} }}'}], {{
        x: 0.5, y: 1.3, w: 9, h: 3.9,
        fontFace: "Calibri", valign: "top",
        paraSpaceAfter: 10
    }});
    
    // Pastki chiziq
    slide_{idx+2}.addShape(pres.shapes.RECTANGLE, {{
        x: 0, y: 5.5, w: 10, h: 0.125,
        fill: {{ color: "{palette['secondary']}", transparency: 70 }},
        line: {{ color: "{palette['secondary']}", transparency: 70 }}
    }});
    
    // Slayd raqami
    slide_{idx+2}.addText("{idx+2}", {{
        x: 9.3, y: 5.3, w: 0.5, h: 0.3,
        fontSize: 10, color: "999999", align: "center", fontFace: "Calibri"
    }});
    """)

    # YAKUNIY SLAYD
    slides_js.append(f"""
    // ===== YAKUNIY SLAYD =====
    let slide_end = pres.addSlide();
    slide_end.background = {{ color: "{palette['primary']}" }};
    
    slide_end.addShape(pres.shapes.RECTANGLE, {{
        x: 0, y: 0, w: 10, h: 0.08,
        fill: {{ color: "{palette['accent']}" }}, line: {{ color: "{palette['accent']}" }}
    }});
    slide_end.addShape(pres.shapes.RECTANGLE, {{
        x: 0, y: 5.545, w: 10, h: 0.08,
        fill: {{ color: "{palette['accent']}" }}, line: {{ color: "{palette['accent']}" }}
    }});
    
    slide_end.addShape(pres.shapes.ROUNDED_RECTANGLE, {{
        x: 2, y: 1.5, w: 6, h: 2.5,
        fill: {{ color: "{palette['secondary']}", transparency: 80 }},
        line: {{ color: "{palette['accent']}", width: 2 }},
        rectRadius: 0.2
    }});
    
    slide_end.addText("E'tiboringiz uchun\\nrahmat! 🙏", {{
        x: 2, y: 1.5, w: 6, h: 2.5,
        fontSize: 32, bold: true, color: "{palette['white']}",
        align: "center", valign: "middle",
        fontFace: "Calibri"
    }});
    """)

    all_slides = "\n".join(slides_js)

    return f"""
const pptxgen = require("pptxgenjs");

async function createPresentation() {{
    let pres = new pptxgen();
    pres.layout = 'LAYOUT_16x9';
    pres.title = {json.dumps(title)};
    pres.author = 'EduBot';

{all_slides}

    await pres.writeFile({{ fileName: {json.dumps(output_path)} }});
    console.log("✅ Tayyor:", {json.dumps(output_path)});
}}

createPresentation().catch(err => {{
    console.error("❌ Xato:", err);
    process.exit(1);
}});
"""


async def create_docx(topic: str, content: dict, doc_type: str) -> str:
    """docx-js yordamida Word hujjat yaratish"""
    safe_name = "".join(c for c in topic[:30] if c.isalnum() or c in " _-").strip()
    output_path = os.path.join(OUTPUT_DIR, f"docx_{safe_name}_{datetime.now().strftime('%H%M%S')}.docx")

    js_code = _build_docx_js(topic, content, doc_type, output_path)

    js_file = tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False)
    js_file.write(js_code)
    js_file.close()

    try:
        proc = await asyncio.create_subprocess_exec(
            "node", js_file.name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)

        if proc.returncode != 0:
            logger.error(f"DOCX xato: {stderr.decode()}")
            raise Exception(f"DOCX yaratish xatosi: {stderr.decode()}")

        return output_path
    finally:
        os.unlink(js_file.name)


def _build_docx_js(topic: str, content: dict, doc_type: str, output_path: str) -> str:
    sections = content.get("sections", [])
    title = content.get("title", topic)

    doc_type_names = {
        "mustaqil": "MUSTAQIL ISH",
        "amaliy": "AMALIY ISH",
        "referat": "REFERAT",
    }
    doc_type_name = doc_type_names.get(doc_type, "HUJJAT")

    # Sections JS kodini qurish
    sections_code = []
    for section in sections:
        heading = section.get("heading", "Bo'lim").replace("\\", "\\\\").replace('"', '\\"')
        body = section.get("content", "").replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

        sections_code.append(f"""
        new Paragraph({{
            children: [new TextRun({{ text: "{heading}", bold: true, size: 28, font: "Times New Roman" }})],
            heading: HeadingLevel.HEADING_1,
            spacing: {{ before: 300, after: 150 }}
        }}),
        new Paragraph({{
            children: [new TextRun({{ text: "{body}", size: 24, font: "Times New Roman" }})],
            spacing: {{ before: 0, after: 200, line: 360 }},
            indent: {{ firstLine: 720 }},
            alignment: AlignmentType.JUSTIFIED
        }}),""")

    all_sections = "\n".join(sections_code)

    return f"""
const {{ Document, Packer, Paragraph, TextRun, AlignmentType, HeadingLevel,
        Header, Footer, PageNumber, Table, TableRow, TableCell, WidthType, BorderStyle, ShadingType }} = require("docx");
const fs = require("fs");

async function createDocument() {{
    const doc = new Document({{
        styles: {{
            default: {{
                document: {{
                    run: {{ font: "Times New Roman", size: 24 }}
                }}
            }},
            paragraphStyles: [
                {{
                    id: "Heading1",
                    name: "Heading 1",
                    basedOn: "Normal",
                    next: "Normal",
                    quickFormat: true,
                    run: {{ size: 28, bold: true, font: "Times New Roman", color: "1A3C5E" }},
                    paragraph: {{
                        spacing: {{ before: 300, after: 150 }},
                        outlineLevel: 0
                    }}
                }}
            ]
        }},
        sections: [{{
            properties: {{
                page: {{
                    size: {{ width: 11906, height: 16838 }},
                    margin: {{ top: 1440, right: 1008, bottom: 1440, left: 1728 }}
                }}
            }},
            headers: {{
                default: new Header({{
                    children: [
                        new Paragraph({{
                            children: [new TextRun({{ text: "O'zbekiston Respublikasi ta'lim tizimi", size: 18, font: "Times New Roman", color: "666666" }})],
                            alignment: AlignmentType.CENTER,
                            border: {{ bottom: {{ style: BorderStyle.SINGLE, size: 3, color: "CCCCCC", space: 1 }} }}
                        }})
                    ]
                }})
            }},
            footers: {{
                default: new Footer({{
                    children: [
                        new Paragraph({{
                            children: [
                                new TextRun({{ text: "Sahifa: ", size: 18, font: "Times New Roman", color: "666666" }}),
                                new PageNumber()
                            ],
                            alignment: AlignmentType.CENTER,
                            border: {{ top: {{ style: BorderStyle.SINGLE, size: 3, color: "CCCCCC", space: 1 }} }}
                        }})
                    ]
                }})
            }},
            children: [
                // Sarlavha sahifasi
                new Paragraph({{
                    children: [new TextRun({{ text: "", size: 24 }})],
                    spacing: {{ before: 600 }}
                }}),
                new Paragraph({{
                    children: [new TextRun({{ text: "{doc_type_name}", bold: true, size: 32, font: "Times New Roman", color: "1A3C5E" }})],
                    alignment: AlignmentType.CENTER,
                    spacing: {{ before: 400, after: 200 }}
                }}),
                new Paragraph({{
                    children: [new TextRun({{ text: "Mavzu:", bold: true, size: 24, font: "Times New Roman" }})],
                    alignment: AlignmentType.CENTER,
                    spacing: {{ before: 200 }}
                }}),
                new Paragraph({{
                    children: [new TextRun({{ text: {json.dumps(title)}, bold: true, size: 28, font: "Times New Roman" }})],
                    alignment: AlignmentType.CENTER,
                    spacing: {{ before: 100, after: 600 }}
                }}),
                new Paragraph({{
                    children: [new TextRun({{ text: new Date().getFullYear() + "-yil", size: 24, font: "Times New Roman" }})],
                    alignment: AlignmentType.CENTER,
                    spacing: {{ before: 800 }}
                }}),
                
                // Sahifa kesimi
                new Paragraph({{
                    children: [{{ type: "pageBreak" }}],
                    pageBreakBefore: true
                }}),
                
                // Asosiy kontent
                {all_sections}
            ]
        }}]
    }});

    const buffer = await Packer.toBuffer(doc);
    fs.writeFileSync({json.dumps(output_path)}, buffer);
    console.log("✅ Tayyor:", {json.dumps(output_path)});
}}

createDocument().catch(err => {{
    console.error("❌ Xato:", err.message);
    process.exit(1);
}});
"""
