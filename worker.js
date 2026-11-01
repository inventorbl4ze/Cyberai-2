// CYBERAI 2.0 secure AI gateway — deploy as a Cloudflare Worker.
const corsHeaders = (origin, allowedOrigin) => ({
  "Access-Control-Allow-Origin": allowedOrigin === "*" ? "*" : (origin === allowedOrigin ? origin : allowedOrigin),
  "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
  "Vary": "Origin"
});

const recentRequests = new Map();
function rateLimited(ip) {
  const now = Date.now();
  const record = recentRequests.get(ip) || { start: now, count: 0 };
  if (now - record.start > 60_000) {
    record.start = now;
    record.count = 0;
  }
  record.count++;
  recentRequests.set(ip, record);
  if (recentRequests.size > 500) {
    for (const [key, value] of recentRequests) {
      if (now - value.start > 60_000) recentRequests.delete(key);
    }
  }
  return record.count > 20;
}

function json(data, status, headers) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", ...headers }
  });
}

export default {
  async fetch(request, env) {
    const origin = request.headers.get("Origin") || "";
    const allowedOrigin = env.ALLOWED_ORIGIN || "*";
    const headers = corsHeaders(origin, allowedOrigin);
    const url = new URL(request.url);

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers });
    }

    if (url.pathname === "/health" && request.method === "GET") {
      return json({ ok: true, service: "CYBERAI 2.0 AI gateway" }, 200, headers);
    }

    if (url.pathname !== "/api/chat" || request.method !== "POST") {
      return json({ error: "Not found" }, 404, headers);
    }

    if (allowedOrigin !== "*" && origin !== allowedOrigin) {
      return json({ error: "This website origin is not allowed." }, 403, headers);
    }

    const ip = request.headers.get("CF-Connecting-IP") || "unknown";
    if (rateLimited(ip)) {
      return json({ error: "Too many messages. Please wait a minute and try again." }, 429, headers);
    }

    if (!env.OPENAI_API_KEY) {
      return json({ error: "The AI service is not configured yet. Add the OPENAI_API_KEY secret to this Worker." }, 503, headers);
    }

    let body;
    try {
      const raw = await request.text();
      if (raw.length > 20_000) return json({ error: "Message is too large." }, 413, headers);
      body = JSON.parse(raw);
    } catch {
      return json({ error: "Invalid request body." }, 400, headers);
    }

    const message = typeof body.message === "string" ? body.message.trim().slice(0, 4000) : "";
    if (!message) return json({ error: "Please enter a message." }, 400, headers);

    const history = Array.isArray(body.history) ? body.history.slice(-10).map(item => ({
      role: item && item.role === "assistant" ? "assistant" : "user",
      content: String(item && item.content || "").slice(0, 2000)
    })).filter(item => item.content) : [];

    const input = [
      ...history,
      { role: "user", content: message }
    ];

    try {
      const apiResponse = await fetch("https://api.openai.com/v1/responses", {
        method: "POST",
        headers: {
          "Authorization": "Bearer " + env.OPENAI_API_KEY,
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          model: env.AI_MODEL || "gpt-5.5",
          instructions: "You are CYBERAI 2.0, a helpful, friendly, accurate AI assistant created by Oduyebo Abiola. Answer clearly and naturally. Be honest when uncertain. For schoolwork, explain concepts and help the learner understand rather than simply encouraging copying. Do not claim to see, hear, or access anything that was not provided in the conversation.",
          input,
          max_output_tokens: 1200
        })
      });

      const result = await apiResponse.json().catch(() => ({}));
      if (!apiResponse.ok) {
        const message = result && result.error && result.error.message;
        return json({ error: message || "The AI provider could not complete that request." }, apiResponse.status, headers);
      }

      const answer = (result.output || [])
        .filter(item => item.type === "message")
        .flatMap(item => item.content || [])
        .filter(item => item.type === "output_text")
        .map(item => item.text || "")
        .join("\n")
        .trim();

      if (!answer) return json({ error: "The AI returned an empty response. Please try again." }, 502, headers);
      return json({ answer }, 200, headers);
    } catch {
      return json({ error: "Could not reach the AI service. Please try again." }, 502, headers);
    }
  }
};
