# Naar Google Cloud

Eén script in Cloud Shell richt alles in. Daarna deployt elke merge naar `main` vanzelf via
GitHub Actions. Verwachte kosten: € 0 (alles binnen de gratis laag), met een budgetalarm
op € 1 voor het geval dat.

## Wat er komt te staan

| Onderdeel | Naam | Wat |
| --- | --- | --- |
| Cloud Run-service | `thuis-app` | API en web-app, alleen bereikbaar via IAP met je Workspace-account |
| Cloud Run-job | `thuis-verzamel` | Eén ronde: Frank Energie, Easee, Kia, Open-Meteo, Slim laden, meldingen |
| Cloud Scheduler | `thuis-verzamel-elk-kwartier` | Start de job om :00, :15, :30 en :45 |
| BigQuery | dataset `thuis` (EU) | Alle historie; tabellen maakt de verzamelaar zelf |
| Secret Manager | `thuis-geheimen` | De kluis: tokens van de koppelingen (en eventuele oude logins) in één JSON; alleen `thuis-run` kan erbij |
| Artifact Registry | `thuis` | Container-images; na 7 dagen weg, de laatste 5 blijven |
| Service-accounts | `thuis-run`, `thuis-deploy` | De app en job draaien als `thuis-run`; GitHub deployt als `thuis-deploy` |
| Workload Identity | pool `github` | GitHub Actions logt in zonder sleutel, alleen vanaf `main` van deze repository |
| Budget | `Thuis` | Mail bij 50%, 90% en 100% van € 1 per maand |

Regio `europe-west4` (Eemshaven), BigQuery in de EU.

## Vooraf

- Een Google Cloud-project met een **betaalaccount** eraan (verplicht, ook binnen de gratis laag).
- Je bent **eigenaar** van het project. Voor het budgetalarm moet je ook beheerder van het
  betaalaccount zijn; anders slaat het script die stap over met een melding.
- Het project hangt onder je **Google Workspace**-organisatie. Dan regelt IAP het inloggen
  zonder verdere instellingen. Met een los gmail-account: zie onderaan.

## Inrichten

