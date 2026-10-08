#!/usr/bin/env bash
# Thuis: Google Cloud inrichten. Draai in Cloud Shell (https://shell.cloud.google.com):
#
#   git clone https://github.com/frankherling95-sketch/Home-Assistant.git && cd Home-Assistant
#   gcloud config set project JOUW-PROJECT
#   bash deploy/setup-gcp.sh
#
# Het script is herhaalbaar: wat al bestaat, blijft staan of wordt bijgewerkt. Instellen kan
# met omgevingsvariabelen vóór het commando, bijvoorbeeld:
#   EMAILS=frank@herling.nl,partner@herling.nl BOUW=1 bash deploy/setup-gcp.sh
#
#   PROJECT      Google Cloud-project (standaard: het actieve project in gcloud)
#   REGIO        standaard europe-west4 (Nederland)
#   EMAILS       wie de app mag openen, komma-gescheiden (standaard: jij)
#   GITHUB=j     automatisch deployen vanuit GitHub instellen zonder het te vragen (alleen voor
#                de beheerder van GITHUB_REPO, standaard frankherling95-sketch/Home-Assistant)
#   BUDGET       maandbudget voor het alarm, standaard 1 (in de valuta van je betaalaccount)
#   BOUW=1       ook een nieuw image bouwen als de app al draait
#
# Het script vraagt de logins (Frank Energie, Easee, Kia/Hyundai). Bij een volgende keer vraagt
# het of je ze wilt wijzigen; Enter laat een waarde staan.
#
# Zie docs/deploy.md voor uitleg en kosten, en docs/eigen-installatie.md voor een eigen
# installatie stap voor stap.
set -euo pipefail
cd "$(dirname "$0")/.."

PROJECT="${PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
REGIO="${REGIO:-europe-west4}"
EMAILS="${EMAILS:-$(gcloud config get-value account 2>/dev/null)}"
GITHUB_REPO="${GITHUB_REPO:-frankherling95-sketch/Home-Assistant}"
BUDGET="${BUDGET:-1}"
BOUW="${BOUW:-0}"

APP=thuis-app
JOB=thuis-verzamel
SCHEMA=thuis-verzamel-elk-kwartier
DATASET=thuis
GEHEIM=thuis-geheimen
REPO=thuis
POOL=github
PROVIDER=github-repo
BUDGETNAAM=Thuis

stap() { printf '\n\033[1;34m== %s\033[0m\n' "$*"; }
info() { printf '   %s\n' "$*"; }
let_op() { printf '\033[1;33m   LET OP: %s\033[0m\n' "$*"; }
stil() { "$@" >/dev/null 2>&1; }

[ -n "$PROJECT" ] || { echo "Geen project. Zet eerst: gcloud config set project JOUW-PROJECT"; exit 1; }
[ -n "$EMAILS" ] || { echo "Geen e-mailadres. Zet EMAILS=jij@domein.nl"; exit 1; }
NUMMER="$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')"
RUN_SA="thuis-run@$PROJECT.iam.gserviceaccount.com"
DEPLOY_SA="thuis-deploy@$PROJECT.iam.gserviceaccount.com"
IMAGE_BASIS="$REGIO-docker.pkg.dev/$PROJECT/$REPO/thuis"

stap "Project $PROJECT ($NUMMER), regio $REGIO"
if [ "$(gcloud billing projects describe "$PROJECT" --format='value(billingEnabled)')" != "True" ]; then
  echo "Aan dit project hangt geen betaalaccount. Koppel er een in de console (Facturering) en draai opnieuw."
  exit 1
fi

stap "API's aanzetten"
gcloud services enable --project="$PROJECT" \
  run.googleapis.com cloudscheduler.googleapis.com bigquery.googleapis.com secretmanager.googleapis.com \
  artifactregistry.googleapis.com iap.googleapis.com iam.googleapis.com iamcredentials.googleapis.com \
  sts.googleapis.com cloudresourcemanager.googleapis.com billingbudgets.googleapis.com

stap "Service-accounts"
for sa in thuis-run thuis-deploy; do
  if stil gcloud iam service-accounts describe "$sa@$PROJECT.iam.gserviceaccount.com" --project="$PROJECT"; then
    info "$sa bestaat al"
  else
    gcloud iam service-accounts create "$sa" --project="$PROJECT" \
      --display-name="$([ "$sa" = thuis-run ] && echo 'Thuis: app en verzamelaar' || echo 'Thuis: deploy vanuit GitHub')"
  fi
