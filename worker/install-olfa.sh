#!/usr/bin/env bash
set -euo pipefail
ROOT="${HOME}/ai/sprite-gen"
mkdir -p "$ROOT/data" "$HOME/.config/systemd/user"
cp worker/sprite-gen.service "$HOME/.config/systemd/user/sprite-gen.service"
if command -v go >/dev/null; then
  go build -o "$ROOT/sprite-gen" ./cmd/sprite-gen
else
  echo "go not found; copy a linux amd64 sprite-gen binary to $ROOT/sprite-gen" >&2
fi
install -m 0755 worker/run_job.py "$ROOT/worker/run_job.py"
systemctl --user daemon-reload
systemctl --user enable --now sprite-gen.service
systemctl --user status sprite-gen.service --no-pager || true
echo "worker on http://0.0.0.0:8787"
