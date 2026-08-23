# Requirements — Staartploeg

Levend document. Groeit met elke interviewronde; ik werk het bij zodra jij antwoordt.

| | |
| --- | --- |
| **Project** | Afbouw en inrichting van een nieuwbouwwoning, oplevering 2027 |
| **Opdrachtgever** | Frank |
| **Laatst bijgewerkt** | 23 augustus 2026 — na v0.7, live op GitHub Pages |
| **App** | https://frankherling95-sketch.github.io/staartploeg/ |

Status per regel: **GEBOUWD** = zit in de app · **VAST** = besloten, nog te bouwen ·
**VOORSTEL** = mijn invulling, mag omver · **OPEN** = wacht op antwoord.

Sectie 8 onderaan bevat de testbevindingen en het domeinonderzoek.

---

## 1. Waar de app voor is

**VAST** — De app ondersteunt één project: het afbouwen en inrichten van een nieuwbouwwoning.
Niet het bouwen zelf; wel alles daarna — keuken, badkamer, vloeren, wanden, verlichting,
meubels, tuin, en de administratie eromheen.

**VAST** — Mobiel is de hoofdvorm. De webversie is dezelfde app op een breder scherm.

**VAST** — De app vervangt de huidige werkwijze in Google Drive en Excel. Dat is de meetlat:
als iets in de app meer handelingen kost dan in Excel, is het ontwerp fout.

**VAST** — De **ruimte** is het organiserende principe. Frank denkt in kamers, niet in
deadlines: de app opent op ruimtes, beeld hangt aan een ruimte, en ruimtes waren het eerste
dat gebouwd is.

## 1b. Waar het op moet lijken

Frank noemde vijf bestaande gereedschappen. De app moet daar één ding van worden:

| Bron | Wat we ervan overnemen | Status |
| --- | --- | --- |
| **Milanote** | Visueel bord per kamer: foto's, tegels, kleurcodes, productlinks en afmetingen bij elkaar, om combinaties te zien vóór je bestelt | GEBOUWD |
| **Notion** | Tabel per kamer met Product, Ruimte, Link/Artikelnummer, Afmetingen, Prijs, Status | GEBOUWD |
| **Houzz / Pinterest** | Verzamelen en vergelijken: meerdere opties naast elkaar, er één kiezen | GEBOUWD — alleen automatisch importeren vanuit een webshop nog niet |
| **Kluswijzers (Gamma, Praxis, Hornbach)** | Materiaalberekening per m²: voorstrijk, tegellijm, voegmortel, egaline | GEBOUWD |
| **Klusidee** | Antwoorden op specifieke klusvragen | Niet ingebouwd; blijft een link |

---

## 2. Het model

**GEBOUWD** — Er is één centraal object: het **onderdeel**. Alle schermen zijn vensters op
dezelfde verzameling. Eén keer invoeren, overal zichtbaar.

| Veld | Toelichting |
| --- | --- |
| Naam | "PVC-vloer woonkamer" |
| Ruimte | Zelf te benoemen |
| Soort | Kopen, klus, of allebei |
| Status | Kopen: Te kiezen → Gekozen → Besteld → Geleverd op bouw → Gemonteerd<br>Klus: Te doen → Ingepland → Bezig → Klaar |
| Stap | Welke van de acht stappen in de werkvolgorde |
| Afmetingen | Vrij veld: "240 × 90 × 45 cm" of "18,5 m²" |
| Winkel | Leverancier |
| Artikelnummer | Om in de winkel terug te vinden |
| Geld | Begroot en betaald |
| Tijd | Nodig op (datum) + levertijd → **uiterste besteldatum wordt berekend** |
| Notitie | Vrij veld |
| Links | Webshop, productpagina, offerte |

**GEBOUWD** — Losstaand daarvan: het **bouwmarktlijstje**. Kit, voorstrijk, verlengsnoer.
Geen status, geen budget, geen planning — snel toevoegen en afvinken in de winkel.

**GEBOUWD** — Beeld hangt aan een **ruimte**: foto's (camera of galerij) en kleur- of
materiaalstalen, met de winkellinks van die ruimte ernaast.

