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

**v0.7 — live.** De app draait op GitHub Pages en is installeerbaar op je beginscherm.
Delen vanuit een webshop komt binnen als link bij een ruimte naar keuze.

Gegevens staan in localStorage; fotos in IndexedDB. Nog geen synchronisatie tussen
apparaten — bewuste keuze, zie de requirements (B11). Export en import van JSON is de
brug naar een gedeelde versie later.

| | |
| --- | --- |
| Live | https://frankherling95-sketch.github.io/staartploeg/ |
| Voorbeeld op claude.ai | https://claude.ai/code/artifact/d3a4ece3-ec9b-4e91-9423-f7419b0d4365 |
| Requirements | https://claude.ai/code/artifact/5133bd49-1d15-441f-a910-3079ecf5edd4 |

## Iconen

```bash
node tools/maak-iconen.mjs
```
