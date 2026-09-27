#!/usr/bin/env bash
# Lokale Änderungen mit GitHub abgleichen.
# Aufruf:  ./deploy.sh "Was geändert wurde"
set -euo pipefail
cd "$(dirname "$0")"

NACHRICHT="${1:-Aktualisierung}"
# Diese Dateien schreibt nur der Kalender-Bot auf GitHub – lokal nie hochladen
GENERIERT=(':(glob)docs/*/kalender.ics' ':(glob)docs/*/spiele.json' 'docs/teams.json')

echo "→ Lokal erzeugte Kalenderdateien verwerfen"
for muster in "${GENERIERT[@]}"; do
  git restore --staged --worktree -- "$muster" 2>/dev/null || true
  git clean -fq -- "$muster" 2>/dev/null || true
done

echo "→ mannschaften.json prüfen"
if ! python3 -m json.tool mannschaften.json >/dev/null; then
  echo "✗ mannschaften.json ist fehlerhaft (Komma oder Anführungszeichen prüfen). Nichts hochgeladen."
  exit 1
fi

echo "→ Eigene Änderungen speichern"
git add -A
if git diff --cached --quiet; then
  echo "  keine eigenen Änderungen"
else
  git commit -q -m "$NACHRICHT"
  git --no-pager log -1 --stat --format="  %s"
fi

echo "→ Neuesten Stand von GitHub holen"
git pull --rebase -q

echo "→ Hochladen"
git push -q
echo "✓ Fertig. Die Seite ist in ca. 1 Minute aktualisiert."
echo "  Bei Änderungen an mannschaften.json startet der Kalender-Abgleich automatisch (Tab „Actions“)."
