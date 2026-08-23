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

**v0.1 — intake.** De app verzamelt nu de projectgegevens en de scope-keuzes.
Zodra de intake ingevuld is, wordt dit een echte projecttracker: ruimtes, taken,
budget, levertijden en deadlines.

Gegevens staan in `localStorage` op het apparaat zelf. Nog geen synchronisatie
tussen telefoon en laptop — dat is een expliciete keuze in de intake (blok I).
