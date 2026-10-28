#!/usr/bin/env bash
# Install as /opt/cu3rd-self-service/reconcile.sh; not executed from unreviewed PRs.
set -euo pipefail
umask 077
export PATH=/opt/cu3rd-self-service/bin:/usr/local/bin:/usr/bin:/bin
export TF_IN_AUTOMATION=1
export TF_INPUT=0
exec 9>/var/lib/cu3rd-self-service/reconcile.lock
flock -n 9 || exit 0
set -a
source /etc/cu3rd-self-service/runtime.env
if [[ -f /etc/cu3rd-self-service/cloudflare.env ]]; then source /etc/cu3rd-self-service/cloudflare.env; fi
set +a
cd /opt/cu3rd-self-service/repo
git fetch --quiet origin master
git checkout --quiet --detach origin/master
revision=$(git rev-parse HEAD)
# Reconcile every hour too, so external drift is eventually repaired.
last=$(cat /var/lib/cu3rd-self-service/applied-revision 2>/dev/null || true)
if [[ "$revision" == "$last" ]] && find /var/lib/cu3rd-self-service/applied-revision -mmin -60 | read -r _; then exit 0; fi
/opt/cu3rd-self-service/venv/bin/python scripts/validate.py
export TF_VAR_chart_revision="$revision"
export TF_VAR_postgres_host=$(kubectl -n postgres get service pg-grm-rw -o jsonpath='{.spec.clusterIP}')
export TF_VAR_postgres_port=5432
trap 'rm -f /var/lib/cu3rd-self-service/apply.tfplan' EXIT
tofu init -input=false -backend-config=/etc/cu3rd-self-service/backend.hcl
tofu validate
tofu plan -lock-timeout=60s -out=/var/lib/cu3rd-self-service/apply.tfplan
tofu show -json /var/lib/cu3rd-self-service/apply.tfplan | /opt/cu3rd-self-service/venv/bin/python scripts/check-plan.py
tofu apply -input=false -lock-timeout=60s /var/lib/cu3rd-self-service/apply.tfplan
printf '%s\n' "$revision" > /var/lib/cu3rd-self-service/applied-revision
