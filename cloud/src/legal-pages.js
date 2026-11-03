// The public pages (home, privacy policy, terms) live on the ZunimiLabs website. The cloud only sends visitors there,
// so old links (and the app's links) keep working.
const SITE = "https://zunimilabs.online";
const REDIRECTS = {
  "/": SITE + "/chatdoom/",
  "/privacy": SITE + "/chatdoom/privacy/",
  "/terms": SITE + "/chatdoom/terms/",
};

export function handlePublicPage(request, url) {
  if (request.method !== "GET" && request.method !== "HEAD") return null;
  const to = REDIRECTS[url.pathname];
  return to ? Response.redirect(to, 301) : null;
}
