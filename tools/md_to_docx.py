#!/usr/bin/env python3
"""Convert Markdown files to beautifully styled Word (.docx) documents."""

import os
import re
import sys
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn

def set_cell_background(cell, fill_hex):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>')
    tcPr.append(shd)

def set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = parse_xml(f'<w:tcMar {nsdecls("w")}><w:top w:w="{top}" w:type="dxa"/><w:bottom w:w="{bottom}" w:type="dxa"/><w:left w:w="{left}" w:type="dxa"/><w:right w:w="{right}" w:type="dxa"/></w:tcMar>')
    tcPr.append(tcMar)

def add_styled_heading(doc, text, level):
    h = doc.add_heading(level=level)
    run = h.add_run(text)
    run.font.name = "Calibri"
    if level == 1:
        run.font.size = Pt(20)
        run.font.bold = True
        run.font.color.rgb = RGBColor(0x1B, 0x36, 0x5D) # Navy
        h.paragraph_format.space_before = Pt(16)
        h.paragraph_format.space_after = Pt(8)
    elif level == 2:
        run.font.size = Pt(15)
        run.font.bold = True
        run.font.color.rgb = RGBColor(0x2E, 0x5B, 0x88) # Slate blue
        h.paragraph_format.space_before = Pt(14)
        h.paragraph_format.space_after = Pt(6)
    elif level == 3:
        run.font.size = Pt(12)
        run.font.bold = True
        run.font.color.rgb = RGBColor(0x33, 0x33, 0x33)
        h.paragraph_format.space_before = Pt(10)
        h.paragraph_format.space_after = Pt(4)
    return h

def add_formatted_runs(paragraph, text, default_color=None, is_bold=False, is_italic=False):
    # Parses bold **text**, code `text`, italic *text*
    # Tokenize by markdown styles
    pattern = re.compile(r'(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)')
    tokens = pattern.split(text)
    for token in tokens:
        if not token:
            continue
        if token.startswith('**') and token.endswith('**'):
            run = paragraph.add_run(token[2:-2])
            run.bold = True
            run.font.name = "Calibri"
            if default_color:
                run.font.color.rgb = default_color
        elif token.startswith('*') and token.endswith('*'):
            run = paragraph.add_run(token[1:-1])
            run.italic = True
            run.font.name = "Calibri"
            if default_color:
                run.font.color.rgb = default_color
        elif token.startswith('`') and token.endswith('`'):
            run = paragraph.add_run(token[1:-1])
            run.font.name = "Consolas"
            run.font.size = Pt(9.5)
            run.font.color.rgb = RGBColor(0xA3, 0x15, 0x15) # Dark red for code
        else:
            run = paragraph.add_run(token)
            run.bold = is_bold
            run.italic = is_italic
            run.font.name = "Calibri"
            if default_color:
                run.font.color.rgb = default_color

