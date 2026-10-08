# API-contract

Alle endpoints onder `/api/`, JSON, tijden als ISO 8601 met tijdzone (UTC), datums als
`YYYY-MM-DD` (lokale datum Europe/Amsterdam). Bedragen in euro, energie in kWh, gas in m³.
Inloggen: IAP vóór Cloud Run zet `X-Goog-Authenticated-User-Email`; lokaal `THUIS_AUTH_UIT=1`.
Zonder geldige header: 401; een adres buiten `TOEGESTANE_EMAILS`: 403. Validatiefouten: 422.

Dit bestand is leidend voor backend (`app/thuis`) en frontend (`app/web`).

### `GET /api/gebruiker`
`{"email": "frank@…"}`

### `GET /api/dag?datum=YYYY-MM-DD`
Eén dag per uur (23/24/25 uren rond de zomertijdwissel). Zonder `datum`: vandaag.
```json
{
  "datum": "2026-10-07",
  "uren": ["2026-10-06T22:00:00+00:00", "..."],
  "reeksen": {
    "stroom": [0.41, ...], "teruglevering": [0, ...], "gas": [0.08, ...], "laden": [0, ...],
    "kosten_stroom": [0.11, ...],
    "temperatuur": [11.2, null, ...]
  },
  "prijzen": {
    "stroom": [{"van": "...", "tot": "...", "prijs": 0.231}],
    "gas":    [{"van": "...", "tot": "...", "prijs": 1.32}]
  },
  "totalen": {
    "stroom":        {"hoeveelheid": 6.16, "kosten": 1.57, "eenheid": "kWh"},
    "teruglevering": {"hoeveelheid": 11.37, "kosten": -0.82, "eenheid": "kWh"},
    "gas":           {"hoeveelheid": 3.57, "kosten": 4.71, "eenheid": "m³"},
    "laden":         {"hoeveelheid": 32.4, "kosten": 6.60, "eenheid": "kWh"}
  },
  "compleet": {"verbruik": true, "prijzen": true}
}
```
- `laden` is een deel van `stroom` (de lader hangt achter de meter) en telt niet apart mee in totale kosten.
- `laden` komt uit de meterstand van de lader: het verschil tussen twee metingen telt bij het uur
  van de latere meting, tegen de prijs van het blok waar het midden van dat interval in valt.
- `kosten_stroom` per uur = stroom − |teruglevering|.
- `temperatuur`: gemiddelde °C per uur (Open-Meteo), `null` waar onbekend.
- Prijsblokken zijn kwartieren (of uren, voor oudere data).

### `GET /api/periode?type=week|maand|jaar&datum=YYYY-MM-DD`
De periode waar `datum` in valt (zonder `datum`: vandaag). Week = maandag t/m zondag.
Week/maand: bakjes per dag; jaar: per maand.
```json
{
  "type": "week",
  "van": "2026-10-05", "tot": "2026-10-11",
  "label": "5 – 11 okt 2026",
  "bakjes": ["2026-10-05", "2026-10-06", "..."],
  "bakje_labels": ["ma 5", "di 6", "..."],
  "reeksen": {
    "stroom": [...], "teruglevering": [...], "gas": [...], "laden": [...],
    "kosten": [...],
    "temperatuur": [...]
  },
  "totalen": { "...": "zelfde vorm als /api/dag totalen" },
  "vorige":  { "...": "totalen van de vorige periode van hetzelfde type" },
  "vorige_label": "28 sep – 1 okt 2026"
}
```
- `vorige`: loopt de periode nog (de laatste dag met meterdata ligt vóór `tot`), dan alleen
  dezelfde dagen van de vorige periode; `vorige_label` zegt welke.
- Maand: `bakje_labels` = `["1", "2", ...]`, `label` = `"oktober 2026"`.
- Jaar: `bakjes` = `["2026-01", ...]`, `bakje_labels` = `["jan", ...]`, `label` = `"2026"`.
- `kosten` per bakje = stroom + gas − |teruglevering|.
- `null` in `stroom`/`teruglevering`/`gas`/`kosten`: geen meterdata voor dat bakje (nog niet binnen,
  of in de toekomst). `laden` is `0` voor verleden bakjes zonder laden en `null` voor de toekomst.
- `temperatuur` = gemiddelde °C per bakje of `null`.

