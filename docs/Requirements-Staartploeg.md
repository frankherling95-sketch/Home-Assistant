# Requirements — Staartploeg

Levend document. Groeit met elke interviewronde; ik werk het bij zodra jij antwoordt.

| | |
| --- | --- |
| **Project** | Afbouw en inrichting van een nieuwbouwwoning, oplevering 2027 |
| **Opdrachtgever** | Frank |
| **Laatst bijgewerkt** | 23 augustus 2026 — na interviewronde 1 |
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

**VAST** — De app vervangt de huidige werkwijze in Google Drive en Excel. Dat is het
ijkpunt: als iets in de app omslachtiger is dan in Excel, is het ontwerp fout.

**VOORSTEL** — De app moet drie vragen in vijf seconden beantwoorden:
*Wat moet ik nú doen? Waar staan we? Wat gaat er mis?*

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
| Wie | Wie het heeft toegevoegd of gewijzigd — nodig nu er twee mensen in werken |

De zes vensters:

1. **Nu** — alleen wat deze week moet. Openingsscherm.
2. **Ruimtes** — gegroepeerd per kamer, met voortgang en budget.
3. **Inkoop** — wat besteld of gehaald moet worden, gegroepeerd per winkel.
4. **Beeld** — foto's, kleuren en materialen per ruimte, met winkellinks.
5. **Planning** — tijdlijn met afhankelijkheden en kritiek pad.
6. **Budget** — begroot naast geoffreerd naast betaald.

**VOORSTEL** — Naast onderdelen bestaat een tweede, veel lichter type: het
**bouwmarktlijstje**. Kit, schuurpapier, verlengsnoer. Geen status, geen budget, geen
planning — alleen snel toevoegen en afvinken in de winkel.

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
| F26 | Zoeken over alles — ook staand in een winkel bruikbaar | VAST |

### Planning en deadlines

| # | Requirement | Status |
| --- | --- | --- |
| F6 | Terugrekenen: nodig-op-datum minus levertijd = uiterste besteldatum, automatisch | VOORSTEL |
| F7 | Afhankelijkheden tussen onderdelen; schuift er één, dan schuift de rest zichtbaar mee | VOORSTEL |
| F8 | Kritiek pad zichtbaar maken | VOORSTEL |
| F9 | Aparte, harde categorie voor koperskeuze-deadlines van de aannemer | VOORSTEL |
| F10 | Waarschuwen ruim vóór een deadline, niet erna | VOORSTEL |
| F11 | Beslissingen met een uiterste beslisdatum ("bank kiezen vóór 3 maart") | VOORSTEL |
| F12 | Vorm van de waarschuwing: push, e-mail, agenda of alleen in de app | UITGESTELD |

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
| F17 | Foto's toevoegen vanuit camera of galerij | VAST |
| F18 | Moodboard per ruimte: foto's, screenshots, kleur- en materiaalstalen naast elkaar | VAST |
| F19 | Links opslaan (webshop, productpagina, offerte, Pinterest) | VAST |
| F20 | Waar beeld en link landen bij het opslaan | OPEN → B12 |
| F21 | Twee opties naast elkaar leggen om te kiezen | VOORSTEL |
| F22 | Documenten koppelen (offerte, factuur, garantie) of naar Drive linken | VOORSTEL |

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
| N4 | ~~Offline werken~~ — **niet nodig**, er is altijd bereik | VAST |
| N5 | Twee gebruikers: Frank en partner, allebei lezen én schrijven | VAST |
| N6 | Wijzigingen van de één zijn zichtbaar bij de ander | VAST |
| N7 | Gegevens exporteerbaar; geen opsluiting in één app | VOORSTEL |
| N8 | Afscherming: publiek bereikbaar of niet | OPEN |
| N9 | Voorlopig GitHub Pages, later eventueel eigen domein | VAST |
| N10 | Donkere en lichte modus, contrast op AA-niveau | VAST |
| N11 | Waar de gegevens wonen | OPEN → B11 |

---

## 5. Open beslissingen

