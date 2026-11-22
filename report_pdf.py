"""LoamLab PDF report builder.

Layout rules (so everything lines up):
  * A4 page, 16 mm left/right margins  ->  178 mm content width (CW). Every table below sums to exactly CW.
  * First page has a full-bleed branded band; later pages get a slim running header.
  * Every page has a footer with report number, generated time and "Page X of Y".

Scientific integrity (unchanged): nothing is measured, guessed or recommended by the software.
Only values typed in by the laboratory are shown; the 'position' column is a plain numeric comparison of the
lab's own value against the lab's own interval, and charts never compare different units with each other.
"""
import io, os, re
from datetime import datetime
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.graphics.shapes import Drawing, Rect, String, Polygon, Line
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, NextPageTemplate, Paragraph, Spacer,
                                Table, TableStyle, KeepTogether)

PAGE_W, PAGE_H = A4
MARGIN = 16 * mm
CW = PAGE_W - 2 * MARGIN                      # 178 mm
BAND_H = 54 * mm                              # first-page header band

DARK = colors.HexColor('#141a12'); INK = colors.HexColor('#1b2118'); MUTED = colors.HexColor('#667260')
LIME = colors.HexColor('#8fc413'); LIME_D = colors.HexColor('#5f8a08'); COPPER = colors.HexColor('#b8763d')
PALE = colors.HexColor('#f3f6ee'); ZEBRA = colors.HexColor('#fafcf7'); RULE = colors.HexColor('#d9e0d2')
OK = colors.HexColor('#3f8a1f'); LOW = colors.HexColor('#1f6fa8'); HIGH = colors.HexColor('#c2571a')

# ── fonts: drop Report-Regular.ttf / Report-Bold.ttf into ./fonts to render non-Latin scripts (e.g. Kannada) ──
_FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fonts')
REG, BOLD, UNICODE = 'Helvetica', 'Helvetica-Bold', False
try:
    _r, _b = os.path.join(_FONT_DIR, 'Report-Regular.ttf'), os.path.join(_FONT_DIR, 'Report-Bold.ttf')
    if os.path.exists(_r) and os.path.exists(_b):
        pdfmetrics.registerFont(TTFont('Report', _r)); pdfmetrics.registerFont(TTFont('Report-Bold', _b))
        REG, BOLD, UNICODE = 'Report', 'Report-Bold', True
except Exception:
    pass


def _clean(x):
    t = str(x if x not in (None, '') else '—')
    if not UNICODE:                              # built-in fonts only cover Latin-1/WinAnsi
        t = t.encode('cp1252', 'replace').decode('cp1252')
    return t


def esc(x):
    return escape(_clean(x)).replace('\n', '<br/>')


def S(name, **kw):
    base = dict(fontName=REG, fontSize=9, leading=13, textColor=INK)
    base.update(kw); return ParagraphStyle(name, **base)


ST = {
    'body': S('body'),
    'val': S('val', fontSize=9.2, leading=12.5),
    'label': S('label', fontName=BOLD, fontSize=6.6, leading=9, textColor=MUTED),
    'th': S('th', fontName=BOLD, fontSize=6.8, leading=9, textColor=colors.white),
    'thr': S('thr', fontName=BOLD, fontSize=6.8, leading=9, textColor=colors.white, alignment=TA_RIGHT),
    'num': S('num', fontName=BOLD, fontSize=10, leading=13, alignment=TA_RIGHT),
    'small': S('small', fontSize=7.4, leading=10.6, textColor=MUTED),
    'cell_big': S('cell_big', fontName=BOLD, fontSize=11.5, leading=14),
    'secno': S('secno', fontName=BOLD, fontSize=10, leading=12, textColor=LIME_D),
    'sectitle': S('sectitle', fontName=BOLD, fontSize=12, leading=15),
    'empty': S('empty', textColor=MUTED, fontSize=9),
}


def P(text, style='val'):
    return Paragraph(esc(text), ST[style])


# ── lab-interval comparison (pure numeric comparison of two lab-entered things) ─────────────────────────────
_NUM = r'[-+]?\d+(?:[.,]\d+)?'


def _f(s):
    return float(s.replace(',', '.'))