### `GET /api/nu`
```json
{
  "tijd": "...",
  "auto":  {"naam": "EV6", "accu_pct": 59.3, "bereik_km": 273, "ingeplugd": true, "laadt": false, "bijgewerkt": "...", "tijd": "..."} | null,
  "lader": {"naam": "Oprit", "status": "wacht_op_start", "vermogen_kw": 0, "sessie_kwh": 32.4, "totaal_kwh": 4242.4, "tijd": "..."} | null,
  "plan": {"nu_laden": false, "reden": "wachten", "nodig_kwh": 17.8, "kosten": 3.2, "volledig": true,
           "vertrek": "...", "prijs_nu": 0.283, "accu_pct": 59.3,
           "blokken": [{"van": "...", "tot": "...", "prijs": 0.18}]},
  "instellingen": {"doel_pct": 80, "vertrek": "07:30", "capaciteit_kwh": 77.4, "vermogen_kw": 11,
                   "rendement_pct": 90, "altijd_onder": 0, "sturen": false}
}
```
Lader-statussen: `laden, wacht_op_start, klaar_om_te_laden, niet_verbonden, klaar, offline, fout,
wacht_op_smart_start, wacht_op_schema, wacht_op_autorisatie, ...` (zie `connectors/easee.py`).
Plan-redenen: `gepland, onder_drempel, wachten, doel_bereikt, geen_prijzen, uitgeschakeld`.

### `GET /api/instellingen` · `PUT /api/instellingen`
Body/antwoord = `instellingen` hierboven. Validatiefout → 422.

### `GET /api/laadsessies?van=YYYY-MM-DD&tot=YYYY-MM-DD`
Sessies die in die dagen begonnen (beide inclusief). Standaard de laatste 30 dagen. Nieuwste eerst.
`van` na `tot` → 422.
```json
[
  {"lader_id": "EH000001", "start": "...", "eind": "...", "kwh": 32.4, "kosten": 5.83,
   "gem_prijs": 0.18, "slim": true, "klaar": true, "besparing": 1.20}
]
```
- Een sessie loopt van inpluggen (`start`) tot uitpluggen; `eind` = laatste meting waarin geladen werd.
- `slim` = tijdens de sessie heeft Slim laden de lader gestuurd (stuuractie).
- `klaar` = uitgeplugd of de lader meldt `klaar`; `false` = sessie loopt nog.
- `besparing` = kosten bij direct laden vanaf inpluggen (op het hoogst gemeten vermogen) min de
  werkelijke kosten; `null` als de prijzen dat venster niet dekken.

### `GET /api/inzichten?datum=YYYY-MM-DD`
Korte, uitgerekende inzichten voor de overzichtspagina. Volgorde = belangrijkste eerst.
Voor een eerdere datum wordt gerekend alsof het het eind van die dag is.
```json
[
  {"id": "besparing_laden", "titel": "Slim laden bespaarde", "waarde": "€ 12,40",
   "toelichting": "deze maand t.o.v. direct laden · 4 sessies", "toon": "goed", "icoon": "auto"}
]
```
- `toon`: `goed` | `neutraal` | `let_op`
- `icoon`: `euro` | `bliksem` | `auto` | `vlam` | `zon` | `klok` | `trend_op` | `trend_neer` | `thermometer`
- Ids, in deze volgorde: `negatieve_prijzen` (vanaf nu t/m morgen), `goedkoopste_morgen` (goedkoopste
  aaneengesloten uur, met het daggemiddelde), `besparing_laden` (deze maand), `kosten_maand` (t.o.v. dezelfde dagen vorige
  maand), `gem_laadprijs` (t.o.v. de gemiddelde stroomprijs), `gas_vs_vorige_week` (per graaddag,
  basis 18 °C). Een inzicht zonder data wordt weggelaten.

### `GET /api/koppelingen`
Per dienst de status, voor de pagina "Koppelingen". Nooit tokens of wachtwoorden.
```json
[
  {"dienst": "easee", "naam": "Easee", "uitleg": "Voor de lader: …",
   "velden": [{"naam": "gebruiker", "label": "E-mailadres of telefoonnummer", "type": "text"},
              {"naam": "wachtwoord", "label": "Wachtwoord", "type": "password"}],
   "methode": "inloggen", "status": "ok", "account": "fr…@herling.nl", "sinds": "2026-10-08T14:00:00+00:00"}
]
```
- `dienst`: `frank` | `easee` | `kia` | `bmw` | `google_chat`
- `methode`: `inloggen` (de velden versturen is genoeg) | `code` (BMW: daarna een code bevestigen
  op de site van BMW, zie hieronder)
- `status`: `ok` | `opnieuw` (bewaarde tokens werken niet meer) | `script` (oude login uit het
  setup-script) | `niet`
