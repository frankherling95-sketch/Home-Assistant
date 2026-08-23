# Requirements — Staartploeg

Levend document. Groeit met elke interviewronde; ik werk het bij zodra jij antwoordt.

| | |
| --- | --- |
| **Project** | Afbouw en inrichting van een nieuwbouwwoning, oplevering 2027 |
| **Opdrachtgever** | Frank |
| **Laatst bijgewerkt** | 23 augustus 2026 — na interviewronde 1 (vragen uitgezet, antwoorden nog open) |
| **Prototype** | https://claude.ai/code/artifact/d3a4ece3-ec9b-4e91-9423-f7419b0d4365 |

Status per regel: **VAST** = besloten · **VOORSTEL** = mijn invulling, mag omver · **OPEN** = wacht op antwoord.

---

## 1. Waar de app voor is

**VAST** — De app ondersteunt één project: het afbouwen en inrichten van een nieuwbouwwoning.
Niet het bouwen zelf; wel alles daarna en eromheen — keuken, badkamer, vloeren, wanden,
verlichting, meubels, tuin, en de administratie die erbij hoort.

**VAST** — Het is een planning-, registratie-, checklist- en boodschappenlijstinstrument,
aangevuld met beeldmateriaal en opgeslagen winkellinks.

**VAST** — Mobiel is de hoofdvorm. De webversie is dezelfde app op een breder scherm,
geen apart product.

**VOORSTEL** — De app moet drie vragen in vijf seconden beantwoorden:
*Wat moet ik nú doen? Waar staan we? Wat gaat er mis?* Alles wat daar niet aan bijdraagt
is tweede orde.

---

## 2. Het model

**VOORSTEL** — Er is één centraal object: het **onderdeel**. Planning, checklist,
boodschappenlijst, budget en moodboard zijn geen aparte lijsten maar zes vensters op
dezelfde verzameling. Eén keer invoeren, overal zichtbaar.

Een onderdeel heeft:

| Veld | Toelichting |
| --- | --- |
| Naam | "PVC-vloer woonkamer" |
| Ruimte | Woonkamer, Keuken, Hele huis, Tuin, Administratie… |
| Soort | Aanschaf (kopen), klus (doen), of beide |
| Status | Aanschaf: idee → gekozen → offerte → besteld → geleverd → klaar<br>Klus: te doen → ingepland → bezig → klaar |
| Geld | Begroot / geoffreerd / betaald |
| Tijd | Wanneer nodig + levertijd → **uiterste besteldatum wordt berekend, niet ingevoerd** |
| Afhankelijkheid | "Kan pas na …" |
| Beeld | Foto's, screenshots, kleur- en materiaalstalen |
| Links | Webshop, offerte, productpagina |
| Notitie | Vrij veld |

De zes vensters:

1. **Nu** — alleen wat deze week moet. Openingsscherm.
2. **Ruimtes** — gegroepeerd per kamer, met voortgang en budget.
3. **Inkoop** — wat besteld of gehaald moet worden, gegroepeerd per winkel.
4. **Beeld** — foto's, kleuren en materialen per ruimte, met winkellinks.
5. **Planning** — tijdlijn met afhankelijkheden en kritiek pad.
6. **Budget** — begroot naast geoffreerd naast betaald.

**VOORSTEL** — Naast onderdelen bestaat een tweede, veel lichter type: het
**bouwmarktlijstje**. Kit, schuurpapier, verlengsnoer. Geen status, geen budget, geen
planning — alleen snel toevoegen en afvinken in de winkel. Twee soorten boodschappen die
niet door elkaar moeten lopen.

---

## 3. Functionele requirements

### Registratie

| # | Requirement | Status |
| --- | --- | --- |
| F1 | Onderdeel toevoegen met minimaal een naam; alle andere velden mogen later | VOORSTEL |
| F2 | Toevoegen moet binnen enkele seconden kunnen, staand, met één hand | VOORSTEL |
| F3 | Status wijzigen in één tik vanuit elke lijst | VOORSTEL |
| F4 | Onderdelen groeperen per ruimte; ruimtes zelf benoemen | VOORSTEL |
| F5 | Vrije notities per onderdeel | VOORSTEL |

### Planning en deadlines

| # | Requirement | Status |
| --- | --- | --- |
| F6 | Terugrekenen: nodig-op-datum minus levertijd = uiterste besteldatum, automatisch | VOORSTEL |
| F7 | Afhankelijkheden tussen onderdelen; schuift er één, dan schuift de rest zichtbaar mee | VOORSTEL |
| F8 | Kritiek pad zichtbaar maken | VOORSTEL |
| F9 | Aparte, harde categorie voor koperskeuze-deadlines van de aannemer | VOORSTEL |
| F10 | Waarschuwen ruim vóór een deadline, niet erna | VOORSTEL |
| F11 | Beslissingen met een uiterste beslisdatum ("bank kiezen vóór 3 maart") | VOORSTEL |
| F12 | Hoe de waarschuwing binnenkomt: push, e-mail, agenda of alleen in de app | OPEN → B6 |

