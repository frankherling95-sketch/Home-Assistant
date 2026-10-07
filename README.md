# Home Assistant — Slim laden

[![Openen in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=frankherling95-sketch&repository=staartploeg&category=integration)
[![Integratie toevoegen](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=slim_laden)
[![Blueprint importeren](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Ffrankherling95-sketch%2Fstaartploeg%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fslim_laden%2Feasee_slim_laden.yaml)

Documentatie: https://frankherling95-sketch.github.io/staartploeg/

| Pad | Wat |
| --- | --- |
| `custom_components/slim_laden/` | De integratie (HACS-installeerbaar) |
| `blueprints/automation/slim_laden/` | Automatisering die de Easee-lader aanstuurt |
| `tests/` | pytest, inclusief een echte Home Assistant-testomgeving |
| `index.html` | GitHub Pages-pagina met installatieknoppen |
| `sw.js` | Ruimt de service worker van de vroegere Staartploeg-app op bij oude bezoekers |
| `.github/workflows/validate.yml` | CI: pytest, hassfest en HACS-validatie |

Custom integration die de auto laadt op de goedkoopste uren vóór vertrek. Combineert drie
bestaande integraties in plaats van hun API's na te bouwen:

| Bron | Integratie (HACS) | Wat Slim laden ervan gebruikt |
| --- | --- | --- |
| Frank Energie dagprijzen | [bajansen/home-assistant-frank_energie](https://github.com/bajansen/home-assistant-frank_energie) | `sensor.current_electricity_price_all_in` → attribuut `prices` (from/till/price; uur- én kwartierblokken) |
| Hyundai / Kia Connect | [Hyundai-Kia-Connect/kia_uvo](https://github.com/Hyundai-Kia-Connect/kia_uvo) | `sensor.<auto>_ev_battery_level` (SoC in %) |
| Easee EV laden | [nordicopen/easee_hass](https://github.com/nordicopen/easee_hass) | actie `easee.action_command` (pause/resume) + `sensor.<lader>_status` |

```
Frank Energie ─ prijzen ─┐
                         ├─▶ slim_laden ─▶ binary_sensor.…_nu_laden ─▶ blueprint ─▶ Easee pause/resume
Kia Connect ─── SoC ─────┘
```

De integratie rekent; de blueprint stuurt. Wie later een andere lader of prijsleverancier
heeft, vervangt alleen die kant.

## Hoe het plant

1. Benodigde energie = `(doel-SoC − SoC) × capaciteit ÷ rendement`. Onbekende SoC telt als leeg.
2. Alle prijsblokken tussen nu en de eerstvolgende vertrektijd, op prijs gesorteerd.
3. Goedkoopste blokken pakken tot de energie gedekt is. Het lopende blok telt alleen voor de rest.
4. `Nu laden` = aan als het huidige blok in het plan zit, **of** de prijs op/onder `Altijd laden onder`
   ligt (standaard € 0,00 → gratis/negatieve uren altijd meepakken, tot 100%).
5. Herberekend elke minuut en direct bij een nieuwe prijs of SoC.

Prijzen voor morgen komen rond 13:00. Daarvoor is het plan soms `volledig: false`: het rekent
met wat bekend is en schuift op zodra de nieuwe prijzen binnen zijn.

## Entiteiten

| Entiteit | Functie |
| --- | --- |
| `binary_sensor.…_nu_laden` | Stuursignaal; attribuut `reden`: gepland · onder_drempel · wachten · doel_bereikt · geen_prijzen · uitgeschakeld |
| `sensor.…_start_laden` / `…_einde_laden` | Eerste en laatste gekozen blok; attribuut `blokken` met het hele plan |
| `sensor.…_benodigde_energie` | kWh uit het net |
| `sensor.…_geschatte_kosten` / `…_gemiddelde_laadprijs` | Op basis van de all-in prijs |
| `number.…_doel_accuniveau` | Doel-SoC (standaard 80%) |
| `time.…_vertrektijd` | Uiterlijk dan vol (standaard 07:30) |
| `number.…_altijd_laden_onder` | Prijsdrempel in €/kWh |
| `switch.…_slim_laden_actief` | Uit = gewoon laden, zonder planning |

## Installeren

1. Installeer via HACS de drie integraties hierboven en configureer ze.
2. HACS → ⋮ → *Aangepaste repositories* → voeg deze repo toe als type **Integratie** →
   installeer *Slim laden*. (Handmatig kan ook: kopieer `custom_components/slim_laden` naar
   `/config/custom_components/`.)
3. Kopieer `blueprints/automation/slim_laden/` naar `/config/blueprints/automation/`, of importeer
   de blueprint via *Automatiseringen → Blueprints → Blueprint importeren* met de URL van
   `easee_slim_laden.yaml` in deze repo.
4. Herstart Home Assistant.
5. *Instellingen → Apparaten en diensten → Integratie toevoegen → Slim laden*: kies de prijssensor,
   de accusensor van de auto, bruikbare capaciteit (bijv. 77,4 kWh EV6/Ioniq 5 LR, 64,8 kWh Niro EV)
   en het laadvermogen (11 kW bij 3×16 A).
6. *Automatiseringen → Nieuw → Slim laden → Easee*: kies `Nu laden`, de lader en de statussensor.

Zet in de Easee-app **geen** eigen laadschema aan; dat vecht met de blueprint.

Vereist Home Assistant 2024.6 of nieuwer. Getest tegen 2026.2.

## Testen

```bash
pip install pytest-homeassistant-custom-component
pytest
```

`planner.py` heeft geen Home Assistant-afhankelijkheden; daar zit de rekenlogica en de meeste tests.

## Bekende grenzen

- De SoC van de auto komt via de Kia/Hyundai-cloud en ververst niet elke minuut. Tijdens het laden
  loopt het plan daardoor wat achter; het laatste geplande blok vangt dat op.
- Laadvermogen is een vaste aanname. Bij een koude accu of fase-beperking laadt de auto trager en
  kan het doel net niet gehaald worden — zet dan het vermogen in de opties wat lager.
