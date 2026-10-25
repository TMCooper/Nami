#!/usr/bin/env bash
set -e

echo "========================================================"
echo "  [NAMI] Reconstruction et Mise à Jour du Service"
echo "========================================================"
echo ""

echo "[1/4] Vérification des mises à jour Git de Nami..."
git pull || true

echo ""
echo "[2/4] Reconstruction de l'image Docker (sans cache)..."
docker compose build --no-cache

echo ""
echo "[3/4] Démarrage du conteneur Nami..."
docker compose up -d

echo ""
echo "[4/4] Nettoyage des anciennes images Docker orphelines..."
docker image prune -f

echo ""
echo "========================================================"
echo "  [Succès] Nami est reconstruit et opérationnel !"
echo "  Accès web : http://localhost:8070"
echo "  (Vos utilisateurs, base de données et téléchargements sont préservés)"
echo "========================================================"
