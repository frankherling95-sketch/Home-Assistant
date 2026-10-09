# Thuis: je eigen installatie, stap voor stap

Met deze handleiding zet je de app **Thuis** op in je eigen Google Cloud-account. Je ziet daarna
op je computer en telefoon je stroom- en gasverbruik, de stroomprijzen per kwartier, en de accu
en het laden van je auto.

- **Tijd:** ongeveer 45 minuten, één keer.
- **Kosten:** € 0 per maand. Alles blijft binnen de gratis ruimte van Google Cloud. Je krijgt een
  mail als er toch iets dreigt te gaan kosten (vanaf € 0,50).
- **Privacy:** alles staat in je eigen account. Niemand anders, ook de maker van de app niet,
  kan bij je gegevens. Je wachtwoorden bewaart de app helemaal niet: je logt één keer in, daarna
  gebruikt Thuis alleen een sleutel van de dienst.

Je hoeft geen programmeur te zijn. Je volgt de stappen en kopieert een paar opdrachten.
Loop je vast, maak dan een schermafdruk en stuur die naar Frank.

---

## Wat heb je nodig?

1. **Een Google-account**, bijvoorbeeld je gmail-adres.
2. **Een bankpas of creditcard.** Google vraagt die om misbruik te voorkomen. Je betaalt niets
    zolang je binnen de gratis ruimte blijft, en dat doet deze app.
3. **Je logins:**
    - Frank Energie: e-mailadres en wachtwoord.
    - Easee: e-mailadres (of telefoonnummer) en wachtwoord.
    - Kia Connect of Hyundai Bluelink: e-mailadres en wachtwoord. Je pincode is **niet** nodig.
4. **Een computer** met Chrome of Edge. Dat werkt makkelijker dan een telefoon.

De logins vul je pas aan het eind in, in de app zelf (deel 7). Heb je er een nog niet bij de
hand? Geen probleem, die kun je later toevoegen.

---

## Deel 1: Google Cloud-account aanmaken (±10 minuten)

1. Ga naar **https://console.cloud.google.com** en log in met je Google-account.
2. Kies je land (**Nederland**), ga akkoord met de voorwaarden en klik op **Akkoord en doorgaan**.
3. Klik bovenaan op **Gratis proberen** (of *Start free*). Vul je adres en je bankpas of
    creditcard in.
    - Je krijgt $ 300 tegoed voor 90 dagen. Dat heb je voor deze app niet nodig, maar het kan
      geen kwaad.
4. **Belangrijk:** klik daarna op **Activeren** (*Activate full account*). Die knop staat
    bovenaan in een balk of op de welkomstpagina.
    - Zonder deze stap zet Google na 90 dagen alles stil.
    - Ook na het activeren betaal je niets binnen de gratis ruimte.

---

## Deel 2: Een project maken (±3 minuten)

Een *project* is een map in Google Cloud waar alles van de app in komt.

1. Ga naar **https://console.cloud.google.com/projectcreate**.
2. Vul bij **Projectnaam** in: `Thuis`.
3. Laat **Locatie** staan op **Geen organisatie** (*No organization*) en klik op **Maken**.
4. Onder de projectnaam staat een **project-ID**, bijvoorbeeld `thuis-471209`.
    **Schrijf die op**, je hebt hem straks nodig.

---

## Deel 3: Cloud Shell openen (±2 minuten)

Cloud Shell is een venster in je browser waarin je opdrachten geeft aan Google Cloud.

1. Ga naar **https://shell.cloud.google.com**. Log in met hetzelfde Google-account als je dat
    gevraagd wordt.
2. Onderin verschijnt een zwart venster met een regel die eindigt op `$`. Daar plak je de
    opdrachten.
    - Plakken: **Ctrl+V**. Lukt dat niet, gebruik dan de rechtermuisknop en kies **Plakken**.
    - Na het plakken druk je op **Enter**.
3. Vraagt Google of Cloud Shell mag doorgaan (**Authorize Cloud Shell**)? Klik op **Authorize**.

Plak deze opdracht en vervang `JOUW-PROJECT-ID` door het project-ID uit deel 2:

