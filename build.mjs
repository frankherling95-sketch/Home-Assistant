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
<meta name="apple-mobile-web-app-title" content="Staartploeg">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='7' fill='%231B49C4'/%3E%3Cpath d='M8 22V10h4.5a3.5 3.5 0 0 1 0 7H8m8 5V10h8' stroke='%23fff' stroke-width='2.4' fill='none' stroke-linecap='round'/%3E%3C/svg%3E">
${head}
</head>
<body>
${body}
</body>
</html>
`;

writeFileSync(new URL("./index.html", import.meta.url), html, "utf8");
console.log(`index.html geschreven (${(html.length / 1024).toFixed(1)} kB)`);