- `velden[].type`: `text` | `email` | `password` | `url` | `keuze` (met `keuzes`)

### `POST /api/koppelingen/{dienst}` · `DELETE /api/koppelingen/{dienst}`
POST-body = de velden van die dienst, bijv. `{"gebruiker": "…", "wachtwoord": "…"}`. Thuis logt één
keer in en bewaart alleen wat de dienst teruggeeft (tokens, leveringsadres); het wachtwoord niet.
Antwoord: `{"bericht": "Laders gevonden: Oprit", "koppelingen": [ …zoals GET… ]}`. Daarna start
Thuis meteen een ronde van de verzamelaar.
- 400 met `detail` voor de gebruiker (verkeerde login, ontbrekend veld), 404 onbekende dienst,
  422 ongeldig veld (wachtwoorden worden nooit teruggegeven), 502 als de dienst onverwacht antwoordt.
- DELETE haalt de koppeling weg (en een koppeling die nog op bevestiging wacht); antwoord zoals GET.

### Koppelen met een code (BMW)
BMW CarData werkt met de device code flow: Thuis krijgt geen wachtwoord, je bevestigt een code op
de site van BMW.
1. `POST /api/koppelingen/bmw` met `{"client_id": "…"}` (de client-ID uit het CarData-portaal).
   Antwoord: `{"code": {"code": "KQ7M-XW2P", "link": "https://…", "interval": 5, "verloopt": "…"}}`.
   De app toont de code en de link; wat Thuis nodig heeft om de tokens op te halen (device code,
   PKCE-verifier) blijft op de server, in de kluis onder `wachtend`.
2. `POST /api/koppelingen/bmw/controleer`, elke `interval` seconden. Antwoord
   `{"wacht": true, "interval": 5}` zolang de code niet is bevestigd (het interval kan oplopen als
   BMW dat vraagt), daarna als bij koppelen: `{"bericht": "Auto gevonden: BMW i4 eDrive40",
   "koppelingen": [ … ]}`.
- 400: code verlopen, geweigerd of afgebroken: opnieuw beginnen bij stap 1. 409: er loopt geen
  koppeling (meer).
- Bij het bevestigen zoekt Thuis de auto waarvan je hoofdgebruiker bent en maakt het bij BMW een
  "container" met de gegevens die het leest (accu, bereik, stekker, laadstatus).

### `GET /api/status?tabellen=true|false`
Gezondheid per bron uit de rondelog van de verzamelaar, voor de statusstip en de pagina "Bronnen".
Standaard zonder `tabellen` (één query); `tabellen=true` voegt ze toe (een query per tabel).
```json
{
  "bronnen": [
    {"stap": "prijzen",  "naam": "Frank Energie · prijzen",  "uitslag": "ok", "tijd": "...", "laatst_ok": "..."},
    {"stap": "verbruik", "naam": "Frank Energie · verbruik", "uitslag": "fout: ...", "tijd": "...", "laatst_ok": "..."},
    {"stap": "lader",    "naam": "Easee",                    "uitslag": "overgeslagen", "tijd": "...", "laatst_ok": null},
    {"stap": "auto",     "naam": "Kia Connect",              "...": "..."},
    {"stap": "bmw",      "naam": "BMW CarData",              "...": "..."},
    {"stap": "weer",     "naam": "Open-Meteo",               "...": "..."},
    {"stap": "sturen",   "naam": "Slim laden",               "...": "..."},
    {"stap": "meldingen","naam": "Google Chat",              "...": "..."}
  ],
  "tabellen": {"prijs": "...", "verbruik": "...", "lader_meting": "...", "auto_meting": "...", "...": "..."}
}
```
- `uitslag`: `ok` | `overgeslagen` | `fout: <tekst>`, of `null` als de stap de laatste 30 dagen niet draaide.
- `tijd` = laatste ronde; `laatst_ok` = laatste ronde met `ok` (binnen 30 dagen).
- `tabellen` = wanneer elke tabel voor het laatst een rij kreeg (`null` = nog leeg).
- De naam van `auto` volgt `KIA_MERK`: Kia Connect, Hyundai Bluelink of Genesis Connected.
- `bmw` is ook `ok` in een ronde waarin de auto niet aan de beurt was: BMW staat 50 verzoeken per
  dag toe, dus Thuis vraagt elk kwartier als de auto laadt, elk half uur met de stekker erin en
  anders elk uur (nooit meer dan 45 per 24 uur).