def position(value, ref):
    """Returns ('Within interval'|'Below interval'|'Above interval'|'—', colour)."""
    try:
        v = _f(str(value).strip())
    except Exception:
        return '—', MUTED
    r = str(ref or '').strip()
    m = re.match(rf'^\s*({_NUM})\s*(?:-|–|—|to)\s*({_NUM})', r)
    lo = hi = None
    if m:
        lo, hi = _f(m.group(1)), _f(m.group(2))
    else:
        m = re.match(rf'^\s*(<=|≤|<|>=|≥|>)\s*({_NUM})', r)
        if m:
            n = _f(m.group(2)); lo, hi = (None, n) if m.group(1) in ('<', '<=', '≤') else (n, None)
    if lo is None and hi is None:
        return '—', MUTED
    if lo is not None and v < lo: return 'Below interval', LOW
    if hi is not None and v > hi: return 'Above interval', HIGH
    return 'Within interval', OK


# ── page furniture ─────────────────────────────────────────────────────────────────────────────────────────
def _logo(c, x, y, s):
    """Hexagon + three soil layers mark, centred at (x,y), size s."""
    import math
    pts = [(x + s * math.cos(math.radians(60 * i + 30)), y + s * math.sin(math.radians(60 * i + 30))) for i in range(6)]
    c.setStrokeColor(COPPER); c.setLineWidth(1.3); c.setFillColor(colors.Color(0, 0, 0, 0))
    p = c.beginPath(); p.moveTo(*pts[0]); [p.lineTo(*q) for q in pts[1:]]; p.close(); c.drawPath(p, stroke=1, fill=0)
    for dy, col in ((s * .32, colors.HexColor('#d9b896')), (0, COPPER), (-s * .32, colors.HexColor('#8a5530'))):
        c.setStrokeColor(col); c.setLineWidth(1.6); c.line(x - s * .5, y + dy, x + s * .5, y + dy)


def make_canvas_class(meta):
    class NumberedCanvas(rl_canvas.Canvas):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw); self._saved = []

        def showPage(self):
            self._saved.append(dict(self.__dict__)); self._startPage()

        def save(self):
            total = len(self._saved)
            for st in self._saved:
                self.__dict__.update(st); self._decorate(total); super().showPage()
            super().save()

        def _decorate(self, total):
            c = self; first = c._pageNumber == 1
            c.saveState()
            if first:
                c.setFillColor(DARK); c.rect(0, PAGE_H - BAND_H, PAGE_W, BAND_H, stroke=0, fill=1)
                c.setFillColor(LIME); c.rect(0, PAGE_H - BAND_H - 1.2 * mm, PAGE_W, 1.2 * mm, stroke=0, fill=1)
                _logo(c, MARGIN + 5 * mm, PAGE_H - 17 * mm, 5.2 * mm)
                c.setFont(BOLD, 19); c.setFillColor(colors.white); c.drawString(MARGIN + 13 * mm, PAGE_H - 19.5 * mm, 'Loam')
                w = c.stringWidth('Loam', BOLD, 19); c.setFillColor(LIME); c.drawString(MARGIN + 13 * mm + w, PAGE_H - 19.5 * mm, 'Lab')
                c.setFont(REG, 6.8); c.setFillColor(colors.HexColor('#8d9885'))
                c.drawString(MARGIN + 13 * mm, PAGE_H - 24.5 * mm, 'SOIL TESTING APPOINTMENT & REPORT ACCESS PORTAL')
                c.setFont(BOLD, 23); c.setFillColor(colors.white); c.drawString(MARGIN, PAGE_H - 41 * mm, 'Soil Analytical Report')
                c.setFont(REG, 8.2); c.setFillColor(colors.HexColor('#b8c2ae'))
                c.drawString(MARGIN, PAGE_H - 47.5 * mm, 'Laboratory result summary')
                # right-aligned meta block
                x = PAGE_W - MARGIN; y = PAGE_H - 14 * mm
                for lab, val in (('REPORT NUMBER', meta['report_no']), ('APPOINTMENT REFERENCE', meta['code']), ('DATE OF ISSUE', meta['issued'])):
                    c.setFont(REG, 6.4); c.setFillColor(colors.HexColor('#8d9885')); c.drawRightString(x, y, lab)
                    c.setFont(BOLD, 10.5); c.setFillColor(colors.white); c.drawRightString(x, y - 4.6 * mm, _clean(val)); y -= 11.5 * mm
            else:
                c.setFillColor(DARK); c.rect(0, PAGE_H - 13 * mm, PAGE_W, 13 * mm, stroke=0, fill=1)
                c.setFillColor(LIME); c.rect(0, PAGE_H - 13.8 * mm, PAGE_W, .8 * mm, stroke=0, fill=1)
                _logo(c, MARGIN + 2.5 * mm, PAGE_H - 6.5 * mm, 2.9 * mm)
                c.setFont(BOLD, 10.5); c.setFillColor(colors.white); c.drawString(MARGIN + 8 * mm, PAGE_H - 8 * mm, 'Loam')
                w = c.stringWidth('Loam', BOLD, 10.5); c.setFillColor(LIME); c.drawString(MARGIN + 8 * mm + w, PAGE_H - 8 * mm, 'Lab')
                c.setFont(REG, 7.4); c.setFillColor(colors.HexColor('#b8c2ae'))
                c.drawRightString(PAGE_W - MARGIN, PAGE_H - 8 * mm, f"Soil Analytical Report  ·  {_clean(meta['report_no'])}")
            # footer
            c.setStrokeColor(RULE); c.setLineWidth(.6); c.line(MARGIN, 15 * mm, PAGE_W - MARGIN, 15 * mm)
            c.setFont(REG, 6.8); c.setFillColor(MUTED)
            c.drawString(MARGIN, 10.6 * mm, f"LoamLab  ·  Report {_clean(meta['report_no'])}  ·  Generated {meta['generated']}")
            c.setFont(BOLD, 7.2); c.setFillColor(INK)
            c.drawRightString(PAGE_W - MARGIN, 10.6 * mm, f'Page {c._pageNumber} of {total}')
            c.setFont(REG, 6.2); c.setFillColor(MUTED)
            c.drawString(MARGIN, 6.6 * mm, 'Confidential — intended for the named customer and the issuing laboratory.')
            c.restoreState()
    return NumberedCanvas


