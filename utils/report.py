from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor

def _wrap_text(c, text, x, y, max_width, line_height=12, font="Helvetica", size=9):
    c.setFont(font, size)
    words = text.split()
    line = ""
    for w in words:
        test = (line + " " + w).strip()
        if c.stringWidth(test, font, size) <= max_width:
            line = test
        else:
            c.drawString(x, y, line)
            y -= line_height
            line = w
    if line:
        c.drawString(x, y, line)
        y -= line_height
    return y

def _top_issues(df, n=6):
    issues = df[df["Status"].isin(["Issue","Missing"])].copy()
    # sort by Criticality weight
    weight = {"Critical":3, "Major":2, "Minor":1}
    issues["w"] = issues["Criticality"].map(lambda k: weight.get(k,1))
    issues = issues.sort_values(["w"], ascending=False).head(n)
    out = []
    for _, r in issues.iterrows():
        out.append(f"{r['Parameter']}: {r['Customer Spec']} vs {r['Engineering Spec']} → {r['Status']} (Risk: {r['Risk']})")
    return out

def build_executive_pdf(result_df, project="Project", client="Client", reviewer="Reviewer"):
    # KPIs
    total = len(result_df)
    crit = (result_df["Criticality"]=="Critical").sum()
    open_issues = (result_df["Status"].isin(["Issue","Missing"])).sum()
    ok_count = (result_df["Status"]=="OK").sum()
    score = round(100.0 * ok_count / max(total,1), 1)

    # Category summary
    cat = result_df.groupby("Category")["Status"].apply(lambda s: (s=="OK").sum()/len(s)*100.0).round(1)

    # Build one-page PDF
    from io import BytesIO
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4

    # Header
    c.setFillColor(HexColor("#0F766E"))
    c.rect(0, H-40, W, 40, fill=1, stroke=0)
    c.setFillColor(HexColor("#ffffff"))
    c.setFont("Helvetica-Bold", 16)
    c.drawString(20*mm, H-28, "Executive Summary — Pump Spec Compliance")

    # Meta
    c.setFillColor(HexColor("#000000"))
    c.setFont("Helvetica", 10)
    c.drawString(20*mm, H-55, f"Project: {project}")
    c.drawString(20*mm, H-70, f"Client: {client}")
    c.drawString(120*mm, H-55, f"Prepared by: {reviewer}")

    # KPI Cards
    def card(x, y, title, value):
        c.setFillColor(HexColor("#F1F5F9")); c.rect(x, y, 55*mm, 24*mm, fill=1, stroke=0)
        c.setFillColor(HexColor("#334155")); c.setFont("Helvetica-Bold", 12); c.drawString(x+6*mm, y+14*mm, title)
        c.setFillColor(HexColor("#000000")); c.setFont("Helvetica-Bold", 16); c.drawString(x+6*mm, y+6*mm, str(value))

    y0 = H - 120
    card(20*mm, y0, "Compliance %", f"{score}%")
    card(80*mm, y0, "Critical Checks", crit)
    card(140*mm, y0, "Open Issues", open_issues)

    # Category Pass Rates
    c.setFont("Helvetica-Bold", 12)
    c.drawString(20*mm, y0-15*mm, "Category Pass Rates")
    y = y0-22*mm
    c.setFont("Helvetica", 10)
    for k, v in cat.items():
        c.drawString(20*mm, y, f"• {k}: {v}%")
        y -= 6*mm

    # Top Issues
    c.setFont("Helvetica-Bold", 12)
    c.drawString(100*mm, y0-15*mm, "Top Issues / Risks")
    y2 = y0-22*mm
    items = _top_issues(result_df, n=6)
    for t in items:
        y2 = _wrap_text(c, "• " + t, 100*mm, y2, max_width=90*mm, line_height=11, font="Helvetica", size=10)

    # Footer note
    c.setFont("Helvetica-Oblique", 9)
    c.setFillColor(HexColor("#475569"))
    c.drawString(20*mm, 15*mm, "Note: Negotiation suggestions are heuristic and require engineering judgment.")

    c.showPage()
    c.save()
    return buf.getvalue(), {"score": score, "critical": crit, "open_issues": open_issues}
