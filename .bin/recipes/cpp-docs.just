# C++ documentation in Vim. Imported by ../justfile, so run as `just cpp-docs`.
#
#   clangd : latest upstream clangd (distro builds lag; newer hover renders Doxygen)
#            into ~/.local/share/clangd/<ver>, linked as ~/.local/bin/clangd.
#   cppman : cppreference pages as man pages; common.vim maps `gK` to it in C/C++.

clangd_version := env_var_or_default("CLANGD_VERSION", "latest")
clangd_root    := env_var("HOME") + "/.local/share/clangd"
local_bin      := env_var("HOME") + "/.local/bin"

cpp-docs: clangd cppman

clangd:
    #!/usr/bin/env bash
    set -eu
    ver="{{clangd_version}}"
    if [ "$ver" = latest ]; then
        ver="$(curl -fsSL https://api.github.com/repos/clangd/clangd/releases/latest \
            | sed -n 's/.*"tag_name": *"\([^"]*\)".*/\1/p')"
    fi
    if [ -z "$ver" ]; then
        echo "Error: could not determine the latest clangd release."
        exit 1
    fi
    dest="{{clangd_root}}/$ver"
    if [ ! -x "$dest/bin/clangd" ]; then
        tmp="$(mktemp -d)"
        trap 'rm -rf "$tmp"' EXIT
        echo "Downloading clangd $ver..."
        curl -fsSL -o "$tmp/clangd.zip" \
            "https://github.com/clangd/clangd/releases/download/$ver/clangd-linux-$ver.zip"
        unzip -q "$tmp/clangd.zip" -d "$tmp"
        mkdir -p "{{clangd_root}}"
        rm -rf "$dest"
        mv "$tmp/clangd_$ver" "$dest"
    fi
    mkdir -p "{{local_bin}}"
    ln -sfn "$dest/bin/clangd" "{{local_bin}}/clangd"
    "{{local_bin}}/clangd" --version | head -1
    case ":$PATH:" in
        *":{{local_bin}}:"*) ;;
        *) echo "Warning: {{local_bin}} is not on PATH; coc-clangd will still use the system clangd." ;;
    esac

cppman:
    #!/usr/bin/env bash
    set -eu
    if ! command -v cppman &>/dev/null; then
        if ! command -v uv &>/dev/null; then
            echo "Error: uv not found; run 'just install-uv' first."
            exit 1
        fi
        uv tool install cppman
    fi
    cppman -s cppreference.com >/dev/null
    echo "cppman: $(command -v cppman) (source: cppreference.com)"
    echo "Pages download on first lookup; run 'cppman -c' once to cache everything offline."
