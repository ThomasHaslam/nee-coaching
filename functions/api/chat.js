/**
 * Coach Rick - real-time chat function for Cloudflare Pages.
 *
 * Lives at https://<your-project>.pages.dev/api/chat (POST).
 * Holds the Anthropic API key as a Cloudflare environment variable so the
 * browser never sees it.
 *
 * Required Pages env var:
 *   ANTHROPIC_API_KEY  - your sk-ant-... key
 *
 * Optional:
 *   ANTHROPIC_MODEL    - default claude-haiku-4-5-20251001
 */

// ===== TRAINING KNOWLEDGE BASE (mirrors scripts/training_kb.py) =====
// Coach Rick has the entire CSL Scenario library on every chat turn.

const SCENARIOS = {
  "1":   "Standard Sales Process - clean run, customer ready to buy. Steps: 1A Call Ahead, 1B 5 Star Service Agenda, 2 Relevant Rapport (FORD), 3 Establish Value (Three Power Questions), 4 Estimate & Price (Rules of the Range, Plus 1, Plus 2), 5 Assumptive Ask (Costco Effect).",
  "2":   "Re-Establish Value (Pushback) - customer hesitates after first bid. Steps: REEAP framework, Re-Establish Value 3 ways (different way, new info, alternatives).",
  "3.1": "Roll-Over Pricing - budget-constrained customer. Get something on the truck now, finish at same volume mark on a return visit within 30 days. Includes Priority Items.",
  "3.2": "Coupon Delivery - $25 for 1/8 to 3/8 load, $50 for 1/2 to full. After re-establishing value. How you deliver it is everything; always have a reason. Doesn't apply to Min Charge or SIP.",
  "3.3": "Full Negotiation Protocol - cancel-edge customer. 5 steps: Re-Establish Value, Priority Items (full price first), Coupon, Identify Budget, Call Operations with TM on site.",
};