**GEBOUWD** — "Nodig op" is een **gewone datum**. Verschuift de opleverdatum, dan vraagt de
app of alle datums evenveel mee moeten schuiven. Eerder werd dit relatief aan de sleutel
opgeslagen; dat wierp datums weg zolang er nog geen sleuteldatum was, en stilzwijgend
verplaatsen bleek erger dan een vraag stellen.

## 2b. De werkvolgorde

**VAST** — De acht stappen, in deze volgorde. Stof, vocht en zware werkzaamheden bepalen de
volgorde; wie de vloer te vroeg legt, legt hem twee keer.

1. Voorbereiding, ruwbouw & leidingwerk — *voordat er ook maar iets wordt afgewerkt*
2. Waterdichting & natte voorbereiding — *essentieel voor de badkamer*
3. Stucwerk & wandafwerking (droge ruimtes) — *vóórdat de vloeren erin gaan*
4. Tegelwerk & voegen — *badkamer, toilet en eventuele tegelvloeren*
5. Schilderwerk & spuiten — *wanden en plafonds afwerken*
6. Vloeren leggen (woon- en slaapkamers) — *pas als al het zware en natte werk klaar is*
7. Montage & installatie — *keuken, binnendeuren en sanitair*
8. Afkitten & fijnafwerking — *de laatste stap*

---

## 3. Functionele requirements

### Registratie

| # | Requirement | Status |
| --- | --- | --- |
| F1 | Onderdeel toevoegen met minimaal een naam | GEBOUWD |
| F2 | Toevoegen in enkele seconden, met één hand | GEBOUWD |
| F3 | Status wijzigen in één tik | GEBOUWD |
| F4 | Groeperen per ruimte, ruimtes zelf benoemen | GEBOUWD |
| F5 | Vrije notities, afmetingen en artikelnummer | GEBOUWD |
| F26 | Zoeken over naam, winkel, artikelnummer, maten en notities | GEBOUWD |

### Planning en deadlines

| # | Requirement | Status |
| --- | --- | --- |
| F6 | Terugrekenen: nodig-op minus levertijd = uiterste besteldatum | GEBOUWD |
| F27 | Werkvolgorde in acht stappen, met onderdelen per stap | GEBOUWD |
| F28 | Automatisch tonen welke stap nu aan de beurt is | GEBOUWD |
| F7 | Afhankelijkheden tussen individuele onderdelen | VOORSTEL |
| F9 | Aparte, harde categorie voor koperskeuze-deadlines | GEBOUWD |
| F11 | Beslissingen met een uiterste beslisdatum | VAST |
| F12 | Vorm van de waarschuwing: push, e-mail, agenda of in de app | UITGESTELD |

### Checklist, boodschappen en materiaal

| # | Requirement | Status |
| --- | --- | --- |
| F13 | Inkooplijst gegroepeerd per winkel | GEBOUWD |
| F14 | Bouwmarktlijstje: los, snel toevoegen, afvinken | GEBOUWD |
| F29 | Materiaalcalculator per ruimte op basis van m² en omtrek | GEBOUWD |
| F30 | Berekend materiaal in één tik naar het bouwmarktlijstje | GEBOUWD |
| F16 | Standaard checklists (verhuizen, nutsvoorzieningen, verzekeringen) | VOORSTEL |

### Beeld en links

| # | Requirement | Status |
| --- | --- | --- |
| F17 | Foto's toevoegen vanuit camera of galerij, automatisch verkleind | GEBOUWD |
| F18 | Moodboard per ruimte: foto's en kleur-/materiaalstalen | GEBOUWD |
| F19 | Links opslaan bij ruimte én bij onderdeel | GEBOUWD |
| F31 | Vrij sleepbaar bord per ruimte, met foto's, stalen en notities | GEBOUWD |
| F32 | Eigen kleur kiezen bij een staal, met snelkeuzes | GEBOUWD |
| F21 | Opties naast elkaar leggen en er één kiezen; de keuze vult prijs, winkel en link | GEBOUWD |
| F33 | Delen vanuit een webshop rechtstreeks de app in | GEBOUWD |
| F22 | Documenten koppelen of naar Drive linken | VOORSTEL |

