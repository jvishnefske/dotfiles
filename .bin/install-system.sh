#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== System packages installer (requires sudo) ==="

uvx --from ansible-core ansible-playbook "$SCRIPT_DIR/system.yml" --ask-become-pass
uvx --from ansible-core ansible-playbook "$SCRIPT_DIR/install-system.yml" --ask-become-pass -e "install_github_cli=true"

echo ""
echo "System packages installation complete!"
