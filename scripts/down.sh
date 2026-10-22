#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TF_DIR="$REPO_ROOT/infra/envs/dev"

cd "$TF_DIR"

echo "Reviewing selected resources for destruction..."

terraform plan -destroy \
  -target=module.compute \
  -target=module.migrate \
  -target=module.data \
  -target=module.network \
  -out=down.tfplan

echo "Plan saved to down.tfplan."
echo "Review it before applying."
