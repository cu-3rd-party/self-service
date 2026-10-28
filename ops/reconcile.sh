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
kubectl -n postgres port-forward --address=127.0.0.1 service/pg-grm-rw 15432:5432 >/var/lib/cu3rd-self-service/port-forward.log 2>&1 &
forward_pid=$!
trap 'kill "$forward_pid" 2>/dev/null || true; rm -f /var/lib/cu3rd-self-service/apply.tfplan' EXIT
for attempt in {1..30}; do
  if (echo > /dev/tcp/127.0.0.1/15432) 2>/dev/null; then break; fi
  kill -0 "$forward_pid"
  sleep 1
done
tofu init -input=false -backend-config=/etc/cu3rd-self-service/backend.hcl
tofu validate
tofu plan -lock-timeout=60s -out=/var/lib/cu3rd-self-service/apply.tfplan
tofu show -json /var/lib/cu3rd-self-service/apply.tfplan | /opt/cu3rd-self-service/venv/bin/python scripts/check-plan.py
tofu apply -input=false -lock-timeout=60s /var/lib/cu3rd-self-service/apply.tfplan
printf '%s\n' "$revision" > /var/lib/cu3rd-self-service/applied-revision