def convert_md_to_docx(md_path, docx_path):
    with open(md_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    doc = Document()
    
    # Page setup: Margins 0.8 in
    for section in doc.sections:
        section.top_margin = Inches(0.8)
        section.bottom_margin = Inches(0.8)
        section.left_margin = Inches(0.8)
        section.right_margin = Inches(0.8)
    
    # Style standard paragraph
    style_normal = doc.styles['Normal']
    style_normal.font.name = 'Calibri'
    style_normal.font.size = Pt(11)
    style_normal.font.color.rgb = RGBColor(0x22, 0x22, 0x22)
    style_normal.paragraph_format.line_spacing = 1.15
    style_normal.paragraph_format.space_after = Pt(4)

    i = 0
    n = len(lines)
    in_code_block = False
    code_lines = []

    while i < n:
        line = lines[i].rstrip('\r\n')
        
        # Check code blocks
        if line.startswith('```'):
            if in_code_block:
                # end code block
                in_code_block = False
                code_text = "\n".join(code_lines)
                table = doc.add_table(rows=1, cols=1)
                table.alignment = WD_TABLE_ALIGNMENT.CENTER
                cell = table.cell(0, 0)
                set_cell_background(cell, "F4F4F4")
                set_cell_margins(cell, top=120, bottom=120, left=180, right=180)
                cp = cell.paragraphs[0]
                cp.paragraph_format.space_before = Pt(2)
                cp.paragraph_format.space_after = Pt(2)
                run = cp.add_run(code_text)
                run.font.name = "Consolas"
                run.font.size = Pt(9.5)
                run.font.color.rgb = RGBColor(0x22, 0x22, 0x22)
                p_spacer = doc.add_paragraph()
                p_spacer.paragraph_format.space_after = Pt(4)
                code_lines = []
            else:
                in_code_block = True
                code_lines = []
            i += 1
            continue
        
        if in_code_block:
            code_lines.append(line)
            i += 1
            continue

        # Check table
        if line.startswith('|') and '|' in line[1:]:
            # Collect all table rows
            table_lines = []
            while i < n and lines[i].strip().startswith('|'):
                table_lines.append(lines[i].strip())
                i += 1
            
            # Filter out separator line like |---|---|
            parsed_rows = []
            for tl in table_lines:
                # split by |
                parts = [c.strip() for c in tl.split('|')[1:-1]]
                if all(re.match(r'^:?-+:?$', p) for p in parts if p):
                    continue # separator row
                parsed_rows.append(parts)
            
            if parsed_rows:
                num_cols = max(len(r) for r in parsed_rows)
                tbl = doc.add_table(rows=len(parsed_rows), cols=num_cols)
                tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
                tbl.autofit = True
                
                for r_idx, row_data in enumerate(parsed_rows):
                    is_header = (r_idx == 0)
                    for c_idx in range(num_cols):
                        val = row_data[c_idx] if c_idx < len(row_data) else ""
                        val = val.replace('<br>', '\n')
                        cell = tbl.cell(r_idx, c_idx)
                        set_cell_margins(cell, top=80, bottom=80, left=120, right=120)
                        
                        if is_header:
                            set_cell_background(cell, "2E5B88") # Navy header
                            cp = cell.paragraphs[0]
                            cp.paragraph_format.space_before = Pt(2)
                            cp.paragraph_format.space_after = Pt(2)
                            add_formatted_runs(cp, val, default_color=RGBColor(0xFF, 0xFF, 0xFF), is_bold=True)
                        else:
                            bg = "F9FBFD" if r_idx % 2 == 1 else "FFFFFF"
                            set_cell_background(cell, bg)
                            cp = cell.paragraphs[0]
                            cp.paragraph_format.space_before = Pt(2)
                            cp.paragraph_format.space_after = Pt(2)
                            add_formatted_runs(cp, val)
                
                p_spacer = doc.add_paragraph()
                p_spacer.paragraph_format.space_after = Pt(6)
            continue

        # Check Headings
        if line.startswith('# '):
            add_styled_heading(doc, line[2:].strip(), level=1)
        elif line.startswith('## '):
            add_styled_heading(doc, line[3:].strip(), level=2)
        elif line.startswith('### '):
            add_styled_heading(doc, line[4:].strip(), level=3)
        elif line.startswith('#### '):
            add_styled_heading(doc, line[5:].strip(), level=3)
        elif line.startswith('> '):
            # Blockquote
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Inches(0.3)
            p.paragraph_format.space_before = Pt(4)
            p.paragraph_format.space_after = Pt(6)
            add_formatted_runs(p, line[2:].strip(), default_color=RGBColor(0x3B, 0x4B, 0x5B), is_italic=True)
        elif line.strip() == '---':
            # Horizontal rule -> subtle divider
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(6)
            p.paragraph_format.space_after = Pt(6)
            run = p.add_run("―" * 35)
            run.font.color.rgb = RGBColor(0xCC, 0xCC, 0xCC)
        elif line.strip().startswith('- ') or line.strip().startswith('* '):
            # Bullet point
            p = doc.add_paragraph(style='List Bullet')
            p.paragraph_format.space_before = Pt(1)
            p.paragraph_format.space_after = Pt(2)
            content = line.strip()[2:]
            add_formatted_runs(p, content)
        elif re.match(r'^\d+\.\s', line.strip()):
            # Numbered list
            m = re.match(r'^(\d+\.)\s*(.*)', line.strip())
            p = doc.add_paragraph(style='List Number')
            p.paragraph_format.space_before = Pt(1)
            p.paragraph_format.space_after = Pt(2)
            add_formatted_runs(p, m.group(2))
        elif line.strip():
            # Standard paragraph
            p = doc.add_paragraph()
            add_formatted_runs(p, line)
        else:
            # Empty line
            pass
        
        i += 1

    doc.save(docx_path)
    print(f"Successfully generated: {docx_path}")

if __name__ == "__main__":
    src = "vmlu_docs/02_upper_bound_campaign/GITHUB_ISSUE_UPPER_BOUND_18_BATCHES.md"
    dst1 = "vmlu_docs/02_upper_bound_campaign/Bao_Cao_Upper_Bound_1589_Cau.docx"
    dst2 = "report_upper_bound_1589_cau.docx"
    convert_md_to_docx(src, dst1)
    import shutil
    shutil.copyfile(dst1, dst2)
    print(f"Copied to root: {dst2}")