# ── building blocks ────────────────────────────────────────────────────────────────────────────────────────
def section(num, title):
    t = Table([[Paragraph(f'{num:02d}', ST['secno']), Paragraph(esc(title), ST['sectitle'])]], colWidths=[11 * mm, CW - 11 * mm])
    t.setStyle(TableStyle([('LINEBELOW', (0, 0), (-1, 0), .9, LIME), ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
                           ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                           ('BOTTOMPADDING', (0, 0), (-1, -1), 4), ('TOPPADDING', (0, 0), (-1, -1), 0)]))
    t.keepWithNext = 1
    return [Spacer(1, 7 * mm), t, Spacer(1, 3.2 * mm)]


def summary_strip(items):
    widths = [62 * mm, 44 * mm, 36 * mm, 36 * mm]            # = 178 mm; first cell is wider for long panel names
    cells = [[Paragraph(esc(k), ST['label']) for k, _ in items], [Paragraph(esc(v), ST['cell_big']) for _, v in items]]
    t = Table(cells, colWidths=widths)
    st = [('BACKGROUND', (0, 0), (-1, -1), PALE), ('LEFTPADDING', (0, 0), (-1, -1), 10), ('RIGHTPADDING', (0, 0), (-1, -1), 8),
          ('TOPPADDING', (0, 0), (-1, 0), 9), ('BOTTOMPADDING', (0, 0), (-1, 0), 1), ('TOPPADDING', (0, 1), (-1, 1), 1),
          ('BOTTOMPADDING', (0, 1), (-1, 1), 9), ('LINEBEFORE', (0, 0), (0, -1), 2.2, LIME)]
    for i in range(1, len(items)):
        st.append(('LINEBEFORE', (i, 0), (i, -1), .6, RULE))
    t.setStyle(TableStyle(st)); return t


def particulars(rows):
    w = [29 * mm, 60 * mm, 29 * mm, 60 * mm]
    data = [[Paragraph(esc(a), ST['label']), P(b), Paragraph(esc(c), ST['label']), P(d)] for a, b, c, d in rows]
    t = Table(data, colWidths=w)
    t.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LINEBELOW', (0, 0), (-1, -1), .4, RULE),
                           ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                           ('TOPPADDING', (0, 0), (-1, -1), 5.5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5.5),
                           ('TOPPADDING', (0, 0), (0, -1), 7), ('TOPPADDING', (2, 0), (2, -1), 7), ('LINEABOVE', (0, 0), (-1, 0), .4, RULE)]))
    return t


