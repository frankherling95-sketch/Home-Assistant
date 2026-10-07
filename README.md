# Home Assistant — configuratie als code

Deze repo **is** de `/config`-map van mijn Home Assistant. Wijzigingen worden hier ontwikkeld,
getest in CI en via de Git pull-app naar Home Assistant gehaald.

```
ontwikkelen ─▶ PR (tests, hassfest, config-check) ─▶ main ─▶ Git pull-app ─▶ Home Assistant
```

Documentatie: https://frankherling95-sketch.github.io/Home-Assistant/

## Structuur

| Pad | Wat |
| --- | --- |
| `configuration.yaml` | Basis: packages, dashboards, valuta EUR |
| `packages/bronnen.yaml` | **Enige plek** waar entiteiten van Frank Energie, Kia en Easee genoemd worden |
| `packages/energie_prijzen.yaml` | Prijsinzichten: laagste/hoogste/gemiddeld, goedkoopste moment, niveau |
| `dashboards/energie.yaml` | Energie: totalen, vermogensbronnen, elektriciteit, gas & water, prijzen |
| `dashboards/laden.yaml` | Auto, lader en het laadplan van Slim laden |
| `custom_components/slim_laden/` | Eigen integratie: laden op de goedkoopste uren |
| `blueprints/automation/slim_laden/` | Stuurt de Easee-lader op basis van Slim laden |
| `tools/koppel-git.sh` | Eenmalig: bestaande `/config` veilig aan deze repo koppelen |
| `tests/` | pytest tegen een echte Home Assistant-testomgeving |
| `index.html` | GitHub Pages |

**Niet** in git (zie `.gitignore`, die werkt met een toestaanlijst): `secrets.yaml`, `.storage/`,
de database, logs, `automations.yaml`/`scripts.yaml`/`scenes.yaml` (die beheert de UI) en via HACS
geïnstalleerde integraties.

## Lagen

```
Frank Energie · Kia/Hyundai · Easee     (HACS-integraties, in de UI ingesteld)
              │
              ▼
packages/bronnen.yaml                   stabiele namen: sensor.stroomprijs_nu, sensor.auto_accuniveau, …
              │
              ├─▶ packages/energie_prijzen.yaml     inzichten
              ├─▶ Slim laden                       planning  ─▶ blueprint ─▶ Easee
              ▼
dashboards/*.yaml                        alleen stabiele namen
```

Andere auto, lader of leverancier: alleen `packages/bronnen.yaml` aanpassen.

## Eerste keer instellen

1. **Backup**: Instellingen → Systeem → Back-ups → nu maken.
2. **HACS-integraties** installeren en instellen: Frank Energie, Easee, Kia/Hyundai Connect.
   In HACS → Frontend ook **apexcharts-card** (voor de prijsgrafieken).
3. **Terminal & SSH-app** openen en uitvoeren:
   ```bash
   curl -fsSL https://raw.githubusercontent.com/frankherling95-sketch/Home-Assistant/main/tools/koppel-git.sh | bash
   ```
   Dit koppelt `/config` aan de repo zonder je automatiseringen, `secrets.yaml`, `.storage` of
   HACS-integraties te wissen. Van je oude `configuration.yaml` blijft een kopie staan; het script
   toont wat er anders is.
4. **`packages/bronnen.yaml`**: de regels met `# PAS AAN` moeten naar jouw entiteiten wijzen
   (Instellingen → Apparaten en diensten → Entiteiten). Stuur ze door, dan pas ik ze aan.
5. Herstarten: `ha core restart`.
6. **Git pull-app** installeren en instellen:
   ```yaml
   repository: https://github.com/frankherling95-sketch/Home-Assistant.git
   git_branch: main
   git_command: pull
   auto_restart: true
   restart_ignore: [dashboards/, README.md, index.html, tests/, .github/]
   repeat: { active: true, interval: 300 }
   ```
   Start de app pas ná stap 3: een eerste clone door de app zelf wist `.yaml`-bestanden die
   niet in de repo staan.
7. **Slim laden** toevoegen (Instellingen → Integratie toevoegen) met `sensor.stroomprijs_nu`
   en `sensor.auto_accuniveau`, en een automatisering maken van de blueprint *Slim laden → Easee*.
8. **Energie-instellingen** (Instellingen → Dashboards → Energie): bij netverbruik
   *Gebruik een entiteit met de huidige prijs* → `sensor.stroomprijs_nu`. Optioneel bij
   *Individuele apparaten*: `sensor.lader_energie_totaal`.

Daarna: wijzigingen komen binnen 5 minuten na een merge naar `main` vanzelf binnen. De Git pull-app
draait eerst een config-check en herstart alleen als die slaagt.

## Slim laden

Laadt de auto op de goedkoopste prijsblokken vóór de vertrektijd.

1. Benodigde energie = `(doel-SoC − SoC) × capaciteit ÷ rendement`. Onbekende SoC telt als leeg.
2. Alle prijsblokken (uur of kwartier) tussen nu en de vertrektijd, goedkoopste eerst, tot de energie gedekt is.
3. `Nu laden` = aan als het huidige blok in het plan zit, **of** de prijs op/onder *Altijd laden onder* ligt
   (standaard € 0,00 → gratis/negatieve uren altijd meepakken, tot 100%).
4. Herberekend elke minuut en direct bij een nieuwe prijs of SoC.

Prijzen voor morgen komen rond 13:00; daarvoor is het plan soms `volledig: false`.

| Entiteit (vast, onafhankelijk van taal) | Functie |
| --- | --- |
| `binary_sensor.slim_laden_charge_now` | Stuursignaal; attribuut `reden` |
| `sensor.slim_laden_plan_start` / `_plan_end` | Eerste/laatste blok; attribuut `blokken` |
| `sensor.slim_laden_needed_energy` | kWh uit het net |
| `sensor.slim_laden_estimated_cost` / `_average_price` | Op basis van de all-in prijs |
| `number.slim_laden_target_soc` · `time.slim_laden_departure` | Doel-SoC · vertrektijd |
| `number.slim_laden_cheap_threshold` | Prijsdrempel in €/kWh |
| `switch.slim_laden_enabled` | Uit = gewoon laden |

Zet in de Easee-app geen eigen laadschema aan; dat vecht met de blueprint.

## Ontwikkelen en testen

```bash
pip install pytest-homeassistant-custom-component
pytest
```

CI (`.github/workflows/validate.yml`) draait pytest, de Home Assistant-configcheck, hassfest en de
HACS-validatie. `planner.py` heeft geen Home Assistant-afhankelijkheden; daar zit de rekenlogica.

## Bekende grenzen

- De SoC komt via de Kia/Hyundai-cloud en ververst niet elke minuut.
- Laadvermogen is een vaste aanname; bij een koude accu laadt de auto trager.
- Energiebronnen en -kosten blijven in de UI ingesteld: Home Assistant kent daar geen YAML voor.