### Checklist en boodschappen

| # | Requirement | Status |
| --- | --- | --- |
| F13 | Inkooplijst: alles wat besteld moet worden, gegroepeerd per leverancier | VOORSTEL |
| F14 | Bouwmarktlijstje: los, snel toevoegen, afvinken | VOORSTEL |
| F15 | Klussenchecklist per ruimte, afvinkbaar | VOORSTEL |
| F16 | Standaard checklists om over te nemen (verhuizen, nutsvoorzieningen, verzekeringen) | VOORSTEL |

### Beeld en links

| # | Requirement | Status |
| --- | --- | --- |
| F17 | Foto's toevoegen vanuit camera of galerij, gekoppeld aan ruimte of onderdeel | VOORSTEL |
| F18 | Moodboard per ruimte: foto's, screenshots, kleur- en materiaalstalen naast elkaar | VOORSTEL |
| F19 | Links opslaan bij een onderdeel of ruimte (webshop, productpagina, offerte) | VOORSTEL |
| F20 | Waar een link "landt" — bij ruimte, bij onderdeel, of in één bak met labels | OPEN → B5 |
| F21 | Twee opties naast elkaar kunnen leggen om te vergelijken | OPEN → B5 |
| F22 | Documenten koppelen (offerte, factuur, garantie) of alleen naar Drive linken | OPEN |

### Geld

| # | Requirement | Status |
| --- | --- | --- |
| F23 | Begroot, geoffreerd en betaald per onderdeel en per ruimte | VOORSTEL |
| F24 | Totaal versus budget, met wat er nog te gaan is | VOORSTEL |
| F25 | Cashflow: wanneer moet welk bedrag betaald zijn | VOORSTEL |

---

## 4. Niet-functioneel

| # | Requirement | Status |
| --- | --- | --- |
| N1 | Mobile-first; ontworpen op 375 px, verbreedt naar desktop | VAST |
| N2 | Te openen via een URL, installeerbaar op het beginscherm | VOORSTEL |
| N3 | Bruikbaar met stoffige handen: grote raakvlakken, weinig typewerk | VOORSTEL |
| N4 | Werkt zonder internet in een lege woning | OPEN → B4 |
| N5 | Samen gebruiken met partner, inclusief synchronisatie | OPEN → B3 |
| N6 | Gegevens exporteerbaar; geen opsluiting in één app | VOORSTEL |
| N7 | Afscherming: publiek bereikbaar of niet | OPEN |
| N8 | Voorlopig gehost op GitHub Pages, later eventueel eigen domein | VAST |
| N9 | Donkere en lichte modus, contrast op AA-niveau | VAST |

---

## 5. Open beslissingen

| # | Vraag | Blokkeert |
| --- | --- | --- |
| B1 | Wanneer pak je de app erbij — plannend op de bank, of staand in de winkel? | Het openingsscherm |
| B2 | Waar houd je het nu bij en wat werkt daar niet? | Wat de app moet vervangen |
| B3 | Gebruikt je partner de app ook? | N5, hele opslagarchitectuur |
| B4 | Moet het zonder internet werken? | N4, opslagkeuze |
| B5 | Waar komen beeld en links vandaan, en wil je vergelijken? | F18–F21 |
| B6 | Hoe wil je gewaarschuwd worden? | F12 |
| B7 | Wanneer is de oplevering en hoeveel speling zit er? | Alle datumberekeningen |
| B8 | Wat doet de aannemer wel en niet? | De hele inhoud van de lijst |
| B9 | Ligt er vloerverwarming? | Kritiek pad rond droogstoken en vloer |

---

## 6. Interviewlog

### Ronde 0 — uitgangspunten (23 aug 2026)

Vastgesteld uit het gesprek:

- Het gaat om afbouw en inrichting, niet om de bouw zelf.
- Web én mobiel, met de nadruk op mobiel.
- Ontwikkeling gebeurt grotendeels vanaf de telefoon; validatie via een online URL.
- GitHub Pages nu, eigen domein mogelijk later — patroon uit een eerder project.
- De vragenlijst is een hulpmiddel voor requirements, **geen** functionaliteit van de app.
- Gewenste kern: planning, registratie, boodschappenlijst, checklist, moodboard en links.

### Ronde 1 — hoe je de app gaat gebruiken (uitgezet 23 aug 2026)

Vragen B1 t/m B6 staan uit. Antwoorden komen hier.

### Ronde 2 — het project zelf (nog niet gestart)

Vragen B7 t/m B9 plus de projectinventarisatie per ruimte.
