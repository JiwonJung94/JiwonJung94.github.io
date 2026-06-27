const ORIGIN = "https://jiwonjung94.github.io";
const ok = s => /^[a-z0-9_-]+$/i.test(s);
const okLang = s => /^[a-z]{2,5}$/i.test(s);

export default {
  async fetch(req, env) {
    const u = new URL(req.url);
    const book = u.searchParams.get("book") || "";
    const slug = u.searchParams.get("slug") || "";
    const lang = u.searchParams.get("lang") || "";
    const locales = (u.searchParams.get("locales") || "").split(",").filter(okLang);
    const cors = { "Access-Control-Allow-Origin": ORIGIN,
                   "content-type": "application/json", "cache-control": "no-store" };
    if (!ok(book) || (slug && !ok(slug)))
      return new Response("{}", { status: 400, headers: cors });

    const from = req.headers.get("Origin") || req.headers.get("Referer") || "";
    const hit = u.searchParams.get("hit") === "1" && from.startsWith(ORIGIN);

    if (hit && slug && okLang(lang)) {
      const pKey = "v:" + book + ":" + lang + ":" + slug;
      const n = parseInt((await env.VIEWS.get(pKey)) || "0", 10) + 1;
      await env.VIEWS.put(pKey, String(n), { metadata: { n } });
      const tKey = "t:" + book;
      const t = parseInt((await env.VIEWS.get(tKey)) || "0", 10) + 1;
      await env.VIEWS.put(tKey, String(t));
    } else if (hit && !slug) {
      const tKey = "t:" + book;
      const t = parseInt((await env.VIEWS.get(tKey)) || "0", 10) + 1;
      await env.VIEWS.put(tKey, String(t));
    }

    const out = { book: parseInt((await env.VIEWS.get("t:" + book)) || "0", 10) };
    if (slug && locales.length) {
      let page = 0;
      for (const L of locales)
        page += parseInt((await env.VIEWS.get("v:" + book + ":" + L + ":" + slug)) || "0", 10);
      out.page = page;
    }
    return new Response(JSON.stringify(out), { headers: cors });
  },
};
