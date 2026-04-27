"""
Coaching knowledge base, derived from the official CSL Scenario training PDFs.

Used by refresh_dashboard.py to anchor coaching narratives in the actual training
language and to surface specific scripts/excerpts that match each TM's metric pattern.

Source: Southwind CSL Training - Scenarios 1, 2, 3.1, 3.2, 3.3.
"""

# ---------- scenarios at a glance ----------

SCENARIOS = {
    "1": {
        "title": "Scenario 1 - Standard Sales Process",
        "when": "The clean run. Customer is ready to buy if we execute the close cleanly.",
        "steps": [
            ("1A", "Call Ahead", "30 minutes before the window. Customer voice on. Plant the seed for more items."),
            ("1B", "5 Star Service Agenda", "Walk-through, thorough evaluation, free no-obligation estimate, lead-rep dedication."),
            ("2",  "Relevant Rapport", "Personal rapport via FORD (Family, Occupation, Recreation, Dreams) plus relevant rapport about the project."),
            ("3",  "Establish Value", "Three Power Questions. Price sheet, life cycle of items, paint the picture of completion."),
            ("4",  "Estimate & Price", "Confidence is everything. Memorize price list. Range bid (Plus 1, Plus 2). Never mention min charge. Only give full truck price."),
            ("5",  "Assumptive Ask", "Pair immediately with the bid. Lead the job. Use value keys (Time, Space, Effort). No pause."),
        ],
    },
    "2": {
        "title": "Scenario 2 - Re-Establish Value (Pushback)",
        "when": "Customer hesitates after first bid. Hold the price, reintroduce value differently.",
        "steps": [
            ("1A", "Call Ahead", "Same as Scenario 1."),
            ("1B", "5 Star Service Agenda", "Same as Scenario 1."),
            ("2",  "REEAP", "Recognize, Explore, Empathize, Acknowledge, Pivot. Don't argue, redirect."),
            ("3",  "Re-Establish Value (different way)", "Same value, told a new way. Lead with what they already valued."),
            ("4",  "Re-Establish Value (new info)", "Surface a benefit you haven't already shared (donations, recycling, full service)."),
            ("5",  "Re-Establish Value (alternatives)", "What's the cost of doing it themselves? Time, hauling, dump fees."),
        ],
    },
    "3.1": {
        "title": "Scenario 3.1 - Roll-Over Pricing",
        "when": "Customer wants the work but can't pay the full bid today. Get something on the truck now.",
        "steps": [
            ("1A", "Call Ahead", "Same as Scenario 1."),
            ("1B", "5 Star Service Agenda", "Same as Scenario 1."),
            ("2",  "REEAP", "Same as Scenario 2."),
            ("3",  "Re-Establish Value", "Tighten the bid to what's possible today."),
            ("4",  "Priority Items / Roll-Over Pricing", "Customer pays what they can now for a partial load. Within 30 days they finish at the volume mark they stopped at."),
            ("5",  "Positive Ending / Exceptional Receipt", "Lock in the next visit. Customer leaves the conversation feeling progress, not pressure."),
        ],
    },
    "3.2": {
        "title": "Scenario 3.2 - Coupon Delivery",
        "when": "After re-establishing value, a small concession unlocks the close.",
        "steps": [
            ("1A", "Call Ahead", "Same as Scenario 1."),
            ("1B", "5 Star Service Agenda", "Same as Scenario 1."),
            ("2",  "REEAP", "Same as Scenario 2."),
            ("3",  "Re-Establish Value", "Same as Scenario 2."),
            ("4",  "Coupon Delivery ($25 / $50)", "Hand the coupon as a kind gesture with a reason. $25 for 1/8 to 3/8, $50 for 1/2 to full. Doesn't apply to min charge or SIP."),
            ("5",  "Positive Ending / Exceptional Receipt", "Same as 3.1."),
        ],
    },
    "3.3": {
        "title": "Scenario 3.3 - Full Negotiation Protocol",
        "when": "The save scenario. Customer is on the cancel edge or has a firm budget cap.",
        "steps": [
            ("1A", "Call Ahead", "Same as Scenario 1."),
            ("1B", "5 Star Service Agenda", "Same as Scenario 1."),
            ("2",  "REEAP", "Same as Scenario 2."),
            ("3",  "Re-Establish Value", "Tight, energetic, value-key driven."),
            ("4",  "Execute Negotiation Protocol", "1) Re-Establish Value. 2) Priority Items (full price first). 3) Offer $25/$50 Coupon. 4) Identify Budget. 5) Call Operations with TM on site."),
            ("5",  "Positive Ending / Exceptional Receipt", "Same as 3.1."),
        ],
    },
}


# ---------- pull-quotes from the actual training pages ----------