const TRAINING_QUOTES = [
  {
    ref: "Scenario 1 Step 4 - Estimate & Price (Rules of the Range)",
    text: "Confidence is EVERYTHING. Believe in what you're saying, KNOW YOUR WORTH. Bring ENERGY and EXCITEMENT to the bid. Memorize the price list - eye contact, credibility, body language. Never mention Min Charge - customers hear the price they want to hear. Only give the full truck price. Bid the job at what it is and cut the maybes and probablys out. The lowest part of your range is what you think it is. The Assumptive Ask MUST come right after the range is given - no pauses. Replace pain with pleasure - paint the picture of the completed project."
  },
  {
    ref: "Scenario 1 Step 5 - Assumptive Ask",
    text: "The Assumptive Ask should be immediately paired with the estimate and price. Right after the bid, it is YOUR job to lead the customer. Do NOT wait for the 'ok'. Tell them what you are about to do. Examples: 'With everything you have shown me, you are going to be filling up 1/2 to 2/3 of a load. There are items in the basement, backyard and garage; where would you like for us to start?' Or: 'We have an empty truck in the driveway and are ready to get started for you. Would you prefer that we start downstairs or in the backyard?' Use value keys (Time, Space, Effort). Utilize the Costco Effect - while working, ask customer to look around for other items."
  },
  {
    ref: "Scenario 1 Step 1B - 5 Star Service Agenda",
    text: "Should be presented naturally, NOT robotic. 'Good morning Mr/Ms Last Name, my name is ____, this is my partner ____ and we would like to thank you for providing us the opportunity to serve you today. If it is ok with you, we would love to walk you through our Dedication to 5 Star Service Agenda. First, we will start by doing a WALK THROUGH of your property... THOROUGH EVALUATION of the items to assess load size... FREE NO OBLIGATION ESTIMATE. As soon as we receive your blessing of APPROVAL, we have an empty truck parked out front and we are fully equipped and READY to get the job done for you TODAY. The last thing we want to guarantee you is that we are dedicated to providing you with a 5 star experience. If at any time you feel as if you are receiving anything less than a 5 star experience, please DO NOT hesitate to pull me aside.' Roll straight into Relevant Rapport."
  },
  {
    ref: "Scenario 1 Step 2 - Relevant Rapport (FORD + Power Questions)",
    text: "Personal rapport: making a friend with the customer. FORD - Family, Occupation, Recreation, Dreams. Relevant rapport: identify info about the customer's project and goal - items, time frame, quality, reasons for needing junk removal. Example questions to use on every job: 'How long has this stuff been here?' 'What are you planning on doing with the space once we get these items removed?' 'Are there any items of sentimental value or importance that we should handle with extra care?' 'What were you hoping to accomplish today?' 'What type of project are we working on today?' Purpose: lead to MORE for the customer."
  },
  {
    ref: "Scenario 1 Step 3 - Three Power Questions / Establish Value",
    text: "Three Power Questions: 1) What items will we be removing today? 2) Why are you getting rid of the items? (surfaces value key - time, space, effort) 3) What is the project or end goal you are aiming to achieve? Then build value in three components: explain volume in full detail and All Inclusive Pricing (taxes, labor, loading, offloading, donations, recycling). Memorize the price list. Walk through life cycle of items - what we do with them after we drive away. Paint the picture of the completed project."
  },
  {
    ref: "Scenario 2 Step 2 - REEAP Framework",
    text: "REEAP: Rapport, Establish Value, Estimate & Price, Assumptive Ask, Positive Ending. When a customer doesn't immediately agree with our initial bid, hold firm on the price and explain in a different way why our service makes sense. Elaborate on full service capabilities. Explain what we do with their items after the job. PRICE IS ONLY AN ISSUE IN THE ABSENCE OF VALUE."
  },
  {
    ref: "Scenario 2 Step 4 - Re-Establish Value (Present New Information)",
    text: "Hold firm and reiterate with NEW information. Break down the behind-the-scenes. Examples: 'One thing to consider, if you use our service today, we could actually do ____ for you at the end, saving your time and your back.' 'Once we're finished and get this room cleaned out, we can actually move your new TV and couch from upstairs down to this room.' 'Our donation center comes by our warehouse at least once a week, I can guarantee you it will be in a new family's home within 14 days or so. Rest assured it will not be thrown away.'"
  },
  {
    ref: "Scenario 2 Step 5 - Identify Customer Alternatives",
    text: "Ask questions to identify alternatives - tools, time, manpower, opportunity cost of doing it themselves. Examples: 'How else were you planning on getting rid of the items?' 'Doing this yourself is possible, but will still cost you $____ and your entire weekend.' 'You mentioned possibly getting a dumpster. With a dumpster, you pay full price regardless of how full it is. You also take the risk of your neighbors filling it before you do and it sits in your driveway for a week. With us, we will fill the dumpster and drive it away TODAY.'"
  },
  {
    ref: "Scenario 3.1 Step 4 - Priority Items + Roll-Over Pricing",
    text: "Many customers are on a strict budget and cannot pay full amount today. Roll-Over Pricing: customer pays what they can now, we take the volume equivalent. On the next visit (within 30 days), we start at the volume/price they finished at and they only pay the difference. 'Pay what you can now and pay the rest later.' Pair with Priority Items: 'let's get something on the truck' - offer to take the bigger or heavier items that fit their budget today."
  },
  {
    ref: "Scenario 3.2 Step 4 - Coupon Delivery ($25 / $50)",
    text: "The coupon is our 'kind gesture'. AFTER we have re-established value and made a 2nd attempt at full price, take a book of coupons out of the clipboard and hand it to the customer. How you deliver the coupon is EVERYTHING - make it special. Always have a REASON for offering it. Examples: 'I'm supposed to leave this coupon with you in exchange for using our service today, but if it would help, I could apply $25/$50 off TODAY.' 'Because all the items are in the garage, I would be happy to give you this $25/$50 off today.' 'Since you have 2 full loads today, I can offer 2 $50 off coupons, saving you $100.' Rules: 1/8 to 3/8 = $25 off. 1/2 to full load = $50 off. Doesn't apply to Min Charge or SIP."
  },
  {
    ref: "Scenario 3.3 Step 4 - Full Negotiation Protocol (5 steps)",
    text: "1) Re-Establish Value: focus on replacing pain with pleasure using value keys (TIME, SPACE, EFFORT). 2) Priority Items: get something on the truck. Offer the priority items (bigger/heavier) that fit their budget. This step comes BEFORE the coupon so we can still get FULL PRICE. 3) Offer Coupon: $25/$50 depending on volume. Make it special and exciting. 4) Identify Customer Budget: 'How else did you plan on getting rid of the items?' 'How much did you anticipate a service like ours would cost?' 5) Call Operations: ALWAYS leave someone on site with the customer while making the call. TM gives ops the relevant info. Ops calls the customer back with the Final Offer. Be ready to answer: 'Where are the items?' 'How long will the job take?' 'What's the last price you offered?' 'What's their budget?'"
  },
  {
    ref: "Scenario 3.1 Step 5 - Exceptional Receipt / Positive Ending",
    text: "A thorough receipt demonstrates professionalism. Include 'Thank You' with team's names listed, detailed breakdown of load size, items removed, additional fees, discounts. NO STANDARD JUNK REMOVAL on the receipt. Transparent pricing especially matters when the spouse is not on site. Example: '1/2 Load (1) - Reclining sofa, donatable loveseat, donatable kitchen table, 4 chairs, 2 television, 2 boxes, 1 lamp. E-Waste (2) - recycling fees for 2 tube tvs. Discount (1) - $25 off - door hanger. Thank you for using our service today! Alex/Bryce.'"
  },
  {
    ref: "Costco Effect (Scenario 1 Step 5)",
    text: "While we're working, ask the customer to look around for other items or tasks. They forget what's still on the list until you remind them. A small assumptive prompt mid-job often turns a 1/3 load into a 1/2 or 5/8."
  },
];

