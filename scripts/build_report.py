"""Turn the generated experiment Markdown into a printable PDF.

Optional authoring dependency: reportlab>=4. Experiments need only NumPy.
Usage: python scripts/build_report.py --results outputs/default
"""
import argparse
from html import escape
import json
from pathlib import Path
import re
import shutil

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, PageBreak
from reportlab.graphics.shapes import Drawing, Rect, String


def register_font():
    font_path = Path("C:/Windows/Fonts/simhei.ttf")
    if font_path.exists():
        pdfmetrics.registerFont(TTFont("ReportChinese", str(font_path)))
        return "ReportChinese"
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    return "STSong-Light"


def chart(title, labels, values, font):
    width = 480
    height = 55 + len(values) * 29
    drawing = Drawing(width, height)
    maximum = max(values) or 1
    drawing.add(String(0, height-18, title, fontName=font, fontSize=11, fillColor=colors.HexColor("#20382b")))
    for i, (label, value) in enumerate(zip(labels, values)):
        y = height - 50 - i * 29
        drawing.add(String(0, y+4, str(label), fontName=font, fontSize=9))
        bar_width = value / maximum * 305
        drawing.add(Rect(92, y, bar_width, 16, fillColor=colors.HexColor("#347056"), strokeColor=None))
        text = f"{value:.4f}" if value < 100 else str(int(value))
        drawing.add(String(100+bar_width, y+4, text, fontName=font, fontSize=9))
    return drawing


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", default="outputs/default")
    parser.add_argument("--output", default="deliverables/project_report.pdf")
    args = parser.parse_args()
    source = Path(args.results)
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    font = register_font()
    styles = getSampleStyleSheet()
    body = ParagraphStyle("ChineseBody", fontName=font, fontSize=10.2, leading=16.5,
                          spaceAfter=9, wordWrap="CJK", allowOrphans=0, allowWidows=0,
                          textColor=colors.HexColor("#182b22"))
    title = ParagraphStyle("ChineseTitle", parent=body, fontSize=21, leading=31,
                           spaceAfter=17, textColor=colors.black)
    heading = ParagraphStyle("ChineseHeading", parent=body, fontSize=14, leading=21,
                             spaceBefore=14, spaceAfter=10, keepWithNext=True, textColor=colors.black)
    table_style = ParagraphStyle("TableText", parent=body, fontSize=8.0, leading=11.5, spaceAfter=0)
    code_style = ParagraphStyle("Code", parent=body, fontSize=8.5, leading=13,
                               backColor=colors.HexColor("#f0f3ef"), borderPadding=8)
    stats = json.loads((source/"data_stats.json").read_text(encoding="utf-8"))
    results = json.loads((source/"metrics.json").read_text(encoding="utf-8"))
    story, pending_table, code_lines, in_code = [], [], [], False

    def inline(text):
        # SimHei does not cover every Unicode math glyph; use unambiguous ASCII.
        text = text.replace("−", "-").replace("²", "^2").replace("≥", ">=").replace("∩", " intersect ")
        text = escape(text)
        text = re.sub(r'\[([^\]]+)\]\((https?://[^)]+)\)', r'<link href="\2" color="#205f43">\1</link>', text)
        return text.replace("`", "")

    def flush_table():
        if not pending_table:
            return
        cells = [[Paragraph(inline(c), table_style) for c in row] for row in pending_table]
        ncols = len(cells[0])
        widths = {3: [90, 80, 309], 4: [70, 88, 91, 230], 7: [69, 64, 64, 64, 64, 78, 76]}.get(ncols)
        table = Table(cells, colWidths=widths, repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#e6eee7")),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#f7f9f6")]),
            ("GRID", (0,0), (-1,-1), 0.4, colors.HexColor("#c9d4cb")),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
            ("LEFTPADDING", (0,0), (-1,-1), 7), ("RIGHTPADDING", (0,0), (-1,-1), 7),
            ("TOPPADDING", (0,0), (-1,-1), 8), ("BOTTOMPADDING", (0,0), (-1,-1), 8),
        ]))
        story.append(KeepTogether([Spacer(1, 3), table, Spacer(1, 12)]))
        pending_table.clear()

    for line in (source/"report.md").read_text(encoding="utf-8").splitlines():
        if line.startswith("```"):
            in_code = not in_code
            if not in_code:
                story.append(Paragraph("<br/>".join(escape(c) for c in code_lines), code_style))
                code_lines.clear()
            continue
        if in_code:
            code_lines.append(line)
            continue
        if line.startswith("|"):
            if not re.fullmatch(r'[| :\-]+', line):
                pending_table.append([c.strip() for c in line.strip("|").split("|")])
            continue
        flush_table()
        if not line.strip():
            continue
        if line.startswith("# "):
            story.append(Paragraph(inline(line[2:]), title))
        elif line.startswith("## "):
            if line.startswith(("## 3 ", "## 5 ", "## 8 ")):
                story.append(PageBreak())
            story.append(Paragraph(inline(line[3:]), heading))
        elif line.startswith("!["):
            if "distribution" in line:
                plot = chart("评分分布  横轴从零起点", list(stats["rating_distribution"]),
                             list(stats["rating_distribution"].values()), font)
            elif "rating_rmse" in line:
                story.append(PageBreak())
                rating = [r for r in results if "rmse" in r]
                plot = chart("测试 RMSE  越低越好", [r["model"] for r in rating], [r["rmse"] for r in rating], font)
            else:
                plot = chart("测试 NDCG@10  越高越好", [r["model"] for r in results], [r["ndcg"] for r in results], font)
            story.append(KeepTogether([Spacer(1, 6), plot, Spacer(1, 8)]))
        else:
            story.append(Paragraph(inline(line), body))
    flush_table()

    def page_number(canvas, document):
        canvas.setFont(font, 8)
        canvas.setFillColor(colors.HexColor("#52695b"))
        canvas.drawRightString(A4[0]-55, 29, f"{document.page}")

    doc = SimpleDocTemplate(str(destination), pagesize=A4, rightMargin=55, leftMargin=55,
                           topMargin=47, bottomMargin=47,
                           title="Amazon 园艺商品评分预测与 Top-10 推荐实验报告", author="")
    doc.build(story, onFirstPage=page_number, onLaterPages=page_number)
    shutil.copyfile(source/"report.md", destination.parent/"project_report.md")
    shutil.copyfile(source/"report.html", destination.parent/"project_report.html")
    shutil.copytree(source/"figures", destination.parent/"figures", dirs_exist_ok=True)
    print(f"Created {destination.resolve()}")


if __name__ == "__main__":
    main()