QUOTES = {
    "ajs_close": {
        "scenario": "1",
        "step": "4",
        "name": "Estimate & Price - Rules of the Range",
        "text": "Confidence is EVERYTHING. Memorize the price list. Bid the job at what it is and cut the maybes and probablys out. The lowest part of your range is what you think it is. Never mention Min Charge. Only give the full truck price.",
    },
    "assumptive_ask": {
        "scenario": "1",
        "step": "5",
        "name": "Assumptive Ask",
        "text": "The Assumptive Ask should be immediately paired with the estimate and price. No pause. Lead the job - tell them what you are about to do, give an ETA, paint the picture of the completed project.",
    },
    "five_star_agenda": {
        "scenario": "1",
        "step": "1B",
        "name": "5 Star Service Agenda",
        "text": "Thank you for the opportunity. Walk-through. Thorough evaluation. Free no-obligation estimate. Empty truck out front. Lead representative dedication.",
    },
    "ford_rapport": {
        "scenario": "1",
        "step": "2",
        "name": "Relevant Rapport - FORD",
        "text": "Personal rapport with FORD: Family, Occupation, Recreation, Dreams. Relevant rapport about the project: how long has this been here, what are you planning for the space, what were you hoping to accomplish today?",
    },
    "three_power_questions": {
        "scenario": "1",
        "step": "3",
        "name": "Three Power Questions (Establish Value)",
        "text": "1) What items will we be removing today? 2) Why are you getting rid of the items (their value key - time, space, effort)? 3) What is the project / end goal you are aiming to achieve?",
    },
    "reeap": {
        "scenario": "2",
        "step": "2",
        "name": "REEAP",
        "text": "Recognize, Explore, Empathize, Acknowledge, Pivot. When the customer pushes back, don't argue - redirect to value told a different way.",
    },
    "priority_items": {
        "scenario": "3.1",
        "step": "4",
        "name": "Priority Items + Roll-Over Pricing",
        "text": "When budget is the constraint, get something on the truck now. Customer pays what they can today for a partial load. Within 30 days they finish at the same volume mark.",
    },
    "coupon_delivery": {
        "scenario": "3.2",
        "step": "4",
        "name": "Coupon Delivery",
        "text": "How you deliver the coupon is EVERYTHING - make it special. Always have a REASON. $25 for 1/8 to 3/8. $50 for 1/2 to full load. Doesn't apply to Min Charge or SIP.",
    },
    "negotiation_protocol": {
        "scenario": "3.3",
        "step": "4",
        "name": "Negotiation Protocol",
        "text": "1) Re-Establish Value. 2) Priority Items first (still full price). 3) Offer $25/$50 Coupon. 4) Identify Budget. 5) Call Operations with TM on site - leave someone with the customer.",
    },
    "costco_effect": {
        "scenario": "1",
        "step": "5",
        "name": "Costco Effect",
        "text": "While we're working, ask the customer to look around for other items or tasks. They forget what's still on the list until you remind them.",
    },
    "value_keys": {
        "scenario": "all",
        "step": "all",
        "name": "Value Keys",
        "text": "Time, Space, Effort. Replace pain with pleasure. Every value statement and assumptive ask should anchor on at least one of these.",
    },
}


# ---------- map metric pattern to coaching anchor ----------

# Order here matters when more than one applies — check primary issue first.
METRIC_ANCHORS = {
    # AJS-led: close mechanics
    "ajs":         ["ajs_close", "assumptive_ask", "three_power_questions"],
    # Complaint-led: service experience
    "complaint":   ["five_star_agenda", "ford_rapport"],
    # NPS-led: how the customer feels about the experience
    "nps":         ["ford_rapport", "five_star_agenda"],
    # Reviews-led: closeout ask
    "gr":          ["five_star_agenda", "assumptive_ask"],
    # Cancel save: full negotiation
    "cancel_save": ["negotiation_protocol", "priority_items", "coupon_delivery", "reeap"],
    # Truck+: priority items + Costco effect
    "truck_plus":  ["priority_items", "costco_effect", "ajs_close"],
}


def quote_for(primary_issue: str, secondary: bool = False) -> dict:
    """Return the most relevant training quote for a given metric pattern."""
    keys = METRIC_ANCHORS.get(primary_issue, [])
    if not keys:
        return QUOTES["ajs_close"]
    idx = 1 if (secondary and len(keys) > 1) else 0
    return QUOTES[keys[idx]]


def scenario_label(quote: dict) -> str:
    """Format a scenario reference like 'Scenario 1, Step 4 - Estimate & Price'."""
    s = quote.get("scenario", "")
    step = quote.get("step", "")
    name = quote.get("name", "")
    if s == "all":
        return name
    return f"Scenario {s}, Step {step} - {name}"