done
for rol in roles/bigquery.dataEditor roles/bigquery.jobUser; do
  gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:$RUN_SA" --role="$rol" \
    --condition=None --quiet >/dev/null
done
info "thuis-run mag lezen en schrijven in BigQuery"

stap "BigQuery-dataset $DATASET (EU)"
if stil bq --project_id="$PROJECT" show --dataset "$PROJECT:$DATASET"; then
  info "bestaat al"
else
  bq --project_id="$PROJECT" --location=EU mk --dataset --description="Thuis: energiedata" "$PROJECT:$DATASET"
fi

stap "Logins (alle wachtwoorden samen in één geheim: $GEHEIM)"
# sleutel|vraag|verborgen
VRAGEN=(
  "FRANK_EMAIL|Frank Energie: e-mailadres|nee"
  "FRANK_WACHTWOORD|Frank Energie: wachtwoord|ja"
  "EASEE_GEBRUIKER|Easee: e-mailadres of telefoonnummer|nee"
  "EASEE_WACHTWOORD|Easee: wachtwoord|ja"
  "KIA_MERK|Auto: merk (kia of hyundai)|nee"
  "KIA_GEBRUIKER|Kia Connect / Hyundai Bluelink: e-mailadres|nee"
  "KIA_WACHTWOORD|Kia Connect / Hyundai Bluelink: wachtwoord|ja"
  "KIA_PIN|Kia/Hyundai: pincode (in Europa niet nodig, Enter)|ja"
  "GOOGLE_CHAT_WEBHOOK|Google Chat-webhook voor meldingen (mag leeg)|ja"
)
vraag_logins() {  # $1 = huidige JSON; schrijft de nieuwe JSON naar stdout (vragen gaan naar stderr)
  local regel sleutel vraag verborgen waarde
  export HUIDIG="$1"  # via de omgeving, niet als argument: zo staat het niet in de proceslijst
  info "Enter = overslaan (of laten zoals het is), - = leegmaken. Wachtwoorden zie je niet tijdens het typen." >&2
  for regel in "${VRAGEN[@]}"; do
    IFS='|' read -r sleutel vraag verborgen <<<"$regel"
    if KEY="$sleutel" python3 -c 'import json,os,sys; sys.exit(0 if json.loads(os.environ["HUIDIG"]).get(os.environ["KEY"]) else 1)'; then
      vraag="$vraag [al ingevuld]"
    fi
    if [ "$verborgen" = ja ]; then read -rsp "   $vraag: " waarde; echo >&2; else read -rp "   $vraag: " waarde; fi
    if [ -n "$waarde" ]; then printf '%s\0%s\0' "$sleutel" "$waarde"; fi
  done | python3 -c '
import json, os, sys
uit = json.loads(os.environ["HUIDIG"])
d = sys.stdin.buffer.read().split(b"\0")[:-1]
for k, v in zip(d[0::2], d[1::2]):
    k, v = k.decode(), v.decode().strip()
    if v == "-":
        uit.pop(k, None)
    else:
        uit[k] = v.lower() if k == "KIA_MERK" else v
print(json.dumps(uit))'
  unset HUIDIG
}
if stil gcloud secrets describe "$GEHEIM" --project="$PROJECT"; then
  antwoord=n
  if [ -t 0 ]; then read -rp "   Logins (opnieuw) invullen of wijzigen? [j/N] " antwoord; fi
  if [[ "$antwoord" =~ ^[jJyY] ]]; then
    huidig="$(gcloud secrets versions access latest --secret="$GEHEIM" --project="$PROJECT" 2>/dev/null || echo '{}')"
    vraag_logins "$huidig" | gcloud secrets versions add "$GEHEIM" --project="$PROJECT" --data-file=- >/dev/null
    # Oude versies uitzetten (niet wissen): zes actieve versies zijn gratis.
    gcloud secrets versions list "$GEHEIM" --project="$PROJECT" --filter="state=ENABLED" \
      --sort-by=~createTime --format='value(name)' | tail -n +2 | while read -r versie; do
      gcloud secrets versions disable "$versie" --secret="$GEHEIM" --project="$PROJECT" --quiet >/dev/null
    done
    info "opgeslagen; de volgende ronde gebruikt de nieuwe logins"
  else
    info "bestaan al en blijven zoals ze zijn"
  fi
