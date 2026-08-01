// Idempotency + issued-licence ledger on Supabase (plain REST, no SDK).
//
// Table (see docs/VERCEL_FULFILLMENT.md):
//   capture_id text primary key,
//   status text not null,          -- claimed | signed | issued | failed
//   edition text, buyer_email text, buyer_name text,
//   license jsonb, error text,
//   created_at timestamptz default now(), updated_at timestamptz default now()
//
// Claim protocol (all outcomes FAIL CLOSED — any datastore ambiguity throws,
// the handler answers 500, PayPal retries):
//   * INSERT with return=representation: a returned row proves WE inserted
//     (atomic winner); an empty body proves a conflict (someone else owns it).
//   * Losers inspect the row: issued => done; signed => resume (email the
//     STORED licence — never sign twice); failed or stale-claimed => atomic
//     takeover via a conditional PATCH (row returned = we own it now);
//     fresh claimed => another invocation is working — back off.

const STALE_CLAIM_MS = 10 * 60 * 1000;

function req(env, path, init) {
  return fetch(`${env.SUPABASE_URL}/rest/v1/${path}`, {
    ...init,
    headers: {
      apikey: env.SUPABASE_SERVICE_KEY,
      Authorization: `Bearer ${env.SUPABASE_SERVICE_KEY}`,
      "Content-Type": "application/json",
      ...(init.headers || {}),
    },
  });
}

async function rows(response, what) {
  if (!response.ok) {
    throw new Error(`${what}: HTTP ${response.status}`);
  }
  const body = await response.json();
  if (!Array.isArray(body)) {
    throw new Error(`${what}: unexpected response shape`);
  }
  return body;
}

export function storeFactory(env) {
  const enc = encodeURIComponent;

  async function takeover(captureId, fromStatus, extraFilter = "") {
    const r = await req(env,
      `roar_licenses?capture_id=eq.${enc(captureId)}`
      + `&status=eq.${fromStatus}${extraFilter}`, {
        method: "PATCH",
        headers: { Prefer: "return=representation" },
        body: JSON.stringify({ status: "claimed",
                               updated_at: new Date().toISOString() }),
      });
    return (await rows(r, "store.takeover")).length === 1;
  }

  return {
    // Returns {state:"claimed"} | {state:"resume", license, buyerEmail,
    // buyerName} | {state:"done"} | {state:"in-progress"}. Throws on any
    // datastore error — never guesses.
    async claim(captureId, { edition }) {
      const insert = await req(env, "roar_licenses", {
        method: "POST",
        headers: { Prefer: "resolution=ignore-duplicates,return=representation" },
        body: JSON.stringify([{ capture_id: captureId, edition,
                                status: "claimed",
                                updated_at: new Date().toISOString() }]),
      });
      if ((await rows(insert, "store.claim insert")).length === 1) {
        return { state: "claimed" };            // atomic winner
      }
      const existing = await rows(await req(env,
        `roar_licenses?capture_id=eq.${enc(captureId)}`
        + "&select=status,license,buyer_email,buyer_name,updated_at",
        { method: "GET" }), "store.claim read");
      if (existing.length !== 1) {
        throw new Error("store.claim: conflicting insert but no row");
      }
      const row = existing[0];
      if (row.status === "issued") return { state: "done" };
      if (row.status === "signed") {
        return { state: "resume", license: row.license,
                 buyerEmail: row.buyer_email, buyerName: row.buyer_name };
      }
      if (row.status === "failed") {
        return (await takeover(captureId, "failed"))
          ? { state: "claimed" } : { state: "in-progress" };
      }
      // claimed: only steal it when the owner looks dead
      const age = Date.now() - Date.parse(row.updated_at || 0);
      if (age > STALE_CLAIM_MS) {
        const cutoff = new Date(Date.now() - STALE_CLAIM_MS).toISOString();
        return (await takeover(captureId, "claimed",
                               `&updated_at=lt.${enc(cutoff)}`))
          ? { state: "claimed" } : { state: "in-progress" };
      }
      return { state: "in-progress" };
    },

    // The licence is persisted BEFORE any email leaves: a retry after a crash
    // resumes with the SAME licence instead of signing a new one.
    async markSigned(captureId, { edition, buyerEmail, buyerName, license }) {
      const r = await req(env,
        `roar_licenses?capture_id=eq.${enc(captureId)}`, {
          method: "PATCH",
          headers: { Prefer: "return=representation" },
          body: JSON.stringify({
            status: "signed", edition, buyer_email: buyerEmail,
            buyer_name: buyerName, license,
            updated_at: new Date().toISOString(),
          }),
        });
      if ((await rows(r, "store.markSigned")).length !== 1) {
        throw new Error("store.markSigned: row not updated");
      }
    },

    async markIssued(captureId) {
      const r = await req(env,
        `roar_licenses?capture_id=eq.${enc(captureId)}`, {
          method: "PATCH",
          headers: { Prefer: "return=representation" },
          body: JSON.stringify({ status: "issued",
                                 updated_at: new Date().toISOString() }),
        });
      if ((await rows(r, "store.markIssued")).length !== 1) {
        throw new Error("store.markIssued: row not updated");
      }
    },

    async markFailed(captureId, error) {
      try {
        await req(env,
          `roar_licenses?capture_id=eq.${enc(captureId)}`, {
            method: "PATCH",
            headers: { Prefer: "return=minimal" },
            body: JSON.stringify({ status: "failed", error: String(error),
                                   updated_at: new Date().toISOString() }),
          });
      } catch { /* best effort: the 500 retry is the real safety net */ }
    },
  };
}
