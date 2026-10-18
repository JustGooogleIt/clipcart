// Runs inside a tab on the ClipCart origin (injected with chrome.scripting.executeScript).
// Its fetches are same-origin requests from ClipCart's own page, so the browser attaches the
// user's existing `cc_owner` cookie and the X-ClipCart-Request header passes without CORS,
// exactly as when the web app uploads. No new endpoint and no cross-origin auth involved.
// Must stay self-contained: executeScript serializes this function without its module scope.

export async function uploadCaptureInPage(payload) {
  const MUTATE = { "X-ClipCart-Request": "1" };
  const fail = async (step, res) => {
    let data = null;
    try {
      data = await res.json();
    } catch {
      /* non-JSON error page */
    }
    return { ok: false, step, status: res.status, code: data?.code ?? "error", message: data?.message ?? res.statusText };
  };
  try {
    // A fresh session keeps the user's current ClipCart session intact; the app's boot
    // call (POST /api/sessions/resume) picks the newest session, which is this one.
    const created = await fetch("/api/sessions", { method: "POST", credentials: "same-origin", headers: MUTATE });
    if (!created.ok) return await fail("session", created);
    const view = await created.json();
    const { id, revision } = view.session;

    const image = await (await fetch(payload.dataUrl)).blob();
    const params = new URLSearchParams({ sessionId: id, expectedRevision: String(revision) });
    if (payload.provenance) {
      if (payload.provenance.sourceUrl) params.set("sourceUrl", payload.provenance.sourceUrl);
      if (payload.provenance.sourceTitle) params.set("sourceTitle", payload.provenance.sourceTitle);
    }
    const uploaded = await fetch(`/api/media/uploads?${params}`, {
      method: "POST",
      credentials: "same-origin",
      headers: { ...MUTATE, "Content-Type": image.type || "image/jpeg" },
      body: image,
    });
    if (!uploaded.ok) return await fail("upload", uploaded);
    const after = await uploaded.json();
    return { ok: true, sessionId: id, mediaId: after.media?.id ?? null, analysisId: after.analysis?.id ?? null };
  } catch (err) {
    return { ok: false, step: "network", status: 0, code: "network", message: String(err?.message ?? err) };
  }
}