else
  json='{}'
  info "Aanbevolen: koppel je accounts straks in de app (pagina Koppelingen); dan bewaart Thuis geen wachtwoorden."
  antwoord=n
  if [ -t 0 ]; then read -rp "   Toch hier logins invullen? [j/N] " antwoord; fi
  if [[ "$antwoord" =~ ^[jJyY] ]]; then json="$(vraag_logins '{}')"; fi
  printf '%s' "$json" | gcloud secrets create "$GEHEIM" --project="$PROJECT" --replication-policy=automatic --data-file=- >/dev/null
  info "aangemaakt"
fi
# Lezen, en nieuwe versies toevoegen en oude opruimen: de app (bij koppelen) en de verzamelaar
# (als tokens ververst zijn) werken de koppelingen zelf bij.
for rol in roles/secretmanager.secretAccessor roles/secretmanager.secretVersionManager; do
  gcloud secrets add-iam-policy-binding "$GEHEIM" --project="$PROJECT" \
    --member="serviceAccount:$RUN_SA" --role="$rol" --quiet >/dev/null
done
info "alleen thuis-run (app en verzamelaar) kan erbij"

stap "Artifact Registry $REPO met opruimregels"
if stil gcloud artifacts repositories describe "$REPO" --project="$PROJECT" --location="$REGIO"; then
  info "bestaat al"
else
  gcloud artifacts repositories create "$REPO" --project="$PROJECT" --location="$REGIO" \
    --repository-format=docker --description="Thuis: container-images"
fi
beleid="$(mktemp)"
cat >"$beleid" <<'JSON'
[
  {"name": "weg-na-7-dagen", "action": {"type": "Delete"}, "condition": {"tagState": "any", "olderThan": "7d"}},
  {"name": "laatste-5-houden", "action": {"type": "Keep"}, "mostRecentVersions": {"keepCount": 5}}
]
JSON
gcloud artifacts repositories set-cleanup-policies "$REPO" --project="$PROJECT" --location="$REGIO" \
  --policy="$beleid" --no-dry-run >/dev/null
rm -f "$beleid"
gcloud artifacts repositories add-iam-policy-binding "$REPO" --project="$PROJECT" --location="$REGIO" \
  --member="serviceAccount:$DEPLOY_SA" --role=roles/artifactregistry.writer --quiet >/dev/null
info "oude images na 7 dagen weg (de laatste 5 blijven); thuis-deploy mag pushen"

stap "Container-image"
IMAGE="$(gcloud run services describe "$APP" --project="$PROJECT" --region="$REGIO" \
  --format='value(spec.template.spec.containers[0].image)' 2>/dev/null || true)"
if [ -z "$IMAGE" ] || [ "$BOUW" = 1 ]; then
  IMAGE="$IMAGE_BASIS:$(git rev-parse --short HEAD)"
  gcloud auth configure-docker "$REGIO-docker.pkg.dev" --quiet >/dev/null
  docker build -t "$IMAGE" app
  docker push "$IMAGE"
else
  info "de app draait al op $IMAGE (een nieuwe versie: git pull && BOUW=1 bash deploy/setup-gcp.sh)"
fi

stap "Verzamelaar: Cloud Run-job $JOB"
# De kluis (logins en tokens) leest de job zelf via de API: dan ziet hij altijd de nieuwste
# koppelingen en kan hij ververste tokens terugschrijven.
gcloud run jobs deploy "$JOB" --project="$PROJECT" --region="$REGIO" --image="$IMAGE" \
  --service-account="$RUN_SA" --command=python --args=-m,thuis.verzamel --clear-secrets \
  --set-env-vars="THUIS_OPSLAG=bigquery,GCP_PROJECT=$PROJECT,BQ_DATASET=$DATASET,THUIS_KLUIS=secretmanager,THUIS_GEHEIM=$GEHEIM" \
  --cpu=1 --memory=512Mi --max-retries=0 --task-timeout=5m --labels=app=thuis --quiet
info "eerste ronde draaien (maakt ook de tabellen aan)…"
gcloud run jobs execute "$JOB" --project="$PROJECT" --region="$REGIO" --wait --quiet ||
  let_op "de eerste ronde had een fout; kijk straks op de pagina Bronnen welke bron"

