"""
Coaching knowledge base, derived from the official CSL Scenario training PDFs.

Quotes here are actual training script text or rule excerpts pulled directly from
the 5 PDFs (Scenarios 1, 2, 3.1, 3.2, 3.3). They are NOT paraphrased summaries.

Used by refresh_dashboard.py to anchor coaching narratives in the real training
language, and (when an Anthropic API key is configured) as context for the AI
coaching generator.
"""

# ---------- scenarios at a glance ----------

SCENARIOS = {
    "1": "Standard Sales Process - clean run, customer ready to buy",
    "2": "Re-Establish Value - customer pushed back on the bid, hold price by re-presenting value",
    "3.1": "Roll-Over Pricing - budget-constrained customer, get something on the truck now",
    "3.2": "Coupon Delivery - small concession ($25/$50) unlocks the close after re-establishing value",
    "3.3": "Full Negotiation Protocol - cancel-edge customer, full save sequence",
}


# ---------- pull-quotes (actual training script text) ----------
#
# Each quote includes:
#   ref:    where in the training it lives
#   name:   the section name as it appears in the PDF
#   text:   the actual paragraph or script from the training (not paraphrased)
#   key_rules: the rule callouts from that page (when relevant)

QUOTES = {

    "ajs_close": {
        "scenario": "1",
        "step": "4",
        "name": "Estimate & Price - Rules of the Range",
        "text": (
            "Confidence is EVERYTHING. Believe in what you're saying, KNOW YOUR WORTH. "
            "Bring ENERGY and EXCITEMENT to the bid. Make it fun and unique for the customer. "
            "Memorizing the price list gives you credibility. Read the customer's body language - "
            "body language doesn't whisper. Never mention Minimum Charge - customers hear the price they "
            "want to hear. Only give the full truck price: 'To fill our truck all the way is $___, "
            "we do have 13 different price points to ensure you only pay for the space your items take "
            "up on the truck.' Bid the job at what it is and cut the maybes and probablys out. "
            "You are the expert. The lowest part of your range is what you think it is. "
            "The Assumptive Ask MUST come right after the range is given - no pauses. "
            "Replace pain with pleasure - paint the picture of the completed project."
        ),
    },

    "assumptive_ask": {
        "scenario": "1",
        "step": "5",
        "name": "Assumptive Ask",
        "text": (
            "The Assumptive Ask should be immediately paired with the estimate and price. "
            "Right after the bid, it is YOUR job to lead the customer and get things started. "
            "Do NOT wait for the 'ok'. Tell them what you are about to do. Give them an estimated "
            "time of how long it will take to complete the job, and paint the picture of the "
            "completed project. Always make sure to let them know to look for other items or tasks "
            "around the house while you're working - utilize the Costco Effect. "
            "Examples: 'With everything you have shown me, you are going to be filling up 1/2 - 2/3 "
            "of a load. There are items in the basement, backyard and garage; where would you like "
            "for us to start?' Or: 'We have an empty truck in the driveway and are ready to get "
            "started for you. Would you prefer that we start downstairs or in the backyard?'"
        ),
    },

    "five_star_agenda": {
        "scenario": "1",
        "step": "1B",
        "name": "5 Star Service Agenda - Dedication Script",
        "text": (
            "This should be presented naturally and NOT sound robotic. "
            "'Good morning Mr. or Ms. Last Name, my name is ____, this is my partner ____ and we "
            "would like to thank you for providing us the opportunity to serve you today! "
            "If it is ok with you, we would love to walk you through our Dedication to 5 Star Service "
            "Agenda. First, we will start by doing a WALK THROUGH of your property... We will then "
            "complete a THOROUGH EVALUATION of the items to assess the load size... We will then "
            "provide you with a FREE NO OBLIGATION ESTIMATE. As soon as we receive your blessing of "
            "APPROVAL, we have an empty truck parked out front and we are fully equipped and READY "
            "to get the job done for you TODAY! The last thing we want to guarantee you is that we "
            "are dedicated to providing you with a 5 star experience. If at any time you feel as if "
            "you are receiving anything less than a 5 star experience, please DO NOT hesitate to "
            "pull me aside. My name is ____ and I will be the lead representative on behalf of our "
            "company today.' Roll straight into Relevant Rapport."
        ),
    },

    "ford_rapport": {
        "scenario": "1",
        "step": "2",
        "name": "Relevant Rapport - FORD + Power Questions",
        "text": (
            "Personal rapport: making a friend with the customer. FORD - Family, Occupation, "
            "Recreation, Dreams. Relevant rapport: identifying important information about the "
            "customer's project and goal. Specific information about the items, their time frame, "
            "quality, or reasons for needing junk removal. The purpose is to lead to more effective "
            "communication and collaboration by achieving MORE for the customer. "
            "Example questions to use on every job: 'How long has this stuff been here?' "
            "'What are you planning on doing with the space once we get these items removed?' "
            "'Are there any items of sentimental value or importance that we should handle with "
            "extra care?' 'What were you hoping to accomplish today?' 'What type of project are we "
            "working on today?'"
        ),
    },

    "three_power_questions": {
        "scenario": "1",
        "step": "3",
        "name": "Establish Value - Three Power Questions",
        "text": (
            "Three Power Questions to establish value: 1) What items will we be removing today? "
            "2) Why are you getting rid of the items? (This surfaces the value key - time, space, "
            "or effort.) 3) What is the project or end goal you are aiming to achieve? "
            "Then build value in three components: explain volume in full detail and All Inclusive "
            "Pricing (taxes, labor, loading, offloading, donations, recycling). Memorize the price "
            "list - eye contact, credibility, body language. Walk them through the life cycle of "
            "the items - what we do with their items once we drive away. Paint the picture of the "
            "completed project."
        ),
    },

    "reeap": {
        "scenario": "2",
        "step": "2",
        "name": "REEAP - Re-Establish Value Framework",
        "text": (
            "REEAP: Rapport, Establish Value, Estimate & Price, Assumptive Ask, Positive Ending. "
            "When a customer doesn't immediately agree with our initial bid, it's our responsibility "
            "to hold firm on the price and explain in a different way why our service makes sense "
            "given the situation. We will elaborate on our full service capabilities and the "
            "conveniences we will provide while on site. It is also important to explain what we do "
            "with their items after the job is completed. "
            "PRICE IS ONLY AN ISSUE IN THE ABSENCE OF VALUE."
        ),
    },

    "reestablish_new_info": {
        "scenario": "2",
        "step": "4",
        "name": "Re-Establish Value - Present New Information",
        "text": (
            "When a customer doesn't immediately agree, hold firm in price and reiterate with NEW "
            "information why our service makes sense given this specific situation. Break down the "
            "behind-the-scenes processes in reference to what we charge. "
            "Examples: 'One thing to consider, if you use our service today, we could actually do "
            "____ for you at the end, saving your time and your back.' "
            "'Once we're finished and get this room cleaned out, we can actually move your new TV "
            "and couch from upstairs down to this room.' "
            "'Our donation center comes by our warehouse at least once a week, I can guarantee you "
            "it will be in a new family's home within 14 days or so. Rest assured it will not be "
            "thrown away.'"
        ),
    },

    "alternatives": {
        "scenario": "2",
        "step": "5",
        "name": "Re-Establish Value - Identify Customer Alternatives",
        "text": (
            "Ask questions to identify the customer's alternative options - tools, time, manpower, "
            "or the full opportunity cost of doing it themselves (financial, time, labor, sacrifices). "
            "Examples: 'How else were you planning on getting rid of the items?' "
            "'Doing this yourself is possible, but will still cost you $____, and your entire weekend.' "
            "'You mentioned possibly getting a dumpster. With a dumpster, you pay full price regardless "
            "of how full it is. You also take the risk of your neighbors filling it before you do and "
            "it sits in your driveway for a week. With us, we will fill the dumpster and drive it "
            "away TODAY.'"
        ),
    },

    "priority_items_rollover": {
        "scenario": "3.1",
        "step": "4",
        "name": "Priority Items + Roll-Over Pricing",
        "text": (
            "Many of our customers are on a strict budget and cannot pay the full amount at the time "
            "it's due. Roll-Over Pricing: the customer pays what they can now, and we take the volume "
            "equivalent to their budget. On our next visit (within 30 days), we'll start at the "
            "volume/price they finished at before, and they only pay the difference. "
            "'Pay what you can now and pay the rest later.' "
            "It gives the customer time. It gets the ball rolling - clears space, gets rid of "
            "heavier items they can't move themselves. It saves them money vs. doing two separate "
            "jobs at full rate. Pair this with Priority Items: 'let's get something on the truck' - "
            "offer to take the bigger or heavier items that fit their budget today."
        ),
    },

    "coupon_delivery": {
        "scenario": "3.2",
        "step": "4",
        "name": "Coupon Delivery - $25 / $50",
        "text": (
            "The coupon is our 'kind gesture' to the customer. AFTER we have re-established value "
            "and made a 2nd attempt at full price, take a book of coupons out of the clipboard and "
            "hand it to the customer as you explain. How you deliver the coupon is EVERYTHING - "
            "make it special. Always have a REASON for offering it. "
            "Examples: 'I'm supposed to leave this coupon with you in exchange for using our "
            "service today, but if it would help, I could apply $25/$50 off TODAY.' "
            "'Because all the items are in the garage, I would be happy to give you this $25/$50 "
            "off today.' "
            "'Since you have 2 full loads today, I can offer 2 $50 off coupons, saving you $100 on "
            "the entire job.' "
            "Rules: 1/8 to 3/8 = $25 off. 1/2 to full load = $50 off. Coupon DOES NOT apply to Min "
            "Charge or SIP."
        ),
    },

    "negotiation_protocol": {
        "scenario": "3.3",
        "step": "4",
        "name": "Full Negotiation Protocol - 5 Steps",
        "text": (
            "1) Re-Establish Value: focus on replacing pain with pleasure using value keys (TIME, "
            "SPACE, EFFORT). 2) Priority Items: get something on the truck. Offer the priority items "
            "(bigger/heavier) that fit their budget. This step comes BEFORE the coupon so we can still "
            "get FULL PRICE. 3) Offer Coupon: $25/$50 depending on volume. Delivery must be special "
            "and exciting. 4) Identify Customer Budget: 'How else did you plan on getting rid of the "
            "items?' 'How much did you anticipate a service like ours would cost?' "
            "5) Call Operations: ALWAYS leave someone on site with the customer while making the "
            "call. TM gives ops the relevant info. Ops calls the customer back with the Final Offer. "
            "The more detailed we are with this call, the better chance we have to land the job as "
            "close to full price as possible."
        ),
    },

    "exceptional_receipt": {
        "scenario": "3.1",
        "step": "5",
        "name": "Exceptional Receipt - Positive Ending",
        "text": (
            "A thorough receipt demonstrates professionalism and attention to detail. Include a "
            "'Thank You' with the team's names listed, a detailed breakdown of the load size, items "
            "removed, additional fees, and discounts. NO STANDARD JUNK REMOVAL on the receipt. "
            "Transparent pricing especially matters when the spouse is not on site. "
            "Example: '1/2 Load (1) - Reclining sofa, donatable loveseat, donatable kitchen table, "
            "4 chairs, 2 television, 2 boxes, 1 lamp. E-Waste (2) - recycling fees for 2 tube tvs. "
            "Discount (1) - $25 off - door hanger. Thank you for using our service today! Alex/Bryce.'"
        ),
    },

    "costco_effect": {
        "scenario": "1",
        "step": "5",
        "name": "Costco Effect - Drive Volume On Site",
        "text": (
            "While we're working, ask the customer to look around for other items or tasks. They "
            "forget what's still on the list until you remind them. This is the Costco Effect - "
            "a small assumptive prompt mid-job that often turns a 1/3 load into a 1/2 or 5/8."
        ),
    },
}