const SYSTEM_PROMPT = `You are COACH RICK, the in-house master sales coach for the New England Elite \
1-800-GOT-JUNK? region. You have coached hundreds of CSLs, CELs and SSLs through the CSL Scenario \
playbook. You speak with the calm authority of someone who has seen every pattern before.

You are answering questions in real time from a leader on the New England Elite leadership team. \
They are using a coaching dashboard that shows daily performance for each teammate.

VOICE RULES (strict):
- Warm but direct. Confident, action-first. Like a senior coach giving a peer the read.
- NEVER name a coach, manager, GM, or person other than the named teammate. Frame actions as \
imperatives: "Pull 15 minutes...", "Run a Scenario X.X drill...", "Block 20 minutes pre-shift...". \
Any leader on the team must be able to act on this without context.
- No em dashes. Use periods or commas.
- Specific to this teammate's actual numbers. If you cite a metric, cite the exact value.
- Reference the actual training material when relevant. Use real scenario names and step numbers.
- 1-3 short paragraphs is usually enough. Use bullet points only when listing concrete actions.

ADAPT YOUR COACHING TO THE TEAMMATE'S TIER:
- ELITE (score 95+): Recognition first. Ask what's working so other teammates can model it. \
Growth is about consistency, leadership reps, and stretch goals (mentoring, harder calls).
- SOLID (80-94): Light-touch maintenance. One small course-correction. Don't over-coach.
- WATCH (65-79): Curious, observational. Diagnose the pattern with them. One focused habit shift.
- URGENT (under 65): Direct, structured. Frame as Level 1 PIP territory if AJS is the driver. \
Pair shadow + scripted practice. 15-day target back to standard.

If the leader asks about a top performer, lead with what to recognize and what to learn from them. \
If the leader asks about a struggling teammate, lead with the most likely root cause and a concrete \
first step.

WHAT YOU KNOW:
You have the full CSL Scenario library (Scenarios 1, 2, 3.1, 3.2, 3.3) committed to memory. \
You will be given the relevant excerpts in every prompt. Treat them as authoritative.

You will also receive:
- The teammate's current performance data (metrics vs franchise standards) - sometimes the basic \
roster snapshot only, sometimes the full daily coaching write-up
- Any prior chat history in this conversation

If the question is something you cannot answer from this context, say so directly and suggest \
what additional info would help. Never invent training material, metrics, or teammate background.`;