def results_table(results, refs, units, guidance):
    w = [45 * mm, 26 * mm, 24 * mm, 49 * mm, 34 * mm]                    # = 178 mm
    data = [[Paragraph('PARAMETER', ST['th']), Paragraph('VALUE', ST['thr']), Paragraph('UNIT', ST['th']),
             Paragraph('LAB REFERENCE / INTERVAL', ST['th']), Paragraph('POSITION', ST['th'])]]
    style = [('BACKGROUND', (0, 0), (-1, 0), DARK), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
             ('LEFTPADDING', (0, 0), (-1, -1), 8), ('RIGHTPADDING', (0, 0), (-1, -1), 8),
             ('TOPPADDING', (0, 0), (-1, -1), 6.5), ('BOTTOMPADDING', (0, 0), (-1, -1), 6.5),
             ('LINEBELOW', (0, 1), (-1, -1), .4, RULE), ('LINEBELOW', (0, -1), (-1, -1), .8, LIME)]
    for i, (k, v) in enumerate(results.items(), start=1):
        ref = refs.get(k)
        pos, col = position(v, ref)
        data.append([Paragraph(f'<b>{esc(k)}</b>', S('p', fontName=BOLD, fontSize=9)), Paragraph(esc(v), ST['num']),
                     P(units.get(k, 'As reported')),
                     P(ref if ref else guidance.get(k, 'Laboratory guidance not supplied'), 'small' if not ref else 'val'),
                     Paragraph(f'<font color="{col.hexval()}"><b>{esc(pos)}</b></font>' if pos != '—' else '—', S('pos', fontSize=8.2))])
        if i % 2 == 0: style.append(('BACKGROUND', (0, i), (-1, i), ZEBRA))
    t = Table(data, colWidths=w, repeatRows=1); t.setStyle(TableStyle(style)); return t


def _ph_colour(t):
    stops = [(0, '#e8603a'), (.22, '#f2a03a'), (.38, '#e9d83c'), (.5, '#7fd23a'), (.64, '#27d3a0'), (.8, '#27c0e6'), (1, '#4c7dff')]
    for (a, ca), (b, cb) in zip(stops, stops[1:]):
        if a <= t <= b:
            k = (t - a) / (b - a); A, B = colors.HexColor(ca), colors.HexColor(cb)
            return colors.Color(A.red + (B.red - A.red) * k, A.green + (B.green - A.green) * k, A.blue + (B.blue - A.blue) * k)
    return colors.HexColor(stops[-1][1])


def ph_scale(value):
    W = CW; H = 44
    d = Drawing(W, H)
    d.add(String(0, H - 9, 'pH', fontName=BOLD, fontSize=9, fillColor=INK))
    d.add(String(W, H - 9, f'{_clean(value)}  /  14', fontName=BOLD, fontSize=9, fillColor=INK, textAnchor='end'))
    n = 140; bw = W / n; y = 16
    for i in range(n):
        d.add(Rect(i * bw, y, bw + .4, 7, fillColor=_ph_colour(i / (n - 1)), strokeColor=None))
    v = max(0.0, min(14.0, _f(str(value).strip()))); x = W * v / 14
    d.add(Polygon([x - 3.4, y + 17, x + 3.4, y + 17, x, y + 8.6], fillColor=INK, strokeColor=None))
    d.add(Line(x, y - 2, x, y + 9, strokeColor=INK, strokeWidth=1.3))
    for pos, lab, anc in ((0, '0 · acidic', 'start'), (W / 2, '7 · neutral', 'middle'), (W, '14 · alkaline', 'end')):
        d.add(String(pos, 4, lab, fontName=REG, fontSize=6.6, fillColor=MUTED, textAnchor=anc))
    return d


