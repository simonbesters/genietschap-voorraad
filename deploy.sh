  #!/usr/bin/env bash
set -euo pipefail

# === Configuratie ===
SSH_USER="deb112860"
SSH_HOST="voorraad.hetgenietschap.eu"  # pas aan als SSH via ander adres gaat
REMOTE_DIR="/home/deb112860/domains/voorraad.hetgenietschap.eu/public_html"
VENV_ACTIVATE="/home/deb112860/virtualenv/domains/voorraad.hetgenietschap.eu/public_html/3.13/bin/activate"
# === Bestanden uploaden via rsync ===
echo "▸ Bestanden uploaden..."
rsync -avz --delete \
    --exclude '.htaccess' \
    --exclude '.git' \
    --exclude '.gitignore' \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    --exclude '.env' \
    --exclude '*.db' \
    --exclude 'deploy.sh' \
    --exclude '.claude' \
    --exclude '.venv' \
    --exclude 'venv' \
    --exclude '.idea' \
    --exclude 'instance' \
    --exclude 'CLAUDE.md' \
    ./ "${SSH_USER}@${SSH_HOST}:${REMOTE_DIR}/"

# === Op de server: dependencies installeren + herstarten ===
echo "▸ Dependencies installeren en app herstarten..."
ssh "${SSH_USER}@${SSH_HOST}" bash -s <<EOF
    source ${VENV_ACTIVATE}
    cd ${REMOTE_DIR}
    pip install -q -r requirements.txt
    mkdir -p tmp
    touch tmp/restart.txt
    echo "✓ App herstart"
EOF

echo "✓ Deploy klaar → https://voorraad.hetgenietschap.eu"
