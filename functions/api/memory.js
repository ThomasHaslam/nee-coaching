/**
 * Coach Rick's memory layer.
 *
 * Per-leader, persistent storage backed by Cloudflare KV (binding: RICK_MEMORY).
 * The leader_id is a UUID generated client-side and stored in localStorage; we
 * do not have user identity, so all memory is partitioned by device.
 *
 * Endpoints:
 *   POST /api/memory   - append a note or feedback record
 *   GET  /api/memory   - return memory blocks for a leader (notes for a TM, feedback summary, etc.)
 *
 * Storage keys:
 *   leader:{leaderId}:notes:{tmId}     -> JSON array of notes about this teammate (or "__general__")
 *   leader:{leaderId}:feedback         -> JSON array of feedback records on Rick's chat replies
 *   leader:{leaderId}:profile          -> JSON object with the leader's preferences/style
 *
 * Hard caps to keep prompt context tight:
 *   - 50 most recent notes per (leader, tm)
 *   - 200 most recent feedback records per leader
 */

const NOTE_CAP = 50;
const FEEDBACK_CAP = 200;
const NOTE_TEXT_MAX = 2000;
const COMMENT_TEXT_MAX = 1500;

function corsHeaders(origin) {
  return {
    "access-control-allow-origin": origin || "*",
    "access-control-allow-methods": "POST, GET, OPTIONS",
    "access-control-allow-headers": "content-type",
    "access-control-max-age": "86400",
    vary: "Origin",
  };
}
function json(obj, status, origin) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "content-type": "application/json", ...corsHeaders(origin) },
  });
}
function uuid() {
  // RFC4122-ish v4
  const r = crypto.getRandomValues(new Uint8Array(16));
  r[6] = (r[6] & 0x0f) | 0x40;
  r[8] = (r[8] & 0x3f) | 0x80;
  const h = Array.from(r, b => b.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0,8)}-${h.slice(8,12)}-${h.slice(12,16)}-${h.slice(16,20)}-${h.slice(20)}`;
}
function safeLeaderId(s) {
  // Defensive: leaderId is user-controlled; whitelist [a-z0-9-] only
  return typeof s === "string" && /^[a-z0-9\-]{8,64}$/i.test(s) ? s : null;
}
function safeTmId(s) {
  // tmIds in the page look like "tm-bno-1" or "roster-bno-Joe-Smith"; or "__general__"
  return typeof s === "string" && /^[a-zA-Z0-9_\-.]{1,80}$/.test(s) ? s : null;
}

async function readJson(env, key, fallback) {
  try {
    const v = await env.RICK_MEMORY.get(key);
    if (!v) return fallback;
    return JSON.parse(v);
  } catch {
    return fallback;
  }
}
async function writeJson(env, key, value) {
  await env.RICK_MEMORY.put(key, JSON.stringify(value));
}

async function appendCapped(env, key, record, cap) {
  const arr = await readJson(env, key, []);
  arr.push(record);
  if (arr.length > cap) arr.splice(0, arr.length - cap);
  await writeJson(env, key, arr);
  return arr.length;
}

export async function onRequest({ request, env }) {
  const origin = request.headers.get("origin") || "*";

  if (request.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: corsHeaders(origin) });
  }
  if (!env.RICK_MEMORY) {
    return json({ error: "Memory store not bound. RICK_MEMORY KV namespace missing." }, 500, origin);
  }

  // ===== GET: read memory for a leader =====
  if (request.method === "GET") {
    const url = new URL(request.url);
    const leaderId = safeLeaderId(url.searchParams.get("leaderId"));
    if (!leaderId) return json({ error: "Missing or invalid leaderId" }, 400, origin);
    const tmId = url.searchParams.get("tmId");

    if (tmId) {
      const safeTm = safeTmId(tmId);
      if (!safeTm) return json({ error: "Invalid tmId" }, 400, origin);
      const notes = await readJson(env, `leader:${leaderId}:notes:${safeTm}`, []);
      return json({ notes }, 200, origin);
    }
    // Without a tmId, return a digest: counts + last 5 general notes + last 5 feedback
    const generalNotes = await readJson(env, `leader:${leaderId}:notes:__general__`, []);
    const feedback = await readJson(env, `leader:${leaderId}:feedback`, []);
    const profile = await readJson(env, `leader:${leaderId}:profile`, null);
    return json({
      generalNotes: generalNotes.slice(-5),
      generalNotesTotal: generalNotes.length,
      recentFeedback: feedback.slice(-5),
      feedbackTotal: feedback.length,
      profile,
    }, 200, origin);
  }

  // ===== POST: append a record =====
  if (request.method !== "POST") {
    return json({ error: "Use GET or POST" }, 405, origin);
  }

  let body;
  try { body = await request.json(); } catch { return json({ error: "Invalid JSON" }, 400, origin); }

  const leaderId = safeLeaderId(body.leaderId);
  if (!leaderId) return json({ error: "Missing or invalid leaderId" }, 400, origin);

  const kind = body.kind;
  const ts = new Date().toISOString();

  if (kind === "note") {
    const tmId = safeTmId(body.tmId || "__general__");
    if (!tmId) return json({ error: "Invalid tmId" }, 400, origin);
    const text = String(body.text || "").trim().slice(0, NOTE_TEXT_MAX);
    if (!text) return json({ error: "Empty note" }, 400, origin);
    const tmName = String(body.tmName || "").slice(0, 100);
    const tmRole = String(body.tmRole || "").slice(0, 40);
    const franchiseCode = String(body.franchiseCode || "").slice(0, 8);
    const record = { id: uuid(), ts, text, tmName, tmRole, franchiseCode };
    const total = await appendCapped(env, `leader:${leaderId}:notes:${tmId}`, record, NOTE_CAP);
    return json({ ok: true, id: record.id, total }, 200, origin);
  }

  if (kind === "feedback") {
    const rating = body.rating === "up" || body.rating === "down" ? body.rating : null;
    if (!rating) return json({ error: "Rating must be 'up' or 'down'" }, 400, origin);
    const comment = String(body.comment || "").trim().slice(0, COMMENT_TEXT_MAX);
    const record = {
      id: uuid(), ts, rating, comment,
      tmName: String(body.tmName || "").slice(0, 100),
      tmId: safeTmId(body.tmId) || null,
      question: String(body.question || "").slice(0, 1000),
      replyExcerpt: String(body.replyExcerpt || "").slice(0, 500),
    };
    const total = await appendCapped(env, `leader:${leaderId}:feedback`, record, FEEDBACK_CAP);
    return json({ ok: true, id: record.id, total }, 200, origin);
  }

  if (kind === "profile") {
    const profile = body.profile || {};
    // Whitelist fields and trim
    const clean = {
      displayName: String(profile.displayName || "").slice(0, 80),
      style: String(profile.style || "").slice(0, 200),
      contextNotes: String(profile.contextNotes || "").slice(0, 2000),
      updatedAt: ts,
    };
    await writeJson(env, `leader:${leaderId}:profile`, clean);
    return json({ ok: true, profile: clean }, 200, origin);
  }

  return json({ error: "Unknown kind. Use 'note', 'feedback', or 'profile'." }, 400, origin);
}
