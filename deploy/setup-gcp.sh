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
#   GITHUB_REPO  standaard frankherling95-sketch/Home-Assistant
#   BUDGET       maandbudget voor het alarm, standaard 1 (in de valuta van je betaalaccount)
#   BOUW=1       ook een nieuw image bouwen als de app al draait
#
# Zie docs/deploy.md voor uitleg en kosten.
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

stap "Geheim $GEHEIM (alle wachtwoorden in één JSON)"
if stil gcloud secrets describe "$GEHEIM" --project="$PROJECT"; then
  info "bestaat al; aanpassen: zie docs/deploy.md (Wachtwoorden wijzigen)"
else
  json='{}'
  if [ -t 0 ]; then
    info "Vul in wat je hebt; Enter = overslaan. Wachtwoorden zie je niet tijdens het typen."
    declare -A waarden=()
    for sleutel in FRANK_EMAIL FRANK_WACHTWOORD EASEE_GEBRUIKER EASEE_WACHTWOORD KIA_GEBRUIKER KIA_WACHTWOORD KIA_PIN KIA_MERK GOOGLE_CHAT_WEBHOOK; do
      case "$sleutel" in
        *WACHTWOORD|*PIN|*WEBHOOK) read -rsp "   $sleutel: " waarde; echo ;;
        *) read -rp "   $sleutel: " waarde ;;
      esac
      [ -n "$waarde" ] && waarden[$sleutel]="$waarde"
    done
    json="$(for k in "${!waarden[@]}"; do printf '%s\0%s\0' "$k" "${waarden[$k]}"; done |
      python3 -c 'import json,sys; d=sys.stdin.buffer.read().split(b"\0")[:-1]; print(json.dumps({d[i].decode(): d[i+1].decode() for i in range(0,len(d),2)}))')"
  fi
  printf '%s' "$json" | gcloud secrets create "$GEHEIM" --project="$PROJECT" --replication-policy=automatic --data-file=-
fi
gcloud secrets add-iam-policy-binding "$GEHEIM" --project="$PROJECT" \
  --member="serviceAccount:$RUN_SA" --role=roles/secretmanager.secretAccessor --quiet >/dev/null
info "alleen thuis-run (de verzamelaar) kan het lezen"

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
  info "de app draait al op $IMAGE (BOUW=1 voor een nieuw image; normaal doet GitHub dat)"
fi

stap "Verzamelaar: Cloud Run-job $JOB"
gcloud run jobs deploy "$JOB" --project="$PROJECT" --region="$REGIO" --image="$IMAGE" \
  --service-account="$RUN_SA" --command=python --args=-m,thuis.verzamel \
  --set-secrets="THUIS_GEHEIMEN=$GEHEIM:latest" \
  --set-env-vars="THUIS_OPSLAG=bigquery,GCP_PROJECT=$PROJECT,BQ_DATASET=$DATASET" \
  --cpu=1 --memory=512Mi --max-retries=0 --task-timeout=5m --labels=app=thuis --quiet
info "eerste ronde draaien (maakt ook de tabellen aan)…"
gcloud run jobs execute "$JOB" --project="$PROJECT" --region="$REGIO" --wait --quiet ||
  let_op "de eerste ronde had een fout; kijk straks op de pagina Bronnen welke bron"

stap "App: Cloud Run-service $APP achter IAP"
# ^;^ = puntkomma als scheidingsteken, want EMAILS kan komma's bevatten.
gcloud run deploy "$APP" --project="$PROJECT" --region="$REGIO" --image="$IMAGE" \
  --service-account="$RUN_SA" --no-allow-unauthenticated --iap \
  --set-env-vars="^;^THUIS_OPSLAG=bigquery;GCP_PROJECT=$PROJECT;BQ_DATASET=$DATASET;TOEGESTANE_EMAILS=$EMAILS;IAP_AUDIENCE=/projects/$NUMMER/locations/$REGIO/services/$APP" \
  --cpu=1 --memory=512Mi --min-instances=0 --max-instances=2 --concurrency=40 --timeout=60 \
  --labels=app=thuis --quiet
gcloud beta services identity create --service=iap.googleapis.com --project="$PROJECT" >/dev/null 2>&1 || true
gcloud run services add-iam-policy-binding "$APP" --project="$PROJECT" --region="$REGIO" \
  --member="serviceAccount:service-$NUMMER@gcp-sa-iap.iam.gserviceaccount.com" --role=roles/run.invoker --quiet >/dev/null
IFS=',' read -ra lijst <<<"$EMAILS"
for email in "${lijst[@]}"; do
  gcloud iap web add-iam-policy-binding --project="$PROJECT" --member="user:$email" \
    --role=roles/iap.httpsResourceAccessor --region="$REGIO" --resource-type=cloud-run --service="$APP" --quiet >/dev/null
  info "toegang voor $email"
done

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

stap "GitHub Actions: Workload Identity Federation (geen sleutels)"
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
URL="$(gcloud run services describe "$APP" --project="$PROJECT" --region="$REGIO" --format='value(status.url)')"
info "App: $URL  (inloggen met $EMAILS)"
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