def unit_bars(unit, items):
    """items = [(name, value_str, float)] all in the same unit; bar length relative to the largest of them."""
    W = CW; row = 17; H = 18 + row * len(items)
    d = Drawing(W, H); mx = max(v for _, _, v in items) or 1
    d.add(String(0, H - 8, f'Unit: {unit}  ·  relative bar length within this unit only', fontName=REG, fontSize=6.8, fillColor=MUTED))
    x0 = 52 * mm; bwid = W - x0 - 28 * mm
    for i, (name, txt, v) in enumerate(items):
        y = H - 26 - i * row
        d.add(String(0, y + 1, name[:30], fontName=BOLD, fontSize=8.2, fillColor=INK))
        d.add(Rect(x0, y - 1, bwid, 7, fillColor=colors.HexColor('#e8eee2'), strokeColor=None))
        d.add(Rect(x0, y - 1, max(1.5, bwid * abs(v) / mx), 7, fillColor=LIME, strokeColor=None))
        d.add(String(W, y + 1, _clean(txt), fontName=BOLD, fontSize=8.4, fillColor=INK, textAnchor='end'))
    return d


def callout(text, empty_msg):
    body = P(text, 'val') if (text or '').strip() else Paragraph(esc(empty_msg), ST['empty'])
    t = Table([[body]], colWidths=[CW])
    t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), PALE), ('LINEBEFORE', (0, 0), (0, -1), 2.4, COPPER),
                           ('LEFTPADDING', (0, 0), (-1, -1), 13), ('RIGHTPADDING', (0, 0), (-1, -1), 12),
                           ('TOPPADDING', (0, 0), (-1, -1), 9), ('BOTTOMPADDING', (0, 0), (-1, -1), 9)]))
    return t


def authorization(r):
    w = [60 * mm, 60 * mm, 58 * mm]
    head = [Paragraph('AUTHORIZED ANALYST', ST['label']), Paragraph('DESIGNATION', ST['label']), Paragraph('REPORT ISSUED AT', ST['label'])]
    vals = [P(r['approved_by'] or 'Not specified'), P(r['designation'] or 'Not specified'), P((r['approved_at'] or 'Not recorded').replace('T', '  '))]
    sig = [Paragraph('SIGNATURE &amp; LABORATORY STAMP', ST['label']), '', Paragraph('DATE', ST['label'])]
    t = Table([head, vals, sig, ['', '', '']], colWidths=w, rowHeights=[None, None, None, 17 * mm])
    t.setStyle(TableStyle([('BOX', (0, 0), (-1, -1), .7, RULE), ('INNERGRID', (0, 0), (-1, 1), .4, RULE),
                           ('BACKGROUND', (0, 0), (-1, 0), PALE), ('LINEABOVE', (0, 2), (-1, 2), .4, RULE),
                           ('BACKGROUND', (0, 2), (-1, 2), PALE), ('LINEBEFORE', (2, 2), (2, 3), .4, RULE),
                           ('SPAN', (0, 2), (1, 2)), ('SPAN', (0, 3), (1, 3)),
                           ('LEFTPADDING', (0, 0), (-1, -1), 9), ('RIGHTPADDING', (0, 0), (-1, -1), 9),
                           ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]))
    return t


LIMITS = ('This report reflects only the sample identified above and the parameters actually measured and entered by the laboratory. '
          'Reference intervals and interpretation depend on analytical method, extractant, soil type, crop, region and laboratory validation. '
          'The "position" column is a numeric comparison of the laboratory\'s own value with the laboratory\'s own interval and is not an agronomic judgement. '
          'Charts compare values only within the same unit and are not fertility scores. Fertilizer or amendment decisions should rely on locally validated '
          'recommendations and qualified agronomic advice. This portal-generated document is not a statutory or accredited laboratory certificate unless reviewed, '
          'signed and issued under the authority of an appropriately authorized laboratory.')


def _num(v):
    try:
        return _f(str(v).strip())
    except Exception:
        return None


