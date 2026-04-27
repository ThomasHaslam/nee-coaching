"""
Build the 'How to Use' PDF guide for the NEE Coaching Dashboard.
Run from repo root:  python3 docs/build_guide_pdf.py
Output:              docs/HOW-TO-USE.pdf
"""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer,
    Table, TableStyle, PageBreak, KeepTogether,
)

# Brand-aligned palette (light background, ink-friendly)
NAVY = colors.HexColor("#0b1020")
NAVY_SOFT = colors.HexColor("#1d2640")
TEXT = colors.HexColor("#1a1f2e")
TEXT_MUTED = colors.HexColor("#525d75")
GOLD = colors.HexColor("#c89028")           # darker for print contrast
GOLD_BG = colors.HexColor("#fff6e3")
VIOLET = colors.HexColor("#7b5cd6")
VIOLET_BG = colors.HexColor("#f3eeff")
INFO = colors.HexColor("#2d6db6")
INFO_BG = colors.HexColor("#e8f1fc")
DONE = colors.HexColor("#2a8765")
DONE_BG = colors.HexColor("#e6f6ee")
URGENT = colors.HexColor("#c33b3b")
RULE = colors.HexColor("#cdd4e0")
PAGE_BG = colors.HexColor("#fafbfd")

OUT = Path(__file__).parent / "HOW-TO-USE.pdf"


def header_footer(canvas, doc):
    canvas.saveState()
    # Top stripe
    canvas.setFillColor(NAVY)
    canvas.rect(0, LETTER[1] - 0.45 * inch, LETTER[0], 0.45 * inch, stroke=0, fill=1)
    canvas.setFillColor(GOLD)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawString(0.6 * inch, LETTER[1] - 0.30 * inch, "NEW ENGLAND ELITE  ·  A SOUTHWIND REGION")
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(LETTER[0] - 0.6 * inch, LETTER[1] - 0.30 * inch, "Coaching Dashboard  ·  How to Use")

    # Footer
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.5)
    canvas.line(0.6 * inch, 0.55 * inch, LETTER[0] - 0.6 * inch, 0.55 * inch)
    canvas.setFillColor(TEXT_MUTED)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(0.6 * inch, 0.38 * inch, "nee-coaching.pages.dev")
    canvas.drawRightString(LETTER[0] - 0.6 * inch, 0.38 * inch, f"Page {doc.page}")
    canvas.restoreState()


styles = getSampleStyleSheet()
H1 = ParagraphStyle("h1", parent=styles["Heading1"], fontName="Helvetica-Bold",
                    fontSize=22, leading=26, textColor=NAVY, spaceBefore=4, spaceAfter=10)
H2 = ParagraphStyle("h2", parent=styles["Heading2"], fontName="Helvetica-Bold",
                    fontSize=14, leading=18, textColor=GOLD, spaceBefore=14, spaceAfter=6,
                    letterSpacing=0.4)
H3 = ParagraphStyle("h3", parent=styles["Heading3"], fontName="Helvetica-Bold",
                    fontSize=11, leading=14, textColor=NAVY, spaceBefore=8, spaceAfter=2)
EYEBROW = ParagraphStyle("eyebrow", parent=styles["Normal"], fontName="Helvetica-Bold",
                         fontSize=8, leading=11, textColor=GOLD, spaceAfter=2,
                         alignment=0)
BODY = ParagraphStyle("body", parent=styles["BodyText"], fontName="Helvetica",
                      fontSize=10, leading=14.5, textColor=TEXT, spaceAfter=6)
BODY_TIGHT = ParagraphStyle("body_tight", parent=BODY, spaceAfter=2)
BULLET = ParagraphStyle("bullet", parent=BODY, leftIndent=14,
                        bulletIndent=2, spaceAfter=3)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=9, leading=12,
                       textColor=TEXT_MUTED)
CODE = ParagraphStyle("code", parent=BODY, fontName="Courier", fontSize=9.5,
                      leading=12, textColor=NAVY_SOFT, leftIndent=10, spaceAfter=4)


