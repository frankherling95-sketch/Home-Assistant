# Staartploeg

Projectapp voor de afbouw en inrichting van een nieuwbouwwoning: van koperskeuze-deadlines
en droogstoken tot de bank die twintig weken levertijd heeft.

Mobile-first. Eén HTML-bestand, geen build-afhankelijkheden, werkt op GitHub Pages.

## Structuur

| Pad             | Wat                                                                     |
| --------------- | ----------------------------------------------------------------------- |
| `src/app.html`  | **De bron.** Alleen hier wijzigen.                                       |
| `build.mjs`     | Wikkelt `src/app.html` in een volledig HTML-document.                    |
| `index.html`    | Gegenereerd. Dit is wat GitHub Pages serveert — niet met de hand editen. |
| `docs/`         | Vragenlijst en projectnotities.                                          |

`src/app.html` bevat de marker `<!--HEAD-END-->`: alles ervoor gaat in `<head>`,
alles erna in `<body>`. Datzelfde bestand wordt ook 1-op-1 als Artifact op claude.ai
gepubliceerd, waar de wrapper automatisch wordt toegevoegd.

## Bouwen

```bash
node build.mjs
```

## Status

**v0.3 — werkend.** Ruimte-eerst: de app opent op de kamerlijst. Per ruimte staan de
onderdelen, een moodboard met foto's en materiaalstalen, de winkellinks en een
materiaalcalculator op basis van m2 en omtrek. Daarnaast: de achtstaps werkvolgorde,
een Nu-scherm met besteldeadlines die terugrekenen, en een inkooplijst per winkel.

Gegevens staan in localStorage; foto's in IndexedDB. Nog geen synchronisatie tussen
apparaten — dat is een bewuste keuze (zie de requirements, B11). Export en import van
JSON is de brug naar een gedeelde versie later.

| | |
| --- | --- |
| App | https://claude.ai/code/artifact/d3a4ece3-ec9b-4e91-9423-f7419b0d4365 |
| Requirements | https://claude.ai/code/artifact/5133bd49-1d15-441f-a910-3079ecf5edd4 |
