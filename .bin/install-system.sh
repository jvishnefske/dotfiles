#!/usr/bin/env bash
# Install system packages and the GitHub CLI (requires sudo).
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
uvx --from ansible-core ansible-playbook "$here/system.yml" --ask-become-pass "$@"