def callout(title, body, accent=GOLD, bg=GOLD_BG):
    """Render a colored callout box."""
    title_style = ParagraphStyle("c_title", parent=H3, textColor=accent,
                                 fontSize=10, spaceBefore=0, spaceAfter=2)
    body_style = ParagraphStyle("c_body", parent=BODY, fontSize=10, leading=14,
                                spaceAfter=0, textColor=TEXT)
    inner = [Paragraph(title, title_style), Paragraph(body, body_style)]
    t = Table([[inner]], colWidths=[6.6 * inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("LINEBEFORE", (0, 0), (0, -1), 3, accent),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    return t


def two_col(left, right, ratios=(0.5, 0.5)):
    """Two-column row with two flowable lists side by side."""
    t = Table([[left, right]], colWidths=[ratios[0] * 6.6 * inch, ratios[1] * 6.6 * inch])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t


def hr():
    """Horizontal rule between sections."""
    t = Table([[""]], colWidths=[6.6 * inch], rowHeights=[1])
    t.setStyle(TableStyle([
        ("LINEABOVE", (0, 0), (-1, -1), 0.6, RULE),
    ]))
    return t


def metric_table():
    data = [
        ["Metric", "Weight", "Standard"],
        ["Adjusted Resi AJS", "50%", "$725 (BNO/BSO) · $619 (CP/CT)"],
        ["TTM Complaints", "27%", "≤ 1.50% (≤ 1.30% at CT)"],
        ["NPS", "14%", "≥ 90%"],
        ["Google Reviews capture", "14%", "≥ 25%"],
    ]
    t = Table(data, colWidths=[2.0 * inch, 1.0 * inch, 3.6 * inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PAGE_BG]),
        ("TEXTCOLOR", (0, 1), (-1, -1), TEXT),
        ("GRID", (0, 0), (-1, -1), 0.4, RULE),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return t


def tier_table():
    data = [
        ["Tier", "Score", "Rick's Posture"],
        ["ELITE", "95+", "Recognition first. Ask what's working."],
        ["SOLID", "80–94", "Light maintenance. One small course-correction."],
        ["WATCH", "65–79", "Curious. Diagnose with them. One habit shift."],
        ["URGENT", "< 65", "Direct. Plan with timeline. Pair shadow + script."],
    ]
    t = Table(data, colWidths=[1.0 * inch, 0.9 * inch, 4.7 * inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 1), (0, 1), DONE),
        ("TEXTCOLOR", (0, 2), (0, 2), INFO),
        ("TEXTCOLOR", (0, 3), (0, 3), GOLD),
        ("TEXTCOLOR", (0, 4), (0, 4), URGENT),
        ("TEXTCOLOR", (1, 1), (-1, -1), TEXT),
        ("TEXTCOLOR", (2, 1), (-1, -1), TEXT),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PAGE_BG]),
        ("GRID", (0, 0), (-1, -1), 0.4, RULE),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def shortcut_table():
    data = [
        ["Action", "Shortcut"],
        ["Open command palette (search any teammate)", "⌘K  /  Ctrl+K"],
        ["Print today's coaching list", "⌘P  /  Ctrl+P"],
        ["Close any modal", "Esc"],
        ["Submit a chat message", "Enter"],
        ["New line in chat", "Shift + Enter"],
    ]
    t = Table(data, colWidths=[4.4 * inch, 2.2 * inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTNAME", (1, 1), (1, -1), "Courier-Bold"),
        ("ALIGN", (1, 0), (1, -1), "CENTER"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PAGE_BG]),
        ("TEXTCOLOR", (0, 1), (-1, -1), TEXT),
        ("GRID", (0, 0), (-1, -1), 0.4, RULE),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


# ---------- assemble ----------

doc = BaseDocTemplate(
    str(OUT), pagesize=LETTER,
    leftMargin=0.6 * inch, rightMargin=0.6 * inch,
    topMargin=0.75 * inch, bottomMargin=0.75 * inch,
    title="NEE Coaching Dashboard - How to Use",
    author="New England Elite",
)
frame = Frame(doc.leftMargin, doc.bottomMargin,
              doc.width, doc.height, id="normal",
              leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
doc.addPageTemplates([PageTemplate(id="all", frames=frame, onPage=header_footer)])

story = []

# ---------- Cover ----------
story.append(Spacer(1, 1.4 * inch))
story.append(Paragraph("A SOUTHWIND REGION", EYEBROW))
story.append(Paragraph("New England Elite", H1))
story.append(Paragraph("Coaching Dashboard", ParagraphStyle(
    "cover_sub", parent=H1, fontSize=18, textColor=GOLD, spaceAfter=20)))
story.append(Spacer(1, 0.2 * inch))
story.append(Paragraph("How to Use This Dashboard", ParagraphStyle(
    "cover_title", parent=H1, fontSize=28, textColor=NAVY, spaceAfter=14)))
story.append(Paragraph(
    "Daily coaching dashboard for franchise leaders. Pulls live data from each "
    "franchise's <i>Junk Route Stats / Digital Whiteboard</i> tab every weekday "
    "at 5am ET. Surfaces who needs coaching, who deserves recognition, and gives "
    "you Coach Rick - an AI coach grounded in your CSL Scenario playbook and 30+ "
    "leadership models you can talk to anytime.",
    BODY,
))
story.append(Spacer(1, 0.6 * inch))
story.append(callout(
    "The 30-second pitch",
    "Open the dashboard each morning. Read the motivational message. Skim the worst-5 picks "
    "in each franchise. Tap into a teammate's card to see Coach Rick's diagnosis and 10 "
    "pre-written coaching answers. For anything else, open the chat and ask Coach Rick.",
    accent=GOLD, bg=GOLD_BG,
))
story.append(PageBreak())

# ---------- Section 1: The Two Views ----------
story.append(Paragraph("1.  The Two Views", H2))
story.append(Paragraph(
    "The dashboard has two tabs at the top. Click between them anytime.",
    BODY,
))
story.append(Spacer(1, 0.1 * inch))
story.append(two_col(
    [
        Paragraph("📊  Dashboard", H3),
        Paragraph(
            "Today's coaching list. Hero stats, motivational message, top performers, "
            "morning huddle brief, and the worst-5 teammates per franchise with full "
            "AI-generated coaching write-ups. This is your morning briefing.",
            BODY,
        ),
    ],
    [
        Paragraph("💬  Coach Rick · Full Chat", H3),
        Paragraph(
            "Full-screen chat with Coach Rick. Sidebar shows every teammate in the region "
            "(searchable, filterable by franchise). Pick anyone OR start in General Coaching "
            "mode to ask about leadership, training, culture, and development.",
            BODY,
        ),
    ],
))

story.append(Spacer(1, 0.18 * inch))
story.append(hr())

# ---------- Section 2: Dashboard layout ----------
story.append(Paragraph("2.  Dashboard Walkthrough (top to bottom)", H2))

story.append(Paragraph("Hero stats", H3))
story.append(Paragraph(
    "Time-aware greeting (morning / afternoon / evening), a dynamic headline that adapts to "
    "today's reality (e.g., \"3 urgent teammates need attention today\"), and a stat row showing "
    "left-to-coach, urgent count, high count, lowest score, and average score.",
    BODY,
))

story.append(Paragraph("📣  Coach Rick's Motivational Message of the Day", H3))
story.append(Paragraph(
    "Coach Rick writes a fresh 2-3 sentence motivational message every morning, in plain blue-collar "
    "voice. References today's reality (urgent count, top performers, day of the week). Read it before "
    "your huddle.",
    BODY,
))

story.append(Paragraph("🏆  Top 5 Regional Performers · This Month", H3))
story.append(Paragraph(
    "The 5 highest-scoring teammates across the entire region for the month-to-date. Composite score "
    "is the primary sort. AJS is the tiebreaker. Use these in your huddle for recognition; ask one of "
    "them to walk the team through what's working.",
    BODY,
))

story.append(Paragraph("📣  Coach Rick's Morning Huddle Brief", H3))
story.append(Paragraph(
    "A 90-second huddle script Rick writes from the entire team picture. Three sections: "
    "<b>What's working</b> (recognition), <b>Where the focus needs to be</b> (team-wide pattern), "
    "<b>Today's challenge</b> (one concrete behavior tied to a Scenario step). Two buttons: "
    "🖨 Print and 📋 Copy to clipboard - paste into Slack or read aloud at the meeting.",
    BODY,
))

story.append(Paragraph("Franchise sections (BNO / BSO / CP / CT)", H3))
story.append(Paragraph(
    "Click any franchise tab to drill in (or click \"All\" for the collapsed view). Each franchise "
    "shows its top performers strip first, then 5 coaching cards.",
    BODY,
))

story.append(Spacer(1, 0.08 * inch))
story.append(callout(
    "📋  Each coaching card contains",
    "Severity tag · 5 metric badges (Score, Adj AJS, Complaints, NPS, Reviews) · "
    "<b>The Why</b> (data interpretation) · <b>The Play</b> (specific action this week) · "
    "<b>Coaching Anchor from Training</b> (verbatim CSL Scenario quote that maps to the issue) · "
    "Notes box you can type into · <b>💬 Ask Coach Rick</b> button · <b>Mark Coached</b> button.",
    accent=VIOLET, bg=VIOLET_BG,
))
story.append(PageBreak())

# ---------- Section 3: How scoring works ----------
story.append(Paragraph("3.  How the Score Works", H2))
story.append(Paragraph(
    "Every teammate gets a single composite score from <b>0 to 100</b>, computed from four metrics. "
    "Hitting standard on a metric earns a clean 100 for that slot. Missing standard reduces it "
    "proportionally. No bonus for going above standard, no double-counting.",
    BODY,
))
story.append(Spacer(1, 0.1 * inch))
story.append(metric_table())
story.append(Spacer(1, 0.1 * inch))
story.append(Paragraph(
    "Raw weights in spec are 50 / 30 / 15 / 15 (sums to 110). They're normalized so the final score "
    "always lands on 0-100.",
    SMALL,
))

story.append(Paragraph("How a sub-score is calculated", H3))
story.append(Paragraph(
    "<b>Higher-is-better</b> (AJS, NPS, Reviews):  min(100, value ÷ standard × 100)<br/>"
    "<b>Lower-is-better</b> (Complaints):  min(100, standard ÷ value × 100)",
    CODE,
))
story.append(Paragraph(
    "<i>Example.</i> A BNO teammate with AJS $580 (standard $725):  580 ÷ 725 × 100 = <b>80</b>. "
    "That sub-score then weighs 50% in the composite.",
    BODY,
))

story.append(Paragraph("Tiers and posture", H3))
story.append(tier_table())
story.append(Spacer(1, 0.06 * inch))
story.append(Paragraph(
    "Eligibility: only teammates with at least <b>10 residential jobs</b> in the period are scored. "
    "Smaller samples are too noisy to coach against.",
    SMALL,
))
story.append(PageBreak())

# ---------- Section 4: Coach Rick chat ----------
story.append(Paragraph("4.  Talking to Coach Rick", H2))
story.append(Paragraph(
    "Coach Rick is the AI coach embedded in this dashboard. He has the full CSL Scenario playbook "
    "(Scenarios 1, 2, 3.1, 3.2, 3.3) and a leadership library of 30+ named frameworks committed to "
    "memory - GROW, Radical Candor, the 5 Dysfunctions of a Team, Crucial Conversations, Pink's "
    "Drive, Andy Grove's 1:1, Bill Campbell's coaching posture, Brené Brown's daring leadership, "
    "Wooden's Pyramid of Success, and more.",
    BODY,
))
story.append(Paragraph(
    "He's tuned to talk like a real coach who came up through the trucks - plain blue-collar "
    "language, short sentences, no consultant jargon, no author name-drops. He'll ask you a "
    "clarifying question first when context is missing, then give you a real answer.",
    BODY,
))

story.append(Paragraph("Two ways to open chat", H3))
story.append(two_col(
    [
        Paragraph("From a teammate card", H3),
        Paragraph(
            "Click <b>💬 Ask Coach Rick</b> on any worst-5 card on the dashboard. Rick gets that "
            "teammate's full data + a 10-question deep-dive auto-generated each morning across three "
            "categories: <b>Today's Conversation</b>, <b>Diagnose the Pattern</b>, <b>Path Forward</b>.",
            BODY,
        ),
    ],
    [
        Paragraph("From the Coach Rick tab", H3),
        Paragraph(
            "Click <b>💬 Coach Rick · Full Chat</b> in the top nav. Sidebar lists every teammate in "
            "the region (search by name, filter by franchise). Pick anyone, or stay on <b>🌐 General "
            "Coaching</b> at the top to ask about leadership, training, culture, or development.",
            BODY,
        ),
    ],
))

story.append(Spacer(1, 0.08 * inch))
story.append(callout(
    "💡  Tips for getting good answers",
    "• Be specific. \"Why is Deven's NPS at 29%?\" works better than \"Help Deven.\"<br/>"
    "• Ask follow-ups. Rick remembers the conversation within a session.<br/>"
    "• Ask for what you'll actually use: \"Give me a 60-second 1:1 opener\" or \"Write a verbatim "
    "line I can say to start the conversation.\"<br/>"
    "• Push back when his read seems off - he'll adjust. He treats your knowledge of the team as "
    "more authoritative than his own.",
    accent=VIOLET, bg=VIOLET_BG,
))

story.append(Paragraph("Memory and refresh", H3))
story.append(Paragraph(
    "Conversations are saved to your browser as you go and auto-cleared on every page refresh. "
    "Each refresh starts you with a fresh slate. Multi-turn within a session is fully remembered "
    "(Rick sees the last 8 exchanges on each new question).",
    BODY,
))
story.append(PageBreak())

# ---------- Section 5: Daily workflow + features ----------
story.append(Paragraph("5.  What Runs Every Morning", H2))
story.append(Paragraph(
    "Every weekday at <b>5am ET</b>, an automated workflow:",
    BODY,
))
story.append(Paragraph("• Pulls fresh data from all 4 franchises' Digital Whiteboard tabs (entire sheet, every teammate)", BULLET, bulletText="•"))
story.append(Paragraph("• Computes composite scores; identifies worst 5 per franchise + top 5 per franchise", BULLET, bulletText="•"))
story.append(Paragraph("• Asks Coach Rick to write Why / Play / Anchor + 10 deep-dive Q&As for each of the 20 worst-5 picks", BULLET, bulletText="•"))
story.append(Paragraph("• Picks the regional Top 5 Performers for the month (AJS as tiebreaker)", BULLET, bulletText="•"))
story.append(Paragraph("• Has Rick write today's motivational message + the morning huddle brief", BULLET, bulletText="•"))
story.append(Paragraph("• Writes the full roster.json (all 198 teammates) for the chat sidebar", BULLET, bulletText="•"))
story.append(Paragraph("• Auto-deploys the new dashboard to Cloudflare Pages", BULLET, bulletText="•"))

story.append(Paragraph("Manual refresh", H3))
story.append(Paragraph(
    "If you ever want a fresh pull on demand, you can trigger the workflow manually:",
    BODY,
))
story.append(Paragraph("github.com/ThomasHaslam/nee-coaching/actions  →  \"Refresh coaching dashboard\"  →  \"Run workflow\"", CODE))

story.append(Paragraph("How to know when it last ran", H3))
story.append(Paragraph(
    "View source on the page (or just trust the Top 5 / huddle / motivational message - they're "
    "always today's). The hidden HTML comment near the top reads "
    "<font face=\"Courier\">&lt;!-- LAST_UPDATED: 2026-04-27T05:30:00Z --&gt;</font>.",
    BODY,
))

story.append(Spacer(1, 0.16 * inch))
story.append(hr())

story.append(Paragraph("6.  Quick Reference", H2))
story.append(Paragraph("Keyboard shortcuts", H3))
story.append(shortcut_table())

story.append(Paragraph("Mobile tips", H3))
story.append(Paragraph(
    "• On the chat tab, tap <b>📋 Roster</b> in the chat header to slide the sidebar in. Tap a "
    "teammate, drawer auto-closes.<br/>"
    "• The chat input handles the keyboard correctly - it stays visible as you type. If it ever "
    "glitches, scroll up once and the layout will reset.<br/>"
    "• Add the page to your home screen for a one-tap launcher.",
    BODY,
))

story.append(Paragraph("Useful URLs", H3))
story.append(Paragraph("Dashboard:        nee-coaching.pages.dev", CODE))
story.append(Paragraph("Direct to chat:   nee-coaching.pages.dev/#/chat", CODE))
story.append(Paragraph("Workflow runs:    github.com/ThomasHaslam/nee-coaching/actions", CODE))

story.append(Spacer(1, 0.20 * inch))
story.append(callout(
    "Built different.",
    "If something's confusing, broken, or could be better - say so. The dashboard is a living "
    "tool. Every piece of feedback makes the next version sharper.",
    accent=NAVY, bg=PAGE_BG,
))


doc.build(story)
print(f"wrote {OUT}  ({OUT.stat().st_size:,} bytes)")
