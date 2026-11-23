# coc.nvim support recipes. Imported by ../justfile, so run as `just coc-node`.

# Node for coc.nvim: coc needs global `crypto` (Node 19+), and the system node may be older.
# Installs the nvm Node version (default 24) if missing, then records its binary path in
# coc_node_file so common.vim can point g:coc_node_path at it.
coc_node_version := env_var_or_default("COC_NODE_VERSION", "24")
coc_node_file    := env_var("HOME") + "/.vim/coc-node-path"

coc-node:
    #!/usr/bin/env bash
    set -eu
    export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
    if [ ! -s "$NVM_DIR/nvm.sh" ]; then
        echo "Error: nvm not found at $NVM_DIR; install nvm first."
        exit 1
    fi
    # shellcheck source=/dev/null
    . "$NVM_DIR/nvm.sh"
    nvm install "{{coc_node_version}}" >/dev/null
    bin="$(nvm which "{{coc_node_version}}")"
    if ! "$bin" -e 'process.exit(typeof globalThis.crypto === "object" ? 0 : 1)'; then
        echo "Error: $bin has no global crypto; coc.nvim will not start."
        exit 1
    fi
    mkdir -p "$(dirname "{{coc_node_file}}")"
    printf '%s\n' "$bin" > "{{coc_node_file}}"
    echo "coc.nvim node: $bin (recorded in {{coc_node_file}})"