```bash
gcloud config set project JOUW-PROJECT-ID
```

Plak daarna deze opdracht. Hij haalt de app op:

```bash
git clone https://github.com/frankherling95-sketch/Home-Assistant.git && cd Home-Assistant
```

---

## Deel 4: De installatie starten (±10 minuten)

Plak deze opdracht:

```bash
bash deploy/setup-gcp.sh
```

De installatie loopt nu vanzelf. Blauwe regels die met `==` beginnen, laten zien waar hij is.
Onderweg krijg je twee vragen. Bij allebei druk je op **Enter**.

**"Toch hier logins invullen?"** Druk op **Enter**: dat betekent **nee**. Je koppelt je accounts
straks in de app (deel 7). Dat is makkelijker en veiliger, want dan bewaart de app je
wachtwoorden niet.

**De vraag over GitHub.** Je krijgt de vraag *"Ben jij beheerder van github.com/… en moet
die hier mogen deployen?"*. Druk op **Enter**: dat betekent **nee**. Deze stap is alleen voor
de maker van de app.

**Even wachten.** Bij *Container-image* wordt de app gebouwd; dat duurt een paar minuten. Bij
*Verzamelaar* haalt de app de eerste gegevens op.

**Gele LET OP-melding bij "App"?** Die is te verwachten. Hij betekent dat het inlogscherm nog
ingesteld moet worden. Dat doe je in deel 5.

Aan het eind staat **== Klaar** met het adres van je app, iets als
`https://thuis-app-123456789012.europe-west4.run.app`. Bewaar dat adres.

---

## Deel 5: Het inlogscherm instellen (eenmalig, ±5 minuten)

Google wil dat je één keer zelf aangeeft wie mag inloggen. De knoppen hieronder staan in het
Engels; staat je scherm in het Nederlands, dan zitten ze op dezelfde plek.

1. Open de link die in de gele melding stond. Hij begint met
    `https://console.cloud.google.com/run/detail/…`.
2. Klik op het tabblad **Security** (*Beveiliging*).
3. Bij **Identity-Aware Proxy (IAP)** klik je op **Edit policy** en daarna op **Configure in IAP**.
4. Klik op **Configure consent screen** en vul in:
    - **App name:** `Thuis`
    - **User support email:** je eigen e-mailadres
    - **Audience:** kies **External**
    - **Contact information:** je eigen e-mailadres

    Klik op **Create** of **Save**.

5. Ga terug naar het IAP-scherm, klik op **Auto generate credentials** en dan op **Save**.
6. Ga naar **https://console.cloud.google.com/auth/audience**. Klik bij **Test users** op
    **Add users**, vul je eigen e-mailadres in en klik op **Save**.

Ga terug naar Cloud Shell en start de installatie nog een keer. Die is nu in een minuut klaar:

```bash
bash deploy/setup-gcp.sh
```

Druk bij beide vragen (logins wijzigen en GitHub) op **Enter**. Bij *App* staat nu
**toegang voor jouw-adres@gmail.com** en de gele melding is weg.

**Tip:** zie je `No such file or directory` of is de verbinding weggevallen? Plak dan eerst
deze twee opdrachten, met je eigen project-ID:

```bash
cd ~/Home-Assistant
```
```bash
gcloud config set project JOUW-PROJECT-ID
```

---

## Deel 6: De app openen en op je telefoon zetten

1. Open het adres van je app uit deel 4 en log in met je Google-account.
    - Zie je *"Google heeft deze app niet geverifieerd"*? Klik dan op **Doorgaan**. Het is je
      eigen app.
2. **Op je telefoon:** open hetzelfde adres en log in.
    - **Android (Chrome):** menu (⋮) en dan **Toevoegen aan startscherm**.
    - **iPhone (Safari):** deelknop (vierkantje met pijl) en dan **Zet op beginscherm**.

Wat je op elke pagina vindt:

| Pagina | Wat je ziet |
| --- | --- |
| Overzicht | stroomprijs nu, energiestromen, auto en lader, tips |
| Energie | verbruik en kosten per dag, week, maand en jaar |
| Prijzen | de stroomprijs per kwartier, vandaag en morgen |
| Laden | je auto, de lader, het laadplan en je laadsessies |
| Inzichten | besparingen en vergelijkingen |
| Koppelingen (ook via het bolletje rechtsboven) | je accounts koppelen, en of alles werkt |

---

## Deel 7: Je accounts koppelen (±5 minuten)

1. Open in de app **Koppelingen**. Op je telefoon tik je op het bolletje rechtsboven.
2. Klik bij **Frank Energie** op **Koppelen**. Vul je e-mailadres en wachtwoord in en klik op
   **Koppelen**. Na een paar seconden staat er **Gekoppeld**.
3. Doe hetzelfde bij **Easee** en bij **Kia / Hyundai**. Kies daar eerst het merk; je pincode is
   niet nodig.
4. Optioneel: **Google Chat**, voor meldingen op je telefoon. Hoe je het webhook-adres maakt,
   staat bij het formulier.
5. Optioneel: **Tuya / Smart Life**, voor je slimme stekkers, lampen en sensoren. Daarvoor maak je
   eerst een gratis project op platform.tuya.com en koppel je daar je Smart Life-account. De vier
   stappen staan bij het formulier; reken op ±10 minuten.

Thuis logt één keer in en bewaart daarna alleen een sleutel van de dienst, niet je wachtwoord.
Binnen een paar minuten staan de eerste gegevens in de app. Je verbruik komt via Frank Energie
met ongeveer een dag vertraging.

Goed om te weten:

- **Gegevens:** elk kwartier haalt de app nieuwe gegevens op.
- **Opnieuw koppelen:** staat er ooit **Opnieuw koppelen** bij een dienst, bijvoorbeeld omdat je
  je wachtwoord daar hebt veranderd? Klik erop en log opnieuw in.
- **Slim laden:** de app laat je zien wanneer laden het goedkoopst is. Hij stuurt de lader
  **niet** zelf aan. Dat zet je pas aan bij Laden → Instellingen, als het plan een paar dagen
  klopt.

---

## Later

### Een nieuwe versie installeren

Laat Frank weten dat er een nieuwe versie is? Open Cloud Shell en plak:

```bash
cd ~/Home-Assistant && git pull
```
```bash
BOUW=1 bash deploy/setup-gcp.sh
```

Druk bij beide vragen op **Enter**.

### Kosten bekijken

Kijk bij **https://console.cloud.google.com/billing**, onder **Rapporten** (*Reports*). Je
krijgt automatisch een mail bij € 0,50, € 0,90 en € 1 in een maand. Dat zou niet moeten
gebeuren.

### Stoppen

Wil je de app niet meer? Verwijder dan het project. Daarmee is alles weg, ook je gegevens.

1. Ga naar **https://console.cloud.google.com/iam-admin/settings**.
2. Kies je project, klik op **Shut down** en typ het project-ID ter bevestiging.

---

## Hulp bij problemen

| Wat je ziet | Wat je doet |
| --- | --- |
| *Aan dit project hangt geen betaalaccount* | Ga naar **https://console.cloud.google.com/billing/linkedaccount**, kies je project en koppel je betaalaccount. Start de installatie opnieuw. |
| *No such file or directory* | Plak eerst `cd ~/Home-Assistant` en daarna de opdracht opnieuw. |
| De verbinding met Cloud Shell viel weg | Open Cloud Shell opnieuw en plak de twee opdrachten uit de tip in deel 5. |
| In de app: *You don't have access* | Doe deel 5 (nog eens), en log in met hetzelfde Google-account als in Cloud Shell. |
| Op de pagina **Koppelingen** staat bij iets **Mislukt** of **Opnieuw koppelen** | Klik bij die dienst op **Opnieuw koppelen** en log opnieuw in. |
| Bij koppelen: *Inloggen mislukt* | Controleer e-mailadres en wachtwoord: log ter controle in de app van die dienst in. |
| Iets anders, of rode tekst met *ERROR* | Maak een schermafdruk en stuur die naar Frank. |