def build(r, results, refs, units, guidance):
    """r: sqlite Row with report + appointment + customer columns. Returns BytesIO positioned at 0."""
    out = io.BytesIO()
    issued = (r['approved_at'] or datetime.now().isoformat())[:10]
    meta = {'report_no': r['report_no'], 'code': r['code'], 'issued': issued, 'generated': datetime.now().strftime('%d %b %Y %H:%M')}
    doc = BaseDocTemplate(out, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=20 * mm, bottomMargin=20 * mm,
                          title=f"LoamLab Soil Analysis {r['report_no']}", author=r['lab_name'], subject='Soil analytical report')
    first = Frame(MARGIN, 20 * mm, CW, PAGE_H - BAND_H - 20 * mm - 9 * mm, id='f1', leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    later = Frame(MARGIN, 20 * mm, CW, PAGE_H - 20 * mm - 22 * mm, id='f2', leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate('first', [first], pagesize=A4), PageTemplate('later', [later], pagesize=A4)])

    n_params = len(results)
    story = [NextPageTemplate('later'),
             summary_strip([('TEST PANEL', r['panel']), ('PARAMETERS REPORTED', str(n_params)),
                            ('TESTED ON', r['tested_on'] or 'Not recorded'), ('REPORT STATUS', 'Issued')])]

    # 01 particulars
    loc = ', '.join(x for x in [r['address'], r['district'], r['state']] if x)
    story += section(1, 'Client & sample particulars')
    story.append(particulars([
        ('CUSTOMER', r['customer_name'], 'FARM / PLOT', r['farm_name'] or 'Not supplied'),
        ('EMAIL', r['customer_email'], 'PHONE', r['customer_phone'] or '—'),
        ('SAMPLE LOCATION', loc or 'Not supplied', 'CROP', r['crop'] or 'Not supplied'),
        ('SAMPLE TYPE', r['sample_type'] or 'Soil', 'AREA (ACRES)', r['area_acres'] or 'Not supplied'),
        ('SAMPLE RECEIVED', r['sample_received'] or 'Not recorded', 'TESTED ON', r['tested_on'] or 'Not recorded'),
        ('SAMPLE CONDITION', r['sample_condition'] or 'Not recorded', 'BOOKED ON', (r['appt_created'] or '')[:10] or '—')]))

    # 02 results
    story += section(2, 'Analytical results')
    story.append(Paragraph('Values are transcribed from the measurements entered by the laboratory. Blank or unmeasured parameters are not displayed.', ST['small']))
    story += [Spacer(1, 2.5 * mm), results_table(results, refs, units, guidance)]

    # 03 profile (pH scale + same-unit bar groups)
    blocks = []
    if 'pH' in results and _num(results['pH']) is not None:
        blocks.append(ph_scale(results['pH']))
    groups = {}
    for k, v in results.items():
        n = _num(v)
        if n is not None and k != 'pH': groups.setdefault(units.get(k, 'As reported'), []).append((k, str(v), n))
    for unit, items in groups.items():
        if len(items) >= 2: blocks.append(unit_bars(unit, items))
    if blocks:
        head = section(3, 'Measured value profile') + [Paragraph('The pH marker uses the standard 0–14 scale. Bars compare parameters only when they share the same unit; the length is relative to the largest value in that group and is not a fertility score.', ST['small']), Spacer(1, 3 * mm), blocks[0], Spacer(1, 4 * mm)]
        story.append(KeepTogether(head))
        for b in blocks[1:]:
            story += [b, Spacer(1, 4 * mm)]

    n = 3 if blocks else 2
    story += section(n + 1, 'Laboratory interpretation') + [callout(r['interpretation'], 'No interpretation was entered by the laboratory.')]
    story += section(n + 2, 'Recommendations') + [callout(r['recommendations'], 'No recommendations were entered by the laboratory.')]
    story += section(n + 3, 'Analytical method notes') + [callout(r['method_notes'], 'See laboratory method record.')]

    # authorization (kept together)
    lab_line = ' · '.join(x for x in [r['lab_address'], r['lab_phone'], r['lab_email']] if x) or 'Contact details not supplied'
    auth = section(n + 4, 'Laboratory authorization') + [
        Paragraph(f'<font name="{BOLD}">{esc(r["lab_name"])}</font>', S('lab', fontSize=10.5, leading=14)),
        Paragraph(esc(lab_line), ST['small']), Spacer(1, 3 * mm), authorization(r)]
    if r['attachment']:
        auth += [Spacer(1, 2.5 * mm), Paragraph('A supporting laboratory file accompanies this report and can be downloaded from the portal.', ST['small'])]
    story.append(KeepTogether(auth))

    story += [Spacer(1, 6 * mm), KeepTogether([Paragraph(f'<font name="{BOLD}">Important scope &amp; limitations</font>', S('lh', fontSize=7.8, textColor=INK)),
                                                 Spacer(1, 1.2 * mm), Paragraph(esc(LIMITS), ST['small'])])]

    doc.build(story, canvasmaker=make_canvas_class(meta))
    out.seek(0)
    return out
