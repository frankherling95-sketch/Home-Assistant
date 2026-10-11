# Roadmap na versie 1.0

Wensen voor na de eerste versie. Per punt staat wat versie 1.0 al doet, zodat duidelijk is
wat er nog bij moet.

Legenda: **1.0** = zit erin · **erbij** = na 1.0 toegevoegd · **deels** = basis zit erin, de rest volgt · **later** = na 1.0

## 1. Dashboard (stijl Home Assistant)

| Wens | Status | Toelichting |
| --- | --- | --- |
| Datumbalk met snelknoppen Vandaag / Dag / Week / Maand / Jaar en ‹ › zonder de pagina te herladen | 1.0 | Pagina Energie, via `/api/dag` en `/api/periode` |
| Kaart huidig tarief met trend (stijgend/dalend t.o.v. het volgende uur) | deels | Prijs nu staat erin; de trendpijl volgt |
| Dagtotalen: verbruik, kosten en gemiddelde prijs per kWh van vandaag | deels | Verbruik en kosten staan erin; gemiddelde prijs per kWh volgt |
| EV en laadpaal: accu %, aangesloten, laadvermogen, kosten van de lopende sessie | deels | Kosten van de lopende sessie volgen |
| Uurgrafiek met verbruiksstaven (laden) en de Frank-prijs als lijn of achtergrond | deels | Prijzen en laadplan staan erin; staven en prijs in één grafiek volgen |
| Prijskleuren: groen (goedkoop), geel, rood (duur), blauw/paars bij negatief | 1.0 | Pagina Prijzen, per prijsniveau zoals Tibber |
| Vergelijkingstabel per dag/week/maand: geladen kWh, kosten, gem. prijs, besparing t.o.v. een vast tarief (bijv. € 0,28/kWh) | later | 1.0 toont laadsessies met besparing t.o.v. direct laden; het vaste tarief wordt een instelling |

## 2. Slim laden en sturing

| Wens | Status | Toelichting |
| --- | --- | --- |
| Laadplanner: doel-accu en vertrektijd, kWh nodig, de goedkoopste blokken tot vertrek | 1.0 | `planner.py`, pagina Auto & laden |
| De Easee pauzeren en hervatten volgens het plan | 1.0 | Staat standaard **uit**; aanzetten in de instellingen |
| Knop **Direct laden** (plan negeren, vol vermogen) | later | Nieuw endpoint dat de lader stuurt; tijdelijke override tot de auto is losgekoppeld |
| Knop **Pauzeer** (nu stoppen zonder de kabel los te halen) | later | Idem |
| Plan alleen voor momenten dat de auto thuis is | later | 1.0 plant vanaf nu tot vertrek, ook als de stekker los is (sturen gebeurt alleen als de auto aangesloten is) |
| Kia/Hyundai alleen vaak uitlezen als de Easee zegt dat de auto aan de kabel hangt, anders ±1× per 6 uur | later | 1.0 leest alleen de gecachte status (maakt de auto niet wakker), maar wel elke ronde; minder vaak spaart ook het dagquotum van de API |

## 3. Meldingen

| Wens | Status | Toelichting |
| --- | --- | --- |
| Negatieve prijzen morgen, zodra de prijzen bekend zijn | 1.0 | Google Chat, één keer per dag |
| Extreem lage prijzen (onder een drempel) | later | Drempel als instelling |
| Doellading bereikt (bijv. 80%) | later | 1.0 meldt "laden klaar" als de lader klaar is of de kabel los is |
| Waarschuwing: 's avonds niet aangesloten terwijl de accu onder bijv. 30% zit | later | |
| Sessie afgesloten: "28,4 kWh voor € 3,12 (gemiddeld € 0,11/kWh)" | 1.0 | Met de besparing t.o.v. direct laden erbij |
| Pushberichten op de telefoon (naast Google Chat) | later | Web Push via de geïnstalleerde web-app |

## 4. Beheer en data

| Wens | Status | Toelichting |
| --- | --- | --- |
| Statuspaneel per bron (Frank, Easee, Kia) | deels | Pagina Bronnen: laatste ronde, laatst gelukt, foutmelding. Of een token nog geldig is, volgt |
| Knop **Nu ophalen** als de cronjob vertraagd is | erbij | Knop in de kop: start de Cloud Run-job `thuis-verzamel` (alle bronnen, de auto ook buiten zijn beurt), maar niet tegelijk met de geplande ronde. De auto wekken kan niet via CarData |
| Export van laadsessies en kosten naar CSV/Excel | later | Voor declaraties en de administratie |

## 5. Slimme apparaten

| Wens | Status | Toelichting |
| --- | --- | --- |
| Koppeling met Tuya (Smart Life, Tuya Smart en merken als LSC, Nedis, Calex) | erbij | Pagina Apparaten: live stand, aan en uit, helderheid, temperatuur, rolluiken, timer; snelknoppen op het overzicht. Via de cloud-API van Tuya met een eigen cloudproject |
| Verbruik en kosten per stekker met meting | erbij | Geschat uit de metingen per kwartier, tegen de stroomprijs van dat moment |
| Apparaten automatisch schakelen op de stroomprijs (bijv. boiler aan bij negatieve prijzen) | later | Zoals Slim laden voor de auto: een regel per apparaat, standaard uit |
| Melding als een sensor alarm geeft of een batterij bijna leeg is | later | Via Google Chat, zoals de andere meldingen |
| Lokaal bedienen zonder de cloud van Tuya | later | Kan niet vanuit Cloud Run; zou een klein programma thuis nodig hebben |

## 6. Weer

| Wens | Status | Toelichting |
| --- | --- | --- |
| Het weer voor thuis: nu, regen per kwartier, 48 uur en 7 dagen | erbij | Pagina Weer en kaart op het overzicht, via Open-Meteo (gratis, geen account) |
| Verwacht gasverbruik per dag uit de weersverwachting | erbij | Basis + per graaddag, uit je eigen meterdata van de laatste acht weken |
| Verwachte opbrengst van zonnepanelen | later | Kan zodra bekend is welke panelen het zijn (vermogen, richting); de straling staat al in de verwachting |
| Melding bij storm, ijzel of hitte | later | Via Google Chat, zoals de andere meldingen |

## Ook genoteerd tijdens de bouw

- **Historie inladen**: verbruik bij Frank Energie vanaf de start van het contract en temperaturen
  uit het Open-Meteo-archief, zodat jaaroverzichten en vergelijkingen meteen gevuld zijn.
- **Realtime verbruik** via een P1-meter en **zonnepanelen** als eigen connector, zodra bekend is
  welke apparaten het zijn.
