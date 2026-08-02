// Claim protocol against a stubbed Supabase REST endpoint: a failed row that
// already carries a signed licence must RESUME (re-email the stored licence),
// never sign a second one for the same capture — the ops guide promises the
// retry after an email failure delivers the SAME licence.
import { test } from "node:test";
import assert from "node:assert/strict";
import { storeFactory } from "../lib/supabase.js";

const ENV = { SUPABASE_URL: "https://x.supabase.co", SUPABASE_SERVICE_KEY: "k" };
const LICENSE = { license_id: "ROAR-PRO-AAAA2222", edition: "pro" };

function stubFetch(row, { takeoverWins = true } = {}) {
  const seen = [];
  globalThis.fetch = async (url, init = {}) => {
    seen.push({ url: String(url), method: init.method });
    const body =
      init.method === "POST" ? [] :                    // insert conflict
      init.method === "GET" ? [row] :                  // read existing
      takeoverWins ? [{ ...row, status: "claimed" }] : []; // PATCH takeover
    return { ok: true, json: async () => body };
  };
  return seen;
}

test("failed row WITH stored licence resumes with the same licence", async () => {
  const row = { status: "failed", license: LICENSE,
                buyer_email: "b@example.com", buyer_name: "Ada L",
                updated_at: "2026-08-01T00:00:00Z" };
  const seen = stubFetch(row);
  const claim = await storeFactory(ENV).claim("CAP-1", { edition: "pro" });
  assert.equal(claim.state, "resume");
  assert.deepEqual(claim.license, LICENSE);
  assert.equal(claim.buyerEmail, "b@example.com");
  assert.equal(claim.buyerName, "Ada L");
  assert.ok(seen.some((c) => c.method === "PATCH"), "must still take over");
});

test("failed row WITHOUT a licence re-runs the full path", async () => {
  const row = { status: "failed", license: null, buyer_email: null,
                buyer_name: null, updated_at: "2026-08-01T00:00:00Z" };
  stubFetch(row);
  const claim = await storeFactory(ENV).claim("CAP-2", { edition: "pro" });
  assert.equal(claim.state, "claimed");
});

test("failed row takeover lost means someone else owns it", async () => {
  const row = { status: "failed", license: LICENSE,
                buyer_email: "b@example.com", buyer_name: "Ada L",
                updated_at: "2026-08-01T00:00:00Z" };
  stubFetch(row, { takeoverWins: false });
  const claim = await storeFactory(ENV).claim("CAP-3", { edition: "pro" });
  assert.equal(claim.state, "in-progress");
});
