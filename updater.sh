#!/usr/bin/env bash
# Mises a jour de Nami depuis l'interface (Parametres > Mises a jour), pour l'installation Docker.
#
# Le conteneur n'a ni le depot git ni vos identifiants : cet outil tourne sur la machine hote, dans le
# dossier de Nami. Il indique a Nami la version disponible (data/nami-update/state.json) et lance
# rebuild.sh (git pull + nouvelle image) quand l'interface le demande (data/nami-update/request).
#
#   ./updater.sh            (laisser tourner, par exemple dans tmux / screen)
#
# En service systemd (demarre avec la machine) : /etc/systemd/system/nami-updater.service
#   [Unit]
#   Description=Nami updater
#   After=docker.service
#   [Service]
#   WorkingDirectory=/chemin/vers/Nami
#   ExecStart=/chemin/vers/Nami/updater.sh
#   User=<utilisateur du depot, membre du groupe docker>
#   Restart=always
#   [Install]
#   WantedBy=multi-user.target
# puis : sudo systemctl enable --now nami-updater

cd "$(dirname "$0")" || exit 1
DIR="data/nami-update"
CHECK_EVERY="${CHECK_EVERY:-600}"   # secondes entre deux verifications du depot
mkdir -p "$DIR"

STATE="idle"
MESSAGE=""
LAST_CHECK=0

write_state() {
  local branch local_sha remote_sha
  branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)"
  local_sha="$(git rev-parse HEAD 2>/dev/null)"
  remote_sha="$(git rev-parse "origin/$branch" 2>/dev/null)"
  printf '{"branch":"%s","local":"%s","remote":"%s","state":"%s","message":"%s","checked_at":%s,"alive_at":%s}\n' \
    "$branch" "$local_sha" "$remote_sha" "$STATE" "$MESSAGE" "$LAST_CHECK" "$(date +%s)" > "$DIR/state.json.tmp" \
    && mv -f "$DIR/state.json.tmp" "$DIR/state.json"
}

echo "[Nami updater] Pret (verification toutes les ${CHECK_EVERY}s). Ctrl+C pour arreter."
while true; do
  NOW="$(date +%s)"
  if [ $((NOW - LAST_CHECK)) -ge "$CHECK_EVERY" ]; then
    git fetch -q origin 2>/dev/null || true
    LAST_CHECK="$NOW"
  fi
  if [ -f "$DIR/request" ]; then
    rm -f "$DIR/request"
    STATE="updating"; MESSAGE="Mise a jour en cours"; write_state
    echo "[Nami updater] Mise a jour demandee depuis l'interface..."
    if ./rebuild.sh > "$DIR/last-update.log" 2>&1; then
      STATE="done"; MESSAGE="Nami mis a jour"
    else
      STATE="error"; MESSAGE="Echec de la mise a jour (voir data/nami-update/last-update.log)"
    fi
    git fetch -q origin 2>/dev/null || true
    LAST_CHECK="$(date +%s)"
    echo "[Nami updater] $MESSAGE"
  fi
  write_state
  sleep 5
done