| # | Vraag | Blokkeert |
| --- | --- | --- |
| ~~B1~~ | ~~Wanneer pak je de app erbij?~~ → beide momenten, zie B10 | — |
| ~~B2~~ | ~~Waar houd je het nu bij?~~ → Drive en Excel | — |
| ~~B3~~ | ~~Doet je partner mee?~~ → ja, volwaardig | — |
| ~~B4~~ | ~~Offline nodig?~~ → nee, altijd bereik | — |
| ~~B5~~ | ~~Waar komt beeld vandaan?~~ → alles: eigen foto's, screenshots, Pinterest | — |
| ~~B6~~ | ~~Hoe gewaarschuwd worden?~~ → later beslissen | F12 |
| **B10** | Hoe opent de app, gegeven dat je 'm zowel plannend als onderweg gebruikt | Het openingsscherm |
| **B11** | Waar de gegevens wonen, nu er twee mensen in werken | N11, hele architectuur |
| **B12** | Waar beeld en links landen op het moment dat je ze opslaat | F20 |
| **B13** | Welk venster ik als eerste echt afbouw | Bouwvolgorde |
| B7 | Wanneer is de oplevering en hoeveel speling zit er? | Alle datumberekeningen |
| B8 | Wat doet de aannemer wel en niet? | De inhoud van de lijst |
| B9 | Ligt er vloerverwarming? | Kritiek pad rond droogstoken en vloer |

---

## 6. Gevolgen van ronde 1

**Twee antwoorden veranderen de opzet:**

*Partner doet volwaardig mee (N5) + altijd bereik (N4).* Samen betekent dat de gegevens
niet meer op één telefoon kunnen staan. Er moet een centrale plek komen waar beide
telefoons naartoe schrijven. Dat "altijd bereik" is daarbij goed nieuws: het maakt de
ingewikkeldste variant — offline werken en later samenvoegen, inclusief het oplossen van
conflicten — overbodig. Dat scheelt fors in complexiteit.

Het gevolg is wel dat GitHub Pages alleen niet volstaat. Pages serveert statische
bestanden en kan niets opslaan. Er moet iets naast. Dat is beslissing **B11**.

*Nu al in Drive en Excel.* Dat is geen detail maar de meetlat. Als een handeling in de
app meer tikken kost dan in Excel, gaat hij het niet halen. Het pleit er ook voor om
Drive niet weg te duwen: documenten en offertes mogen daar blijven wonen, met een
verwijzing vanuit de app.

---

## 7. Interviewlog

### Ronde 0 — uitgangspunten (23 aug 2026)

- Het gaat om afbouw en inrichting, niet om de bouw zelf.
- Web én mobiel, met de nadruk op mobiel.
- Ontwikkeling gebeurt grotendeels vanaf de telefoon; validatie via een online URL.
- GitHub Pages nu, eigen domein mogelijk later.
- De vragenlijst is een hulpmiddel voor requirements, **geen** functionaliteit van de app.
- Gewenste kern: planning, registratie, boodschappenlijst, checklist, moodboard en links.

### Ronde 1 — hoe je de app gaat gebruiken (23 aug 2026)

| Vraag | Antwoord |
| --- | --- |
| Wanneer pak je 'm erbij? | Beide: plannend én onderweg |
| Waar houd je het nu bij? | Google Drive en Excel |
| Doet je partner mee? | Ja, volwaardig |
| Offline nodig? | Nee, altijd bereik |
| Waar komt beeld vandaan? | Combinatie van alles |
| Hoe gewaarschuwd worden? | Later beslissen |

**Over de werkwijze:** vanaf nu keuzevragen met concrete opties in plaats van open
vragen. Sneller te beantwoorden en het dwingt mij scherpere voorstellen te doen.

### Ronde 2 — de vier keuzes (uitgezet 23 aug 2026)

B10 openingsscherm · B11 opslag · B12 beeld en links · B13 bouwvolgorde.

### Ronde 3 — het project zelf (nog niet gestart)

B7 t/m B9 plus de inventarisatie per ruimte.