### Geld

| # | Requirement | Status |
| --- | --- | --- |
| F23 | Begroot en betaald per onderdeel en per ruimte | GEBOUWD |
| F24 | Totaal versus budget | GEBOUWD |
| F25 | Cashflow: wanneer moet welk bedrag betaald zijn | VOORSTEL |

---

## 4. Niet-functioneel

| # | Requirement | Status |
| --- | --- | --- |
| N1 | Mobile-first, ontworpen op 375 px | GEBOUWD |
| N4 | ~~Offline werken~~ — niet nodig, er is altijd bereik | VERVALLEN |
| N7 | Gegevens exporteerbaar als JSON, en terug te zetten | GEBOUWD |
| N10 | Donkere en lichte modus, contrast op AA-niveau | GEBOUWD |
| N2 | Installeerbaar op het beginscherm | GEBOUWD |
| N5 | Twee gebruikers, allebei lezen en schrijven | VAST, uitgesteld |
| N6 | Wijzigingen van de één zichtbaar bij de ander | VAST, uitgesteld |
| N9 | GitHub Pages, later eventueel eigen domein | GEBOUWD — https://frankherling95-sketch.github.io/staartploeg/ |
| N8 | Afscherming | BESLOTEN — openbare repo en publieke site; projectgegevens blijven in de browser |
| N11 | Waar de gedeelde gegevens gaan wonen | UITGESTELD → B11 |

---

## 5. Open beslissingen

| # | Vraag | Blokkeert |
| --- | --- | --- |
| B11 | Waar de gegevens wonen zodra jullie samen gaan werken | N5, N6 |
| B7 | Wanneer is de oplevering en hoeveel speling zit er? | Alle datumberekeningen |
| B8 | Wat doet de aannemer wel en niet? | De inhoud van de lijst |
| B9 | Ligt er vloerverwarming? | Kritiek pad rond droogstoken en vloer |
| B14 | Moet de materiaalcalculator per klus vragen wát je doet, of alles tonen met een voorbehoud? | F29 |

Afgehandeld: B1 t/m B6 (ronde 1), B10 t/m B13 (ronde 2).

---

## 6. Interviewlog

### Ronde 0 — uitgangspunten (23 aug 2026)

Afbouw en inrichting, niet de bouw zelf. Web én mobiel, nadruk op mobiel. Ontwikkeling
vanaf de telefoon, validatie via een online URL. GitHub Pages nu, eigen domein later.
De vragenlijst is gereedschap voor requirements, geen functionaliteit.

### Ronde 1 — hoe je de app gebruikt (23 aug 2026)

| Vraag | Antwoord |
| --- | --- |
| Wanneer pak je 'm erbij? | Beide: plannend én onderweg |
| Waar houd je het nu bij? | Google Drive en Excel |
| Doet je partner mee? | Ja, volwaardig |
| Offline nodig? | Nee, altijd bereik |
| Waar komt beeld vandaan? | Combinatie van alles |
| Hoe gewaarschuwd worden? | Later beslissen |

**Over de werkwijze:** vanaf nu keuzevragen met concrete opties in plaats van open vragen.

### Ronde 2 — vier keuzes (23 aug 2026)

| Keuze | Antwoord | Gevolg |
| --- | --- | --- |
| Startscherm | Ruimtes eerst | App opent op de kamerlijst; zoeken zit in de kop |
| Opslag | Eerst alleen jij | localStorage nu; export/import als brug naar later |
| Beeld en links | Meteen aan een ruimte | Geen inbox; beeld hoort direct bij een kamer |
| Eerst bouwen | Invoeren + Ruimtes | v0.3 |

**Aanvulling van Frank:** de app moet een combinatie worden van Milanote, Notion,
Houzz/Pinterest, de Kluswijzers van de bouwmarkten en Klusidee — plus de achtstaps
werkvolgorde. Zie 1b en 2b.

### Ronde 3 — het project zelf (nog niet gestart)

B7 t/m B9 plus de inventarisatie per ruimte.

---

## 8. Testronde en onderzoek (23 aug 2026)

### Gevonden en opgelost

