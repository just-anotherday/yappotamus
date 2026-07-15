function withCors(headers = {}) {
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET,POST,DELETE,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type,x-admin-reset-token",
    ...headers
  };
}

function normalizeAndRankScores(scores) {
  return scores
    .filter((entry) => entry && typeof entry.name === "string" && Number.isFinite(Number(entry.score)))
    .map((entry) => ({
      name: entry.name.trim() || "Anonymous",
      score: Number(entry.score),
      rounds: Math.max(1, Number(entry.rounds) || 1),
      avgWpm: Number(entry.avgWpm ?? entry.avg_wpm ?? 0),
      avgAccuracy: Number(entry.avgAccuracy ?? entry.avg_accuracy ?? 0)
    }))
    .sort((a, b) => b.score - a.score)
    .slice(0, 20);
}

async function readScores(env) {
  try {
    const { results } = await env.DB.prepare(
      `SELECT name, score, rounds,
              (CASE WHEN rounds > 0 THEN total_wpm / rounds ELSE 0 END) AS avg_wpm,
              (CASE WHEN rounds > 0 THEN total_accuracy / rounds ELSE 0 END) AS avg_accuracy
       FROM leaderboard
       ORDER BY score DESC, id ASC
       LIMIT 20`
    ).all();

    return normalizeAndRankScores(results || []);
  } catch {
    // Legacy schema fallback (no rounds/total_wpm/total_accuracy columns yet)
    const { results } = await env.DB.prepare(
      `SELECT name, score
       FROM leaderboard
       ORDER BY score DESC, id ASC
       LIMIT 20`
    ).all();

    return normalizeAndRankScores(results || []);
  }
}

export default {
  async fetch(request, env) {
    try {
      const url = new URL(request.url);

    if (url.pathname === "/favicon.ico") {
      return new Response(null, { status: 204 });
    }

      if (url.pathname === "/api/health") {
      if (!env.DB) {
        return new Response(JSON.stringify({ status: "error", message: "DB binding missing" }), {
          status: 500,
          headers: withCors({ "Content-Type": "application/json" })
        });
      }
      const { results } = await env.DB.prepare("SELECT 1 as ok").all();
      return new Response(JSON.stringify({
        status: "ok",
        d1: Array.isArray(results) && results.length > 0
      }), {
        status: 200,
        headers: withCors({ "Content-Type": "application/json" })
      });
    }

      if (url.pathname === "/wpm" || url.pathname === "/wpm/") {
      const target = new URL("/wpm.html", request.url);
      return Response.redirect(target.toString(), 302);
      }

      if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: withCors() });
      }

      if (url.pathname !== "/api/leaderboard") {
      // Let Cloudflare static assets handle all non-API routes.
      return env.ASSETS.fetch(request);
      }

      if (!env.DB) {
      return new Response(JSON.stringify({ error: "Server misconfiguration", message: "DB binding missing" }), {
        status: 500,
        headers: withCors({ "Content-Type": "application/json" })
      });
      }

      if (request.method === "GET") {
      const scores = await readScores(env);
      return new Response(JSON.stringify(scores), {
        status: 200,
        headers: withCors({ "Content-Type": "application/json" })
      });
      }

      if (request.method === "POST") {
      const body = await request.json().catch(() => null);
      if (!body || typeof body.score !== "number" || typeof body.wpm !== "number" || typeof body.accuracy !== "number") {
        return new Response(JSON.stringify({ error: "Invalid payload" }), {
          status: 400,
          headers: withCors({ "Content-Type": "application/json" })
        });
      }

      const name = typeof body.name === "string" ? body.name.trim() : "Anonymous";
      const score = Number(body.score);
      const wpm = Number(body.wpm);
      const accuracy = Number(body.accuracy);
      if (!Number.isFinite(score) || score <= 0) {
        return new Response(JSON.stringify({ error: "Invalid score" }), {
          status: 400,
          headers: withCors({ "Content-Type": "application/json" })
        });
      }
      if (!Number.isFinite(wpm) || wpm < 0 || !Number.isFinite(accuracy) || accuracy < 0) {
        return new Response(JSON.stringify({ error: "Invalid metrics" }), {
          status: 400,
          headers: withCors({ "Content-Type": "application/json" })
        });
      }

      const normalizedName = (name || "Anonymous").slice(0, 32);

      try {
        const existing = await env.DB.prepare(
          `SELECT id, score, rounds, total_wpm, total_accuracy
           FROM leaderboard
           WHERE name = ?
           LIMIT 1`
        ).bind(normalizedName).first();

        if (existing && Number.isFinite(Number(existing.score))) {
          await env.DB.prepare(
            `UPDATE leaderboard
             SET score = ?, rounds = ?, total_wpm = ?, total_accuracy = ?
             WHERE id = ?`
          ).bind(
            Number(existing.score) + score,
            Math.max(1, Number(existing.rounds) || 1) + 1,
            Number(existing.total_wpm || 0) + wpm,
            Number(existing.total_accuracy || 0) + accuracy,
            existing.id
          ).run();
        } else {
          await env.DB.prepare(
            `INSERT INTO leaderboard (name, score, rounds, total_wpm, total_accuracy) VALUES (?, ?, ?, ?, ?)`
          ).bind(normalizedName, score, 1, wpm, accuracy).run();
        }
      } catch {
        // Legacy schema fallback (name + score only)
        const existingLegacy = await env.DB.prepare(
          `SELECT id, score
           FROM leaderboard
           WHERE name = ?
           LIMIT 1`
        ).bind(normalizedName).first();

        if (existingLegacy && Number.isFinite(Number(existingLegacy.score))) {
          await env.DB.prepare(
            `UPDATE leaderboard
             SET score = ?
             WHERE id = ?`
          ).bind(
            Number(existingLegacy.score) + score,
            existingLegacy.id
          ).run();
        } else {
          await env.DB.prepare(
            `INSERT INTO leaderboard (name, score) VALUES (?, ?)`
          ).bind(normalizedName, score).run();
        }
      }

      const ranked = await readScores(env);

      return new Response(JSON.stringify(ranked), {
        status: 200,
        headers: withCors({ "Content-Type": "application/json" })
      });
      }

      if (request.method === "DELETE") {
      const adminToken = request.headers.get("x-admin-reset-token") || "";
      if (!env.RESET_TOKEN || adminToken !== env.RESET_TOKEN) {
        return new Response(JSON.stringify({ error: "Unauthorized" }), {
          status: 403,
          headers: withCors({ "Content-Type": "application/json" })
        });
      }

      await env.DB.prepare(`DELETE FROM leaderboard`).run();
      return new Response(JSON.stringify([]), {
        status: 200,
        headers: withCors({ "Content-Type": "application/json" })
      });
      }

      return new Response("Method Not Allowed", { status: 405, headers: withCors() });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown worker error";
      return new Response(JSON.stringify({ error: "Internal Server Error", message }), {
        status: 500,
        headers: withCors({ "Content-Type": "application/json" })
      });
    }
  }
};
