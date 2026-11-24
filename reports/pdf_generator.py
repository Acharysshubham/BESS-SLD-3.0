import io
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
from .excel_generator import sizing_tables
from .equipment_schedule import schedule

COL = {"PASS": "#d8f0e2", "WARN": "#fdf0c8", "FAIL": "#f8d4d0", "UNVERIFIED": "#e4e4e4"}


def _tab(df, widths=None, status=False):
    rows = [list(df.columns)] + [[("%.2f" % x if isinstance(x, float) else str(x)) for x in r] for r in df.values.tolist()]
    t = Table(rows, colWidths=widths, repeatRows=1)
    st = [("FONTSIZE", (0, 0), (-1, -1), 7.5), ("GRID", (0, 0), (-1, -1), .3, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dfe7e3")), ("VALIGN", (0, 0), (-1, -1), "TOP")]
    if status: st += [("BACKGROUND", (0, i + 1), (0, i + 1), colors.HexColor(COL[r[0]])) for i, r in enumerate(df.values.tolist())]
    t.setStyle(TableStyle(st)); return t


def report_pdf(P, R, nodes, val):
    ss = getSampleStyleSheet(); buf = io.BytesIO(); doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=30, rightMargin=30, topMargin=30, bottomMargin=30)
    bt, pt, it = sizing_tables(P, R); h = lambda s: Paragraph(s, ss["Heading2"]); p = lambda s: Paragraph(s, ss["BodyText"])
    n = val.Status.value_counts().to_dict()
    S = [Paragraph("BESS & Electrical Engineering Calculation Report", ss["Title"]), p(f"<b>Project:</b> {P['name']} &nbsp; <b>Client:</b> {P['client']} &nbsp; <b>Location:</b> {P['location']}"),
         p(f"<b>Type:</b> {P['ptype']}, {P['coupling']} &nbsp; <b>MV:</b> {P['mv_kv']:g} kV &nbsp; <b>Grid:</b> {P['grid_kv']:g} kV"),
         p("Equipment ratings are user inputs or illustrative defaults, not manufacturer data. This report does not certify compliance; see the validation section for unverified items."),
         h("1. BESS"), _tab(bt), h("2. PCS"), _tab(pt), Spacer(1, 6), _tab(R["pcs_table"]), h("3. Inverter duty transformers")]
    S.append(_tab(it.round(2)) if len(it) else p("No feasible IDT arrangement."))
    S += [h("4. Equipment schedule"), _tab(schedule(nodes), [90, 90, 120, 30, 220]),
          h("5. Validation"), p(" &nbsp; ".join(f"{k}: {v}" for k, v in n.items())), _tab(val[["Status", "Category", "Check", "Detail"]], [60, 80, 120, 270], True)]
    doc.build(S); return buf.getvalue()
