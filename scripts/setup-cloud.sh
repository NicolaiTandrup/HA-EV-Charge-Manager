#!/usr/bin/env bash
set -euo pipefail
command -v node >/dev/null  # Required for real Node-RED parity tests.
export UV_CACHE_DIR=/workspace/.cache/uv
export UV_PYTHON_INSTALL_DIR=/workspace/.local/python
uv python install --no-bin 3.14.8
if [ ! -x /workspace/ev-manager-venv/bin/python ]; then
  uv venv --python 3.14.8 /workspace/ev-manager-venv
fi
cd /workspace/HA-EV-Charge-Manager
uv pip sync --python /workspace/ev-manager-venv/bin/python --require-hashes requirements-dev.lock
/workspace/ev-manager-venv/bin/ruff check custom_components tests
/workspace/ev-manager-venv/bin/ruff format --check custom_components tests
/workspace/ev-manager-venv/bin/python -m pytest