function buildPrompt(tm, history, question) {
  const metricsLines = (tm.metrics || []).map(m => `  ${m.l}: ${m.v}${m.c ? ' (' + m.c + ')' : ''}`).join('\n');

  const anchor = tm.anchor || {};
  const anchorBlock = anchor.ref
    ? `Coaching Anchor: ${anchor.ref}\nName: ${anchor.name || ''}\nRationale: ${anchor.rationale || ''}\nQuote: "${anchor.quote || ''}"`
    : '(no anchor available)';

  const trainingLib = TRAINING_QUOTES.map(q => `--- ${q.ref} ---\n${q.text}`).join('\n\n');

  const histBlock = (history && history.length)
    ? '\n\nPRIOR EXCHANGES IN THIS CONVERSATION:\n' +
      history.slice(-8).map(m => `[${(m.role || 'user').toUpperCase()}] ${m.text}`).join('\n\n')
    : '';

  // Derive tier from score if not already set
  let tier = tm.tier;
  if (!tier) {
    const scoreMetric = (tm.metrics || []).find(m => m.l === 'Score');
    const scoreNum = scoreMetric ? parseInt(String(scoreMetric.v).split('/')[0], 10) : null;
    if (scoreNum !== null && Number.isFinite(scoreNum)) {
      tier = scoreNum >= 95 ? 'elite' : scoreNum >= 80 ? 'solid' : scoreNum >= 65 ? 'watch' : 'urgent';
    } else {
      tier = '(unknown)';
    }
  }

  return `TEAMMATE PROFILE
Name: ${tm.name}
Role: ${tm.role}
Franchise: ${tm.franchiseName || tm.franchiseCode}
Tier: ${tier} (use the matching coaching posture from the system prompt)
Severity today: ${tm.severity || '(daily picks list only - this teammate not on it today)'}
Priority slot today: ${tm.priority || '(not on today\'s coaching list)'}

PERFORMANCE METRICS THIS PERIOD
${metricsLines}

CURRENT COACHING WRITE-UP (today's daily generation)
WHY:
${tm.why || ''}

PLAY:
${tm.play || ''}

${anchorBlock}

CSL SCENARIO LIBRARY (use these excerpts as authoritative reference - cite exact scenario step numbers)
${trainingLib}
${histBlock}

LEADER'S QUESTION:
${question}

Answer in voice. Stay specific to this teammate's actual numbers. Reference the relevant Scenario step.`;
}

function corsHeaders(origin) {
  return {
    'access-control-allow-origin': origin || '*',
    'access-control-allow-methods': 'POST, OPTIONS',
    'access-control-allow-headers': 'content-type',
    'access-control-max-age': '86400',
    'vary': 'Origin',
  };
}

function json(obj, status = 200, origin) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { 'content-type': 'application/json', ...corsHeaders(origin) },
  });
}

export async function onRequest({ request, env }) {
  const origin = request.headers.get('origin') || '*';

  if (request.method === 'OPTIONS') {
    return new Response(null, { status: 204, headers: corsHeaders(origin) });
  }
  if (request.method !== 'POST') {
    return json({ error: 'Use POST' }, 405, origin);
  }
  if (!env.ANTHROPIC_API_KEY) {
    return json({ error: 'Server is missing ANTHROPIC_API_KEY' }, 500, origin);
  }

  let body;
  try { body = await request.json(); } catch { return json({ error: 'Invalid JSON' }, 400, origin); }

  const { teammate, history, question } = body || {};
  if (!teammate || !question || typeof question !== 'string') {
    return json({ error: 'Missing teammate or question' }, 400, origin);
  }

  const userPrompt = buildPrompt(teammate, history, question);

  try {
    const upstream = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'x-api-key': env.ANTHROPIC_API_KEY,
        'anthropic-version': '2023-06-01',
      },
      body: JSON.stringify({
        model: env.ANTHROPIC_MODEL || 'claude-haiku-4-5-20251001',
        max_tokens: 1200,
        system: SYSTEM_PROMPT,
        messages: [{ role: 'user', content: userPrompt }],
      }),
    });

    const data = await upstream.json();
    if (!upstream.ok) {
      return json(
        { error: data?.error?.message || 'Anthropic API error', status: upstream.status },
        upstream.status,
        origin,
      );
    }

    const text = (data?.content || [])
      .filter(b => b.type === 'text')
      .map(b => b.text)
      .join('\n')
      .trim();

    return json({ reply: text, model: data?.model }, 200, origin);
  } catch (e) {
    return json({ error: 'Network error: ' + (e && e.message ? e.message : String(e)) }, 502, origin);
  }
}
