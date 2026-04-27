/**
 * NEE Coaching Chat Proxy - Cloudflare Worker
 *
 * Sits between the dashboard (static page on GitHub Pages) and the Anthropic API.
 * Holds the API key as a secret so the browser never sees it.
 *
 * Deploy: see worker/DEPLOY.md
 *
 * Required Worker secret:
 *   ANTHROPIC_API_KEY  - your sk-ant-... key
 *
 * Optional Worker variables:
 *   ALLOWED_ORIGIN   - e.g. https://thomashaslam.github.io  (default: *)
 *   MODEL            - default claude-haiku-4-5-20251001
 *   MAX_TOKENS       - default 800
 */

const DEFAULT_MODEL = "claude-haiku-4-5-20251001";

export default {
  async fetch(request, env) {
    const allowedOrigin = env.ALLOWED_ORIGIN || "*";

    // CORS preflight
    if (request.method === "OPTIONS") {
      return new Response(null, {
        status: 204,
        headers: corsHeaders(allowedOrigin),
      });
    }

    if (request.method !== "POST") {
      return json({ error: "Use POST" }, 405, allowedOrigin);
    }

    if (!env.ANTHROPIC_API_KEY) {
      return json({ error: "Server is missing ANTHROPIC_API_KEY" }, 500, allowedOrigin);
    }

    let body;
    try {
      body = await request.json();
    } catch {
      return json({ error: "Invalid JSON body" }, 400, allowedOrigin);
    }

    const { teammate, history, question } = body;
    if (!teammate || !question) {
      return json({ error: "Missing teammate or question" }, 400, allowedOrigin);
    }

    // Build the system + user messages
    const system = SYSTEM_PROMPT;
    const messages = [
      {
        role: "user",
        content: buildContextPrompt(teammate, question, history || []),
      },
    ];

    try {
      const upstream = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-api-key": env.ANTHROPIC_API_KEY,
          "anthropic-version": "2023-06-01",
        },
        body: JSON.stringify({
          model: env.MODEL || DEFAULT_MODEL,
          max_tokens: parseInt(env.MAX_TOKENS || "800", 10),
          system,
          messages,
        }),
      });

      const data = await upstream.json();
      if (!upstream.ok) {
        return json(
          { error: data?.error?.message || "Anthropic API error", status: upstream.status },
          upstream.status,
          allowedOrigin,
        );
      }

      const text = (data?.content || [])
        .filter((b) => b.type === "text")
        .map((b) => b.text)
        .join("\n")
        .trim();

      return json({ reply: text, model: data?.model }, 200, allowedOrigin);
    } catch (e) {
      return json({ error: String(e) }, 502, allowedOrigin);
    }
  },
};

const SYSTEM_PROMPT = `You are an expert sales coach for 1-800-GOT-JUNK? franchises, \
helping any team leader on the New England Elite (NEE) leadership team develop their \
teammates. You answer questions about specific teammates using their performance data \
and the company's actual CSL Scenario training material.

VOICE RULES (strict):
- Warm but direct. Confident, action-first. Like a senior coach giving a peer the read.
- NEVER name a specific coach, manager, GM, or person other than the teammate. \
Frame actions as "Pull 15 minutes...", "Ride along this week...", "Run a Scenario X.X drill...". \
Any leader on the team must be able to act on this without context.
- No em dashes. Use periods or commas instead.
- Specific to this teammate's actual numbers. No generic platitudes.
- Reference the actual training material when relevant. Use real scenario names \
and step numbers from the context provided in the prompt.
- Be brief but substantive. 1-3 short paragraphs is usually enough. \
Use bullet points sparingly, only when listing concrete actions.

You will receive:
- The teammate's full performance data (metrics vs standards, score breakdown, severity)
- The current AI-generated coaching write-up (Why / Play / Coaching Anchor)
- Any prior chat history in this conversation
- The leader's question

If the question is outside what you can answer from the data and training context, \
say so directly and suggest what additional info would help. Do not invent metrics, \
training content, or teammate background.`;

function buildContextPrompt(tm, question, history) {
  const metrics = (tm.metrics || [])
    .map((m) => `  ${m.l}: ${m.v}${m.c ? " (" + m.c + ")" : ""}`)
    .join("\n");

  const anchor = tm.anchor || {};
  const anchorBlock = anchor.ref
    ? `Coaching Anchor reference: ${anchor.ref}
Anchor name: ${anchor.name || ""}
Anchor rationale: ${anchor.rationale || ""}
Training quote: "${anchor.quote || ""}"`
    : "(no anchor available)";

  const histBlock = history.length
    ? "\n\nPRIOR EXCHANGES IN THIS CONVERSATION:\n" +
      history
        .slice(-6)
        .map((m) => `[${m.role.toUpperCase()}] ${m.text}`)
        .join("\n\n")
    : "";

  return `TEAMMATE PROFILE
Name: ${tm.name}
Role: ${tm.role}
Franchise: ${tm.franchiseName || tm.franchiseCode}
Severity: ${tm.severity}
Priority slot today: ${tm.priority}

PERFORMANCE METRICS
${metrics}

CURRENT COACHING WRITE-UP (today's daily generation)
WHY:
${tm.why || ""}

PLAY:
${tm.play || ""}

ANCHOR:
${anchorBlock}
${histBlock}

LEADER'S QUESTION:
${question}

Answer the leader's question using the data and training context above. Stay in voice.`;
}

function corsHeaders(origin) {
  return {
    "access-control-allow-origin": origin,
    "access-control-allow-methods": "POST, OPTIONS",
    "access-control-allow-headers": "content-type",
    "access-control-max-age": "86400",
    vary: "Origin",
  };
}

function json(obj, status, origin) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: {
      "content-type": "application/json",
      ...corsHeaders(origin),
    },
  });
}
