from __future__ import annotations

import html
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "SPRINT_BACKLOG_FEATURE_WISE.md"
HTML_OUTPUT = ROOT / "docs" / "SPRINT_BACKLOG_FEATURE_WISE.html"
PDF_OUTPUT = ROOT / "docs" / "SPRINT_BACKLOG_FEATURE_WISE.pdf"
SIMPLE_HTML_OUTPUT = ROOT / "docs" / "SPRINT_BACKLOG_FEATURE_WISE_SIMPLE.html"
SIMPLE_PDF_OUTPUT = ROOT / "docs" / "SPRINT_BACKLOG_FEATURE_WISE_SIMPLE.pdf"

TASK_HEADERS = ["#", "Key", "Jira title", "Description", "Needs first"]
SIMPLE_DROPPED_HEADERS = {"Key", "Needs first"}


def inline_markdown(text: str) -> str:
    escaped = html.escape(text.strip())
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"`(.+?)`", r"<span class=\"label\">\1</span>", escaped)
    return escaped


def parse_table(lines: list[str], start: int, simple: bool = False) -> tuple[str, int]:
    rows: list[list[str]] = []
    index = start
    while index < len(lines) and lines[index].strip().startswith("|"):
        cells = [cell.strip() for cell in lines[index].strip().strip("|").split("|")]
        rows.append(cells)
        index += 1

    headers = rows[0]
    body = rows[2:]
    if headers == TASK_HEADERS:
        if simple:
            keep = [i for i, name in enumerate(headers) if name not in SIMPLE_DROPPED_HEADERS]
            headers = [headers[i] for i in keep]
            body = [[row[i] for i in keep] for row in body]
            table_class = "tasks simple"
            widths = [4, 38, 58]
        else:
            table_class = "tasks"
            widths = [3, 11, 26, 48, 12]
    else:
        table_class = "coverage"
        widths = [16, 21, 21, 21, 21]

    output = [f'<table class="{table_class}">', "<colgroup>"]
    output.extend(f'<col style="width:{width}%">' for width in widths)
    output.extend(["</colgroup>", "<thead><tr>"])
    output.extend(f"<th>{inline_markdown(cell)}</th>" for cell in headers)
    output.append("</tr></thead><tbody>")
    for row in body:
        output.append("<tr>")
        output.extend(f"<td>{inline_markdown(cell)}</td>" for cell in row)
        output.append("</tr>")
    output.append("</tbody></table>")
    return "".join(output), index


def markdown_to_html(markdown: str, simple: bool = False) -> str:
    lines = markdown.splitlines()
    body: list[str] = []
    index = 0
    sprint_number = 0
    in_code = False
    code_lines: list[str] = []

    while index < len(lines):
        stripped = lines[index].strip()
        if stripped == "```":
            if in_code:
                body.append(f"<pre>{html.escape(chr(10).join(code_lines))}</pre>")
                code_lines = []
                in_code = False
            else:
                in_code = True
            index += 1
            continue
        if in_code:
            code_lines.append(lines[index])
            index += 1
            continue
        if not stripped or stripped == "---":
            index += 1
            continue
        if stripped.startswith("# "):
            body.append(f'<header class="document-title"><h1>{inline_markdown(stripped[2:])}</h1>'
                        '<p>Four-sprint delivery plan · Feature-wise implementation backlog</p></header>')
        elif stripped.startswith("## Sprint"):
            if sprint_number:
                body.append("</section>")
            sprint_number += 1
            body.append(
                f'<section class="sprint sprint-{sprint_number}">'
                f'<div class="sprint-heading"><span class="sprint-number">0{sprint_number}</span>'
                f'<h2>{inline_markdown(stripped[3:])}</h2></div>'
            )
        elif stripped.startswith("## "):
            if sprint_number:
                body.append("</section>")
                sprint_number = 0
            body.append(f'<section class="appendix"><h2>{inline_markdown(stripped[3:])}</h2>')
        elif stripped.startswith("|"):
            table, index = parse_table(lines, index, simple)
            body.append(table)
            continue
        elif stripped.startswith("**Sprint outcome:**"):
            text = stripped
            while index + 1 < len(lines) and lines[index + 1].strip() and not lines[index + 1].startswith("#"):
                index += 1
                text += " " + lines[index].strip()
            body.append(f'<div class="outcome">{inline_markdown(text)}</div>')
        elif stripped.startswith("**"):
            body.append(f'<div class="metadata">{inline_markdown(stripped)}</div>')
        else:
            text = stripped
            while index + 1 < len(lines) and lines[index + 1].strip() and not lines[index + 1].startswith(("#", "|", "```")):
                index += 1
                text += " " + lines[index].strip()
            body.append(f"<p>{inline_markdown(text)}</p>")
        index += 1

    if sprint_number or body:
        body.append("</section>")
    return "\n".join(body)


