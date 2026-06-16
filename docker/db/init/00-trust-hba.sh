#!/bin/bash
# Dev-only: relax pg_hba to trust so Windows Docker bridge avoids
# SCRAM-SHA-256 handshake issues. Runs once on first init.
set -euo pipefail
HBA="${PGDATA}/pg_hba.conf"
echo "Overwriting ${HBA} with dev trust rules"
cat > "${HBA}" <<'EOF'
local   all             all                                     trust
host    all             all             127.0.0.1/32            trust
host    all             all             ::1/128                 trust
host    all             all             0.0.0.0/0               trust
host    all             all             ::/0                    trust
local   replication     all                                     trust
host    replication     all             127.0.0.1/32            trust
host    replication     all             ::1/128                 trust
EOF
chown postgres:postgres "${HBA}"
chmod 0644 "${HBA}"