stap "App: Cloud Run-service $APP achter IAP"
# ^;^ = puntkomma als scheidingsteken, want EMAILS kan komma's bevatten.
gcloud run deploy "$APP" --project="$PROJECT" --region="$REGIO" --image="$IMAGE" \
  --service-account="$RUN_SA" --no-allow-unauthenticated --iap \
  --set-env-vars="^;^THUIS_OPSLAG=bigquery;GCP_PROJECT=$PROJECT;BQ_DATASET=$DATASET;TOEGESTANE_EMAILS=$EMAILS;IAP_AUDIENCE=/projects/$NUMMER/locations/$REGIO/services/$APP;THUIS_KLUIS=secretmanager;THUIS_GEHEIM=$GEHEIM;THUIS_JOB=projects/$PROJECT/locations/$REGIO/jobs/$JOB" \
  --cpu=1 --memory=512Mi --min-instances=0 --max-instances=2 --concurrency=40 --timeout=60 \
  --labels=app=thuis --quiet
gcloud beta services identity create --service=iap.googleapis.com --project="$PROJECT" >/dev/null 2>&1 || true
gcloud run services add-iam-policy-binding "$APP" --project="$PROJECT" --region="$REGIO" \
  --member="serviceAccount:service-$NUMMER@gcp-sa-iap.iam.gserviceaccount.com" --role=roles/run.invoker --quiet >/dev/null
# Zonder Google Workspace-organisatie (los gmail-account) heeft IAP eerst een eigen inlogscherm
# nodig. Dat kan alleen eenmalig in de console; daarna lukt het toegang geven hieronder wel.
ORGANISATIE="$(gcloud projects describe "$PROJECT" --format='value(parent.type)')"
TOEGANG_OK=1
IFS=',' read -ra lijst <<<"$EMAILS"
for email in "${lijst[@]}"; do
  if gcloud iap web add-iam-policy-binding --project="$PROJECT" --member="user:$email" \
    --role=roles/iap.httpsResourceAccessor --region="$REGIO" --resource-type=cloud-run --service="$APP" --quiet >/dev/null 2>&1; then
    info "toegang voor $email"
  else
    TOEGANG_OK=0
  fi
done
if [ "$TOEGANG_OK" = 0 ]; then
  let_op "toegang geven lukte nog niet. Doe eenmalig deze stappen in de console en draai daarna dit script opnieuw:"
  info "1. Open https://console.cloud.google.com/run/detail/$REGIO/$APP?project=$PROJECT"
  info "2. Tabblad Security > onder Identity-Aware Proxy (IAP): Edit policy > Configure in IAP"
  info "3. Configure consent screen: kies External, vul de app-naam (Thuis) en je e-mailadres in"
  info "4. Kies Auto generate credentials en klik Save"
  [ "$ORGANISATIE" = organization ] || info "   (Dit project hangt niet onder een Google Workspace-organisatie; daarom is deze stap nodig.)"
fi

stap "Cloud Scheduler: elk kwartier een ronde"
gcloud run jobs add-iam-policy-binding "$JOB" --project="$PROJECT" --region="$REGIO" \
  --member="serviceAccount:$RUN_SA" --role=roles/run.invoker --quiet >/dev/null
schema_opties=(
  --project="$PROJECT" --location="$REGIO" --schedule="*/15 * * * *" --time-zone="Europe/Amsterdam"
  --uri="https://run.googleapis.com/v2/projects/$PROJECT/locations/$REGIO/jobs/$JOB:run"
  --http-method=POST --oauth-service-account-email="$RUN_SA"
)
if stil gcloud scheduler jobs describe "$SCHEMA" --project="$PROJECT" --location="$REGIO"; then
  gcloud scheduler jobs update http "$SCHEMA" "${schema_opties[@]}" --quiet >/dev/null
  info "bijgewerkt"
else
  gcloud scheduler jobs create http "$SCHEMA" "${schema_opties[@]}" --description="Thuis: verzamelaar" --quiet >/dev/null
  info "aangemaakt"
fi

stap "Automatische updates via GitHub Actions"
# Alleen voor wie de GitHub-repository beheert: deze stap laat die repository in dit project
# deployen. Wie andermans repository gebruikt, zegt nee en werkt bij met BOUW=1.
GITHUB="${GITHUB:-}"
if [ -z "$GITHUB" ] && [ -t 0 ]; then
  read -rp "   Ben jij beheerder van github.com/$GITHUB_REPO en moet die hier mogen deployen? [j/N] " GITHUB
fi
if ! [[ "$GITHUB" =~ ^[jJyY] ]]; then
  info "overgeslagen; bijwerken doe je met: git pull && BOUW=1 bash deploy/setup-gcp.sh"
  WIF_PROVIDER=""
else
if ! stil gcloud iam workload-identity-pools describe "$POOL" --project="$PROJECT" --location=global; then
  gcloud iam workload-identity-pools create "$POOL" --project="$PROJECT" --location=global --display-name="GitHub Actions"
