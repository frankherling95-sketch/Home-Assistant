// Bouwt src/app.html om naar een volledige index.html voor GitHub Pages.
// Hetzelfde bronbestand wordt ook 1-op-1 als Artifact gepubliceerd,
// waar claude.ai de <head>/<body> zelf omheen zet.
//
//   node build.mjs
//
import { readFileSync, writeFileSync } from "node:fs";

const src = readFileSync(new URL("./src/app.html", import.meta.url), "utf8");
const marker = "<!--HEAD-END-->";
const i = src.indexOf(marker);
if (i === -1) throw new Error("Marker <!--HEAD-END--> ontbreekt in src/app.html");

const head = src.slice(0, i).trim();
const body = src.slice(i + marker.length).trim();

const html = `<!doctype html>
<html lang="nl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="description" content="Projectapp voor de afbouw en inrichting van een nieuwbouwwoning.">
<meta name="theme-color" content="#EDEDE8" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#101317" media="(prefers-color-scheme: dark)">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Staartploeg">
<link rel="manifest" href="manifest.webmanifest">
<link rel="icon" href="icons/icoon-192.png" type="image/png">
<link rel="apple-touch-icon" href="icons/icoon-180.png">
${head}
</head>
<body>
${body}
<script>
// Alleen op een echte site; in de Artifact-weergave bestaat sw.js niet.
if ("serviceWorker" in navigator && location.protocol.startsWith("http")) {
  addEventListener("load", function () {
    navigator.serviceWorker.register("sw.js").catch(function () {});
  });
}
</script>
</body>
</html>
`;

writeFileSync(new URL("./index.html", import.meta.url), html, "utf8");
console.log(`index.html geschreven (${(html.length / 1024).toFixed(1)} kB)`);
