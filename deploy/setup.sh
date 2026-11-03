#!/usr/bin/env bash
# One-shot setup of PDF Tool on a fresh Ubuntu/Debian cloud VM (x86_64 or arm64).
# Run as a normal user with sudo rights:  bash setup.sh
# Re-running is safe: it updates the code, rebuilds and restarts the service.
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/ignit-fury/pdf-tool.git}"
BRANCH="${BRANCH:-feat/document-viewer-editor}"
APP_DIR="${APP_DIR:-$HOME/pdf-tool}"
PORT="${PORT:-8000}"
NODE_MAJOR="${NODE_MAJOR:-22}"
SERVICE=pdf-tool

[ "$(id -u)" -ne 0 ] || { echo "Run as a normal user, not root (sudo is used where needed)."; exit 1; }
command -v apt-get >/dev/null || { echo "This script supports Debian/Ubuntu (apt) only."; exit 1; }

echo "==> System packages"
sudo apt-get update -y
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
  git curl ca-certificates xz-utils build-essential

echo "==> uv (Python manager) and Python 3.13"
export PATH="$HOME/.local/bin:$PATH"
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.13

echo "==> Node.js ${NODE_MAJOR} (client build only)"
if ! command -v node >/dev/null || [ "$(node -p 'process.versions.node.split(".")[0]')" != "$NODE_MAJOR" ]; then
  case "$(uname -m)" in x86_64) arch=x64 ;; aarch64|arm64) arch=arm64 ;; *) echo "Unsupported CPU $(uname -m)"; exit 1 ;; esac
  base="https://nodejs.org/dist/latest-v${NODE_MAJOR}.x"
  file="$(curl -fsSL "$base/" | grep -o "node-v[0-9.]*-linux-${arch}.tar.xz" | head -1)"
  curl -fsSL "$base/$file" | sudo tar -xJ -C /usr/local --strip-components=1
fi

echo "==> Code"
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" fetch origin "$BRANCH"
  git -C "$APP_DIR" checkout "$BRANCH"
  git -C "$APP_DIR" reset --hard "origin/$BRANCH"
else
  git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"

echo "==> Python dependencies (production set)"
uv sync --frozen --no-dev --no-install-project

echo "==> Client build"
# vite is a devDependency; a shell-wide NODE_ENV=production makes npm omit it.
(cd client && NODE_ENV=development npm ci --include=dev && npm run build)

echo "==> Service"
sudo tee "/etc/systemd/system/${SERVICE}.service" >/dev/null <<UNIT
[Unit]
Description=PDF Tool
After=network-online.target
Wants=network-online.target

[Service]
User=$USER
WorkingDirectory=$APP_DIR
Environment=PDF_TOOL_ENV=production PDF_TOOL_SCRATCH_ROOT=/dev/shm PYTHONDONTWRITEBYTECODE=1
ExecStart=$APP_DIR/.venv/bin/python -m uvicorn server.app:app --host 0.0.0.0 --port $PORT --no-access-log
Restart=on-failure
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE" >/dev/null
sudo systemctl restart "$SERVICE"

sleep 3
if curl -fsS -o /dev/null "http://127.0.0.1:${PORT}/"; then
  echo "OK: PDF Tool is running on port ${PORT}."
  echo "Open that port in the cloud firewall / security group to reach it from outside."
  echo "Logs: journalctl -u ${SERVICE} -f      Memory: free -h"
else
  echo "Service did not answer. Check: journalctl -u ${SERVICE} -n 50"; exit 1
fi