| # | Wat er misging | Ernst |
| --- | --- | --- |
| 1 | `prompt()` en `confirm()` worden in een ingesloten frame geblokkeerd — links, kleurstalen en verwijderen deden dan niets, zonder foutmelding | Blokkerend op mobiel |
| 2 | "Nodig op"-datum werd bij opslaan weggegooid als er nog geen sleuteldatum was | Stil dataverlies |
| 3 | Terug in plaats van Opslaan liet wijzigingen op het scherm staan die niet bewaard waren | Verwarrend |
| 4 | "Kopen én doen" kon nooit de status Ingepland krijgen | Ontwerpgat |
| 5 | Negatieve bedragen en levertijd 999 werden geaccepteerd | Rekenfouten |
| 6 | Kleurstaal kreeg een willekeurige kleur uit een vaste reeks | Functioneel gat |
| 7 | `dagenTot` telde een half etmaal mee: elke teller stond een dag te hoog | Rekenfout |

Datums zijn nu gewone datums in plaats van weken-na-sleutel. Verschuift de
opleverdatum, dan vraagt de app expliciet of alles mee moet schuiven.

### Wat het domeinonderzoek opleverde

- Er zit een **voorschouw** ongeveer twee weken vóór de oplevering.
- Een opleverpunt is alleen afdwingbaar als het **concreet** is: ruimte, plek, aard, omvang, foto.
- Onder de Wkb moet de aannemer schriftelijk wijzen op het **5%-opschortingsrecht**; daarna geldt een onderhoudstermijn van zes maanden en op de meeste technische onderdelen zes jaar garantie.
- **Bouwvocht** kan tot twee jaar duren; stucwerk drogen duurt één tot drie weken, vuistregel één dag per millimeter. Forceren geeft scheuren.
- Elke bouwfase heeft een eigen **sluitingsdatum** voor koperskeuzes; daarna zijn technische wijzigingen onmogelijk. Extra stopcontacten kosten €150–300 via meerwerk.
- Kopers vergeten structureel **verlichting** te begroten; gemiddeld gaat er zo'n €25.000 naar inrichting.
- De **financieringsvergoeding** van 4–8% vóór hypotheekpassering kost duizenden euro's die kopers niet hadden verwacht.
- Houd een **buffer** aan: schuivende opleverdata leiden tot spoedleveringen tegen hogere prijzen.

### Ronde 3 — vier richtingskeuzes

| Keuze | Antwoord |
| --- | --- |
| Eerste app-functie | Kluswijzer-stappenplannen |
| Koperskeuzes | Eigen module, met voorrang |
| Oplevering | Volledige module inclusief termijnen |
| Toon van de app | Actief meedenken |

Alle vier gebouwd in v0.5.

### Nog niet gebouwd

Delen vanuit een webshop rechtstreeks de app in (vraagt om installatie als PWA),
synchronisatie tussen twee telefoons, cashflow-kalender, afhankelijkheden tussen
individuele onderdelen, standaard checklists voor verhuizen en nutsvoorzieningen.

### v0.6 (23 aug 2026)

Moodboard is nu een echt bord: foto's, kleurstalen en notities die je vrij versleept,
met een rasterweergave als alternatief. Opties vergelijken per onderdeel; de gekozen
optie vult prijs, winkel en link en zet de status op Gekozen. Tabelweergave over alle
onderdelen met sorteren per kolom.

Twee bugs gevonden tijdens deze bouw: nieuwe bordtegels stapelden allemaal op dezelfde
plek, en de tabelstijlen bleken bij de v0.3-herbouw verwijderd, waardoor de tabel
ongestyled rendeerde.

### v0.7 (23 aug 2026)

Live op GitHub Pages, installeerbaar op het beginscherm, en een share target:
deel je een productpagina vanuit je browser naar Staartploeg, dan vraagt de app bij
welke ruimte de link hoort. De service worker is netwerk-eerst, met de cache alleen
als vangnet — een verouderde versie serveren is erger dan even geen verbinding.

Bij het publiek maken van de repo zijn de commit-adressen omgezet naar het
noreply-adres van GitHub, zodat het e-mailadres niet publiek werd.
