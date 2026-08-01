// Idempotency + issued-licence ledger on Supabase (plain REST, no SDK).
//
// Table (create once; see docs/VERCEL_FULFILLMENT.md):
//   create table roar_licenses (
//     capture_id text primary key,
//     status text not null default 'claimed',   -- claimed|issued|failed
//     edition text,
//     buyer_email text,
//     buyer_name text,
//     license jsonb,
//     error text,
//     created_at timestamptz default now(),
//     updated_at timestamptz default now()
//   );
// RLS ON with no policies: only the service key (used here) can touch it.

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

export function storeFactory(env) {
  return {
    // Claim BEFORE signing. Returns "claimed" | "already-issued".
    // A previously-failed claim is re-claimed so PayPal retries can complete
    // it; an issued one is final.
    async claim(captureId, { edition }) {
      const insert = await req(env, "roar_licenses", {
        method: "POST",
        headers: { Prefer: "resolution=ignore-duplicates,return=minimal" },
        body: JSON.stringify([{ capture_id: captureId, edition,
                                status: "claimed" }]),
      });
      if (!insert.ok) throw new Error(`store.claim: HTTP ${insert.status}`);
      const rows = await (await req(env,
        `roar_licenses?capture_id=eq.${encodeURIComponent(captureId)}`
        + "&select=status", { method: "GET" })).json();
      const status = rows[0]?.status;
      return status === "issued" ? "already-issued" : "claimed";
    },

    async markIssued(captureId, { edition, buyerEmail, buyerName, license }) {
      const r = await req(env,
        `roar_licenses?capture_id=eq.${encodeURIComponent(captureId)}`, {
          method: "PATCH",
          headers: { Prefer: "return=minimal" },
          body: JSON.stringify({
            status: "issued", edition, buyer_email: buyerEmail,
            buyer_name: buyerName, license,
            updated_at: new Date().toISOString(),
          }),
        });
      if (!r.ok) throw new Error(`store.markIssued: HTTP ${r.status}`);
    },

    async markFailed(captureId, error) {
      await req(env,
        `roar_licenses?capture_id=eq.${encodeURIComponent(captureId)}`, {
          method: "PATCH",
          headers: { Prefer: "return=minimal" },
          body: JSON.stringify({ status: "failed", error,
                                 updated_at: new Date().toISOString() }),
        });
    },
  };
}