fi
# Alleen workflows uit deze repository, en alleen vanaf main, mogen deployen.
provider_opties=(
  --project="$PROJECT" --location=global --workload-identity-pool="$POOL"
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref"
  --attribute-condition="assertion.repository == '$GITHUB_REPO' && assertion.ref == 'refs/heads/main'"
)
if stil gcloud iam workload-identity-pools providers describe "$PROVIDER" --project="$PROJECT" --location=global --workload-identity-pool="$POOL"; then
  gcloud iam workload-identity-pools providers update-oidc "$PROVIDER" "${provider_opties[@]}" --quiet >/dev/null
else
  # Weergavenaam: maximaal 32 tekens (de reponaam zelf is te lang).
  gcloud iam workload-identity-pools providers create-oidc "$PROVIDER" "${provider_opties[@]}" \
    --display-name="GitHub: deploy vanaf main" --issuer-uri="https://token.actions.githubusercontent.com"
fi
gcloud iam service-accounts add-iam-policy-binding "$DEPLOY_SA" --project="$PROJECT" --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/$NUMMER/locations/global/workloadIdentityPools/$POOL/attribute.repository/$GITHUB_REPO" \
  --quiet >/dev/null
gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:$DEPLOY_SA" --role=roles/run.developer \
  --condition=None --quiet >/dev/null
gcloud iam service-accounts add-iam-policy-binding "$RUN_SA" --project="$PROJECT" --role=roles/iam.serviceAccountUser \
  --member="serviceAccount:$DEPLOY_SA" --quiet >/dev/null
WIF_PROVIDER="projects/$NUMMER/locations/global/workloadIdentityPools/$POOL/providers/$PROVIDER"
info "thuis-deploy mag images pushen en app en verzamelaar bijwerken, niets anders"
fi

stap "Budgetalarm ($BUDGET per maand)"
BA="$(gcloud billing projects describe "$PROJECT" --format='value(billingAccountName)')"
BA="${BA#billingAccounts/}"
VALUTA="$(gcloud billing accounts describe "$BA" --format='value(currencyCode)' 2>/dev/null || true)"
VALUTA="${VALUTA:-EUR}"
if gcloud billing budgets list --billing-account="$BA" --filter="displayName=$BUDGETNAAM" --format='value(name)' 2>/dev/null | grep -q .; then
  info "bestaat al"
elif gcloud billing budgets create --billing-account="$BA" --display-name="$BUDGETNAAM" \
  --budget-amount="$BUDGET$VALUTA" --calendar-period=month --filter-projects="projects/$PROJECT" \
  --threshold-rule=percent=0.5 --threshold-rule=percent=0.9 --threshold-rule=percent=1.0 \
  --threshold-rule=percent=1.0,basis=forecasted-spend >/dev/null; then
  info "mail bij 50%, 90% en 100% van $BUDGET $VALUTA, en als de verwachting erboven komt"
else
  let_op "budget niet aangemaakt (daarvoor moet je beheerder van het betaalaccount zijn); doe het in de console onder Facturering > Budgetten"
fi

stap "Klaar"
info "App: https://$APP-$NUMMER.$REGIO.run.app  (inloggen met $EMAILS)"
info "Koppel daar je accounts: menu Koppelingen (Frank Energie, Easee, je auto, Google Chat)."
if [ "$TOEGANG_OK" = 0 ]; then
  let_op "je hebt nog geen toegang: doe de stappen bij 'App' hierboven en draai dit script daarna opnieuw"
fi
if [ -n "$WIF_PROVIDER" ]; then
  info ""
  info "GitHub-variabelen voor automatisch deployen (Settings > Secrets and variables > Actions > Variables):"
  variabelen=("GCP_PROJECT=$PROJECT" "GCP_REGIO=$REGIO" "GCP_WIF_PROVIDER=$WIF_PROVIDER" "GCP_DEPLOY_SA=$DEPLOY_SA")
  if command -v gh >/dev/null && gh auth status >/dev/null 2>&1; then
    for v in "${variabelen[@]}"; do gh variable set "${v%%=*}" --repo "$GITHUB_REPO" --body "${v#*=}"; done
    info "gezet met gh"
  else
    for v in "${variabelen[@]}"; do info "  ${v%%=*} = ${v#*=}"; done
    info "of met gh: gh variable set NAAM --repo $GITHUB_REPO --body WAARDE"
  fi
fi