# ---------- map metric pattern to coaching anchor ----------

# Order matters: when more than one applies, the earlier one is the primary anchor.
METRIC_ANCHORS = {
    # AJS-led: close mechanics
    "ajs":         ["ajs_close", "assumptive_ask", "three_power_questions"],
    # Complaint-led: agenda + rapport
    "complaint":   ["five_star_agenda", "ford_rapport", "exceptional_receipt"],
    # NPS-led: rapport + experience
    "nps":         ["ford_rapport", "five_star_agenda", "exceptional_receipt"],
    # Reviews-led: 5 Star promise + closeout follow-through
    "gr":          ["five_star_agenda", "exceptional_receipt", "assumptive_ask"],
    # Cancel save: full negotiation
    "cancel_save": ["negotiation_protocol", "priority_items_rollover", "coupon_delivery", "reeap"],
    # Truck+ weakness: priority items + costco effect
    "truck_plus":  ["priority_items_rollover", "costco_effect", "ajs_close"],
}


def quote_for(primary_issue: str, secondary: bool = False) -> dict:
    """Return the most relevant training quote for a given metric pattern."""
    keys = METRIC_ANCHORS.get(primary_issue, [])
    if not keys:
        return QUOTES["ajs_close"]
    idx = 1 if (secondary and len(keys) > 1) else 0
    return QUOTES[keys[idx]]


def all_quotes_for(primary_issue: str) -> list[dict]:
    """All quotes mapped to this issue (for AI context-building)."""
    keys = METRIC_ANCHORS.get(primary_issue, [])
    return [QUOTES[k] for k in keys if k in QUOTES]


def scenario_label(quote: dict) -> str:
    """Format a scenario reference like 'Scenario 1, Step 4 - Estimate & Price'."""
    s = quote.get("scenario", "")
    step = quote.get("step", "")
    name = quote.get("name", "")
    if s == "all":
        return name
    return f"Scenario {s}, Step {step} - {name}"
