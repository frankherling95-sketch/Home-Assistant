#!/usr/bin/env bash
# Koppelt een bestaande /config eenmalig aan deze repo — zonder iets te wissen.
#
# Uitvoeren in de Home Assistant-app "Terminal & SSH":
#   curl -fsSL https://raw.githubusercontent.com/frankherling95-sketch/Home-Assistant/main/tools/koppel-git.sh | bash
#
# Waarom niet direct de Git pull-app laten clonen? Die wist bij de eerste keer
# alle .yaml-bestanden die niet in de repo staan, waaronder automations.yaml met
# je UI-automatiseringen. Dit script overschrijft alleen bestanden die wél in de
# repo staan en bewaart van configuration.yaml eerst een kopie.
set -euo pipefail

REPO="${1:-https://github.com/frankherling95-sketch/Home-Assistant.git}"
CONFIG="${CONFIG:-/config}"
cd "$CONFIG"

if [ -d .git ]; then
  echo "Al gekoppeld aan: $(git remote get-url origin)"; exit 0
fi

stamp="$(date +%Y%m%d-%H%M%S)"
backup="$CONFIG/backup-voor-git-$stamp"
mkdir -p "$backup"
for f in configuration.yaml automations.yaml scripts.yaml scenes.yaml; do
  [ -f "$f" ] && cp "$f" "$backup/"
done
echo "Kopie gemaakt in $backup"

git init -q -b main
git remote add origin "$REPO"
git fetch -q origin main
# -f: bestanden uit de repo winnen; bestanden die niet in de repo staan blijven staan.
git checkout -q -f -B main origin/main
git branch -q -u origin/main main

# UI-beheerde bestanden staan niet in git maar configuration.yaml verwacht ze.
[ -f automations.yaml ] || echo "[]" > automations.yaml
[ -f scripts.yaml ]     || echo "{}" > scripts.yaml
[ -f scenes.yaml ]      || echo "[]" > scenes.yaml

echo
if [ -f "$backup/configuration.yaml" ] && ! cmp -s "$backup/configuration.yaml" configuration.yaml; then
  echo "Je oude configuration.yaml week af van die in de repo. Verschil (- oud, + nieuw):"
  diff -u "$backup/configuration.yaml" configuration.yaml || true
  echo
  echo "Stuur regels die je kwijt bent door, dan komen ze in een package."
fi

if command -v ha >/dev/null 2>&1; then
  echo "Configuratie controleren…"
  ha core check && echo "OK. Herstart Home Assistant: ha core restart"
fi
