@echo off
setlocal
echo ========================================================
echo   [NAMI] Reconstruction et Mise a Jour du Service
echo ========================================================
echo.

echo [1/4] Verification des mises a jour Git de Nami...
git pull 2>nul
if %errorlevel% neq 0 (
    echo [Info] Git pull ignore ou depot deja a jour.
)

echo.
echo [2/4] Reconstruction de l'image Docker (sans cache)...
docker compose build --no-cache

if %errorlevel% neq 0 (
    echo.
    echo [Erreur] Echec du build Docker. Verifiez votre connexion ou Docker daemon.
    pause
    exit /b 1
)

echo.
echo [3/4] Demarrage du conteneur Nami...
docker compose up -d

echo.
echo [4/4] Nettoyage des anciennes images Docker orphelines...
docker image prune -f

echo.
echo ========================================================
echo   [Succes] Nami est reconstruit et operationnel !
echo   Acces web : http://localhost:8070
echo   (Vos utilisateurs, donnees et telechargements sont preserves)
echo ========================================================
echo.
pause