Open [Cloud Shell](https://shell.cloud.google.com) en draai:

```bash
git clone https://github.com/frankherling95-sketch/Home-Assistant.git && cd Home-Assistant
gcloud config set project JOUW-PROJECT
bash deploy/setup-gcp.sh
```

Het script bouwt het eerste image (een paar minuten), draait één ronde en zet IAP aan. Je
accounts koppel je daarna in de app (pagina **Koppelingen**); het script kan ze ook vragen,
maar dan staan de wachtwoorden in de kluis in plaats van alleen tokens. Op de vraag of jij beheerder
bent van de GitHub-repository antwoord je met `j` (of zet `GITHUB=j` vóór het commando): dan
mag GitHub Actions in dit project deployen. Aan het eind staan de URL van de app en vier
GitHub-variabelen. Is `gh` ingelogd, dan zet het script die zelf.

Iemand anders (zonder toegang tot deze repository) zet een eigen installatie op met
**[eigen-installatie.md](eigen-installatie.md)**: stap voor stap, ook met een los gmail-account.

Wie mogen er in? Standaard alleen jij. Meer mensen:

```bash
EMAILS=frank@voorbeeld.nl,partner@voorbeeld.nl bash deploy/setup-gcp.sh
```

Het script is herhaalbaar: wat bestaat blijft staan, instellingen worden bijgewerkt. Draai het
na een update van de app die nieuwe rechten of instellingen nodig heeft opnieuw (de PR zegt het).

## Automatisch deployen

Na de vier variabelen (Settings → Secrets and variables → Actions → **Variables**):

| Variabele | Voorbeeld |
| --- | --- |
| `GCP_PROJECT` | `thuis-123456` |
| `GCP_REGIO` | `europe-west4` |
| `GCP_WIF_PROVIDER` | `projects/123…/locations/global/workloadIdentityPools/github/providers/github-repo` |
| `GCP_DEPLOY_SA` | `thuis-deploy@thuis-123456.iam.gserviceaccount.com` |

doet elke push naar `main` dit (`.github/workflows/deploy.yml`):

1. tests, lint en een proefbouw van het image (`ci.yml`, ook op elke pull request);
2. image bouwen en naar Artifact Registry;
3. app en verzamelaar op het nieuwe image zetten (de rest van de instellingen blijft);
4. één ronde draaien, zodat nieuwe tabellen meteen bestaan.

Zonder de variabelen slaat de workflow stap 2–4 over in plaats van te falen.

## Accounts koppelen

In de app, pagina **Koppelingen**: per dienst één keer inloggen. Thuis bewaart alleen de tokens
die de dienst teruggeeft (Frank Energie, Easee, Kia/Hyundai) of het webhook-adres (Google Chat),
niet het wachtwoord. De verzamelaar ververst de tokens elke ronde en schrijft de nieuwe terug;
oude versies van het geheim worden opgeruimd. Werkt een koppeling niet meer, dan staat er
"Opnieuw koppelen" en komt er een melding in Google Chat.

Koppelingen gaan vóór oude logins uit het setup-script. Hoe lang de tokens van Frank, Easee en
Kia geldig blijven, publiceren die diensten niet; elk kwartier verversen houdt ze normaal in leven.

**BMW (en MINI)** koppel je met een code in plaats van een wachtwoord:

1. Log in op de BMW-site (My BMW), ga naar **BMW CarData** en maak een client aan. Zet
   *CarData API* aan en kopieer de **Client-ID**.
2. Kies in Thuis bij BMW **Koppelen**, plak de client-ID en klik **Code aanvragen**.
3. Klik **Open BMW en bevestig** en bevestig daar de code (of vul hem in via *Authenticate device*
   op de CarData-pagina). Thuis ziet dat vanzelf en zoekt je auto erbij.

De tokens zijn twee weken geldig en worden bij elk verzoek ververst. BMW staat 50 verzoeken per
dag toe; Thuis blijft daar ruim onder (zie [api.md](api.md#get-apistatustabellentruefalse)).

### Oude logins (setup-script)

Het script kan ook logins vragen: draai `bash deploy/setup-gcp.sh` en antwoord `j` op *Logins
(opnieuw) invullen of wijzigen?*. Enter laat een waarde staan, `-` maakt hem leeg.

Met de hand kan ook. Alles staat samen in één JSON. Sleutels: `FRANK_EMAIL`, `FRANK_WACHTWOORD`,
`FRANK_SITE` (alleen bij meer adressen), `EASEE_GEBRUIKER`, `EASEE_WACHTWOORD`, `EASEE_LADER`
(alleen bij meer laders), `KIA_GEBRUIKER`, `KIA_WACHTWOORD`, `KIA_PIN`, `KIA_MERK`
(`kia`/`hyundai`/`genesis`), `GOOGLE_CHAT_WEBHOOK`.

```bash
gcloud secrets versions access latest --secret=thuis-geheimen > geheimen.json   # huidige stand
nano geheimen.json
gcloud secrets versions add thuis-geheimen --data-file=geheimen.json && rm geheimen.json
```

Bewaar daarbij het onderdeel `koppelingen` zoals het is. De volgende ronde gebruikt de nieuwe versie.

**Google Chat-meldingen**: maak in een Chat-ruimte een webhook (Apps en integraties →
Webhooks) en koppel die in de app.

**Plaats voor het weer**: standaard De Bilt. Een eigen plek:
`gcloud run jobs update thuis-verzamel --region=europe-west4 --update-env-vars=THUIS_LAT=52.37,THUIS_LON=4.89`.

## Controleren en beheren

- De pagina **Koppelingen** in de app toont per bron de laatste ronde en wat er misging.
- Een ronde nu draaien: `gcloud run jobs execute thuis-verzamel --region=europe-west4 --wait`
- Logs: `gcloud logging read 'resource.labels.job_name="thuis-verzamel"' --limit=50 --freshness=1h`
- IAP aan? `gcloud run services describe thuis-app --region=europe-west4 | grep -i iap`
- De app controleert de door IAP ondertekende JWT (`IAP_AUDIENCE`), niet alleen de e-mailheader,
  en daarna nog `TOEGESTANE_EMAILS`.

## Eigen domein (bijvoorbeeld home.jouwdomein.nl)

Standaard is de app bereikbaar op `https://thuis-app-NUMMER.europe-west4.run.app`. Een eigen adres
kan gratis met een **domeinkoppeling van Cloud Run**. IAP blijft gewoon werken: het beschermt alle
ingangen van de service, en de app controleert de IAP-handtekening op de service, niet op het
adres. Het run.app-adres blijft ook werken.

1. Laat Google weten dat het domein van jou is (eenmalig, voor het hoofddomein):
   ```bash
   gcloud domains list-user-verified
   gcloud domains verify jouwdomein.nl
   ```
   Staat het domein er niet bij, dan opent `verify` Search Console. Zet het TXT-record dat je daar
   krijgt bij je domeinbeheerder en klik op Verifiëren.
2. Koppel het adres aan de app:
   ```bash
   gcloud beta run domain-mappings create --service=thuis-app --domain=home.jouwdomein.nl --region=europe-west4
   gcloud beta run domain-mappings describe --domain=home.jouwdomein.nl --region=europe-west4
   ```
3. Zet bij je domeinbeheerder het record dat `describe` onder `resourceRecords` noemt. Voor een
   subdomein is dat een **CNAME**: naam `home`, waarde `ghs.googlehosted.com.`
4. Wacht op het certificaat: meestal een kwartier, soms tot 24 uur. Open daarna
   `https://home.jouwdomein.nl` in een privévenster: je krijgt de Google-login en daarna Thuis.

Goed om te weten:
- Domeinkoppelingen zijn bij Google nog **Preview**: "niet geschikt voor productie" vanwege
  mogelijk extra vertraging. Voor een app voor thuis is dat geen bezwaar; werkt het niet goed, dan
  haal je hem weg met `gcloud beta run domain-mappings delete --domain=home.jouwdomein.nl --region=europe-west4`.
- Het alternatief zonder Preview is een load balancer met IAP: ±€17 per maand.
- Firebase Hosting werkt niet met IAP (de inlogcookie komt niet door).

## Zonder Google Workspace (los gmail-account)

IAP heeft dan een eigen OAuth-client nodig; die kan alleen in de console:

1. **Google Auth Platform → Branding**: Audience op *External*; zet jezelf als testgebruiker
   (of publiceer de app, anders verloopt je toestemming na 7 dagen).
2. **Clients → Create client → Web application**, redirect-URI
   `https://iap.googleapis.com/v1/oauth/clientIds/CLIENT_ID:handleRedirect`.
3. Koppel hem aan IAP:
   ```bash
   cat > iap.yaml <<EOF
   access_settings:
     oauth_settings:
       client_id: CLIENT_ID
       client_secret: CLIENT_SECRET
   EOF
   gcloud iap settings set iap.yaml --project=JOUW-PROJECT --resource-type=cloud-run --region=europe-west4 --service=thuis-app
   ```

## Kosten

Gecontroleerd tegen de prijspagina's van Google op 8 oktober 2026. De gratis laag geldt per
betaalaccount (Logging: per project).

| Dienst | Gratis per maand | Thuis gebruikt | |
| --- | --- | --- | --- |
| Cloud Run-job | ±240.000 vCPU-s, 450.000 GiB-s | 2.880 rondes × min. 1 minuut × 1 vCPU = 172.800 vCPU-s, 86.400 GiB-s | ±72% van de CPU |
| Cloud Run-service | 2 mln. verzoeken, 180.000 vCPU-s | een paar duizend verzoeken, alleen rekentijd tijdens een verzoek | < 5% |
| Cloud Scheduler | 3 taken | 1 taak | gratis |
| Secret Manager | 6 actieve versies, 10.000 keer lezen | 1 geheim, ±3.000 keer lezen (bij elke start van de job) | gratis |
| Artifact Registry | 0,5 GB | ±0,2 GB (de lagen van de images worden gedeeld) | gratis |
| BigQuery-opslag | 10 GB | < 0,1 GB per jaar | gratis |
| BigQuery-queries | 1 TB | ±350 GB, zie hieronder | ±35% |
| BigQuery laden | gratis (laadtaken) | elke ronde één laadtaak per tabel | gratis |
| Cloud Logging | 50 GB per project | enkele MB's | gratis |
| IAP | gratis | | gratis |

**Twee posten om in de gaten te houden:**

- **Cloud Run-job.** Een job telt per uitvoering minimaal één minuut met minimaal 1 vCPU. Elk
  kwartier draaien gebruikt zo ±72% van de gratis CPU, ook als een ronde maar 15 seconden duurt.
  Wordt dat krap (bijvoorbeeld door meer diensten op hetzelfde betaalaccount), dan kan de
  verzamelaar overdag elk half uur draaien.
- **BigQuery-queries.** BigQuery rekent minimaal 10 MB per tabel per query, hoe klein de tabellen
  ook zijn. Gemeten: een ronde van de verzamelaar doet 9 queries (±90 MB, ±260 GB per maand),
  Overzicht openen 21 queries (±210 MB). Daarom ververst de web-app alleen na een nieuwe
  ronde, bewaart hij antwoorden 5 minuten, en delen de inzichten één set gegevens. Tien keer per
  dag de app openen is ±65 GB per maand; samen ±350 GB van de gratis 1 TB.

Het budgetalarm mailt bij 50% van € 1, dus ruim voordat er iets van betekenis gebeurt.
Kosten bekijken: console → Facturering → Rapporten, filter op label `app=thuis`.

## Opruimen

Alles weg (onomkeerbaar, inclusief de historie in BigQuery):

```bash
gcloud projects delete JOUW-PROJECT
```

Of los: `gcloud scheduler jobs delete thuis-verzamel-elk-kwartier --location=europe-west4`
zet het verzamelen stil, de app en de historie blijven dan staan.
