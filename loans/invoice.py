"""Builds the customer's PDF loan invoice with ReportLab."""

from io import BytesIO

from django.conf import settings
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .pricing import gbp, term_label

BRAND = colors.HexColor("#123763")
MUTED = colors.HexColor("#667A90")
RULE = colors.HexColor("#DDE8F4")
TINT = colors.HexColor("#E8F1FF")


def _styles():
    base = getSampleStyleSheet()
    return {
        "brand": ParagraphStyle("brand", parent=base["Title"], fontSize=20, textColor=BRAND, alignment=0, spaceAfter=2),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontSize=12, textColor=BRAND, spaceBefore=10, spaceAfter=4),
        "body": ParagraphStyle("body", parent=base["BodyText"], fontSize=9.5, leading=13),
        "small": ParagraphStyle("small", parent=base["BodyText"], fontSize=8, leading=10.5, textColor=MUTED),
        "right": ParagraphStyle("right", parent=base["BodyText"], fontSize=9.5, leading=13, alignment=TA_RIGHT),
    }


def _esc(text) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    fca = f" · FCA reference {settings.LENDER_FCA_NUMBER}" if settings.LENDER_FCA_NUMBER else ""
    canvas.drawString(18 * mm, 10 * mm, f"{settings.LENDER_NAME}{fca}")
    canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {doc.page}")
    canvas.restoreState()


def build_invoice_pdf(application) -> bytes:
    s = _styles()
    c = application.customer
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=18 * mm,
        title=f"Loan invoice {application.invoice_number}", author=settings.LENDER_NAME,
    )
    issued = timezone.localtime(application.submitted_at)
    story = []

    lender_lines = [f"<b>{_esc(settings.LENDER_NAME)}</b>", _esc(settings.LENDER_ADDRESS)]
    if settings.LENDER_EMAIL:
        lender_lines.append(_esc(settings.LENDER_EMAIL))
    header = Table(
        [[Paragraph(_esc(settings.LENDER_NAME), s["brand"]), Paragraph("<br/>".join(lender_lines), s["right"])]],
        colWidths=[90 * mm, 84 * mm],
    )
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, 0), 1.2, BRAND), ("BOTTOMPADDING", (0, 0), (-1, 0), 8)]))
    story += [header, Spacer(1, 8)]

    address = [c.full_name, c.address_line1, c.address_line2, c.town, c.county, c.postcode]
    bill_to = "<b>Billed to</b><br/>" + "<br/>".join(_esc(x) for x in address if x)
    meta = (
        f"<b>LOAN INVOICE</b><br/>Invoice no: {_esc(application.invoice_number)}<br/>"
        f"Application ref: {_esc(application.reference)}<br/>Date issued: {issued:%d %B %Y}<br/>"
        f"Status: {_esc(application.get_status_display())}"
    )
    t = Table([[Paragraph(bill_to, s["body"]), Paragraph(meta, s["right"])]], colWidths=[90 * mm, 84 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [t]

    story.append(Paragraph("Loan summary", s["h2"]))
    rows = [
        ["Description", "Amount"],
        [f"Amount borrowed ({application.get_purpose_display().lower()})", gbp(application.amount_pence)],
        ["Processing fee (within the price cap)", gbp(application.processing_fee_pence)],
        [f"Interest ({term_label(application.term_months)})", gbp(application.interest_pence)],
        ["Total cost of credit", gbp(application.total_charges_pence)],
        ["Total amount repayable", gbp(application.total_repayable_pence)],
    ]
    summary = Table(rows, colWidths=[124 * mm, 50 * mm])
    summary.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9.5),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 9.5),
        ("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 10.5),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 0), (-1, 0), BRAND),
        ("BACKGROUND", (0, -1), (-1, -1), TINT),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LINEBELOW", (0, 1), (-1, -2), 0.4, RULE),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story += [summary, Spacer(1, 4), Paragraph(f"Annualised APR (indicative): <b>{application.apr_display}</b>", s["body"])]

    story.append(Paragraph("Repayment schedule", s["h2"]))
    sched = [["Instalment", "Due date", "Amount"]] + [
        [str(r.number), f"{r.due_date:%d %b %Y}", gbp(r.amount_pence)] for r in application.repayments.all()
    ]
    st = Table(sched, colWidths=[40 * mm, 84 * mm, 50 * mm])
    st.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9.5),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 9.5),
        ("BACKGROUND", (0, 0), (-1, 0), TINT),
        ("ALIGN", (2, 0), (2, -1), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(st)

    story.append(Paragraph("Payment details", s["h2"]))
    story.append(Paragraph(
        f"If approved, the loan will be paid into and repayments collected from the account below by Direct Debit or "
        f"continuous payment authority.<br/>Account name: {_esc(application.account_holder_name)}<br/>"
        f"{('Bank: ' + _esc(application.bank_name) + '<br/>') if application.bank_name else ''}"
        f"Sort code: {_esc(application.sort_code)} &nbsp; Account number: ****{_esc(application.account_last4)}",
        s["body"],
    ))

    story += [Spacer(1, 12), Paragraph(
        "<b>Important:</b> this invoice confirms the loan you applied for and the most you would repay. It is not a "
        "credit agreement and no lending decision has been made yet. Charges follow the FCA high-cost short-term credit "
        "price cap: no more than 0.8% of the amount borrowed per day, and total charges never more than the amount "
        "borrowed. If you are worried about money, free and confidential help is available from MoneyHelper "
        "(moneyhelper.org.uk, 0800 138 7777).",
        s["small"],
    )]

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