def build_document(content: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>AI-SPM Feature-Wise Sprint Backlog</title>
<style>
  @page {{ size: A4 landscape; margin: 11mm 10mm 14mm; }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    color: #172033;
    background: #fff;
    font-family: "DejaVu Sans", Arial, sans-serif;
    font-size: 8.5pt;
    line-height: 1.35;
  }}
  .document-title {{
    border-bottom: 3px solid #6d5dfc;
    margin-bottom: 7mm;
    padding: 0 0 4mm;
  }}
  .document-title h1 {{ color: #172033; font-size: 23pt; margin: 0 0 1mm; }}
  .document-title p {{ color: #657089; font-size: 9.5pt; margin: 0; }}
  section {{ page-break-before: always; }}
  section.sprint-1 {{ page-break-before: auto; }}
  .sprint-heading {{
    align-items: center;
    display: -webkit-box;
    display: flex;
    margin-bottom: 2mm;
  }}
  .sprint-number {{
    background: #6d5dfc;
    border-radius: 5px;
    color: #fff;
    display: inline-block;
    font-size: 15pt;
    font-weight: 700;
    margin-right: 3mm;
    padding: 2mm 3mm;
  }}
  h2 {{ color: #172033; font-size: 16pt; margin: 0; }}
  .metadata {{ color: #657089; margin: 0 0 4mm 14mm; }}
  .label {{
    background: #eeeafd;
    border: 1px solid #d8d1fc;
    border-radius: 7px;
    color: #5141cf;
    font-size: 7.5pt;
    font-weight: 700;
    padding: 1px 5px;
    white-space: nowrap;
  }}
  table {{
    border-collapse: separate;
    border-spacing: 0;
    table-layout: fixed;
    width: 100%;
  }}
  thead {{ display: table-header-group; }}
  tr {{ page-break-inside: avoid; }}
  th {{
    background: #292d45;
    color: #fff;
    font-size: 7.8pt;
    letter-spacing: .2px;
    padding: 2.3mm 2mm;
    text-align: left;
    text-transform: uppercase;
  }}
  th:first-child {{ border-radius: 5px 0 0 0; }}
  th:last-child {{ border-radius: 0 5px 0 0; }}
  td {{
    border-bottom: 1px solid #dfe3ec;
    border-right: 1px solid #e8ebf2;
    padding: 2.1mm 2mm;
    vertical-align: top;
    overflow-wrap: anywhere;
    word-break: break-word;
    white-space: normal;
  }}
  td:first-child {{ border-left: 1px solid #e8ebf2; }}
  tbody tr:nth-child(even) td {{ background: #f7f8fc; }}

  table.tasks th:first-child {{ text-align: center; }}
  table.tasks td:first-child {{
    color: #68728a;
    font-weight: 700;
    text-align: center;
    white-space: nowrap;
  }}
  table.tasks td:nth-child(2) {{
    color: #5646d8;
    font-weight: 700;
    white-space: nowrap;
  }}
  table.tasks td:nth-child(3) {{ color: #172033; font-weight: 700; }}
  table.tasks td:last-child {{ color: #5d6780; font-size: 8pt; }}

  table.tasks.simple {{ font-size: 9pt; }}
  table.tasks.simple td:nth-child(2) {{
    color: #172033;
    font-weight: 700;
    white-space: normal;
  }}
  table.tasks.simple td:last-child {{ color: #4a5468; font-size: 8.6pt; }}

  table.coverage {{ font-size: 8.2pt; }}
  table.coverage th:first-child {{ text-align: left; }}
  table.coverage td {{
    color: #172033;
    font-weight: 400;
    line-height: 1.4;
  }}
  table.coverage td:first-child {{
    color: #172033;
    font-weight: 700;
    text-align: left;
    white-space: nowrap;
  }}

  .outcome {{
    background: #eef9f4;
    border-left: 4px solid #21a675;
    border-radius: 4px;
    color: #1f5f49;
    margin-top: 4mm;
    padding: 3mm 4mm;
  }}
  .appendix {{ page-break-before: always; }}
  .appendix h2 {{
    border-bottom: 2px solid #6d5dfc;
    margin-bottom: 5mm;
    padding-bottom: 2mm;
  }}
  pre {{
    background: #172033;
    border-radius: 6px;
    color: #e9edff;
    font-family: "DejaVu Sans Mono", monospace;
    font-size: 8pt;
    line-height: 1.65;
    padding: 6mm;
    white-space: pre-wrap;
  }}
</style>
</head>
<body>
{content}
</body>
</html>
"""


def render(markdown: str, html_path: Path, pdf_path: Path, simple: bool) -> None:
    html_path.write_text(build_document(markdown_to_html(markdown, simple)), encoding="utf-8")
    subprocess.run(
        [
            "google-chrome",
            "--headless",
            "--no-sandbox",
            "--disable-gpu",
            "--no-pdf-header-footer",
            f"--print-to-pdf={pdf_path}",
            html_path.as_uri(),
        ],
        check=True,
    )
    print(pdf_path)


def main() -> None:
    markdown = SOURCE.read_text(encoding="utf-8")
    render(markdown, HTML_OUTPUT, PDF_OUTPUT, simple=False)
    render(markdown, SIMPLE_HTML_OUTPUT, SIMPLE_PDF_OUTPUT, simple=True)


if __name__ == "__main__":
    main()
