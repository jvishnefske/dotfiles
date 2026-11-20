# ~/.profile — environment shared by sh, bash and zsh.
# shellcheck shell=sh
# POSIX sh only (dash reads this at login). Safe to source more than once:
# each directory is added to PATH at most once, and only if it exists.

path_prepend() {
    [ -d "$1" ] || return 0
    case ":$PATH:" in *":$1:"*) ;; *) PATH="$1${PATH:+:$PATH}" ;; esac
}
path_append() {
    [ -d "$1" ] || return 0
    case ":$PATH:" in *":$1:"*) ;; *) PATH="${PATH:+$PATH:}$1" ;; esac
}

# Toolchains (lower priority than system tools)
path_append "$HOME/jdk-current/bin"
path_append "$HOME/go-current/bin"
path_append /opt/rocm-6.2.0/lib/llvm/bin
for d in "$HOME"/.local/arm-gnu-toolchain-*/bin "$HOME"/.local/node-v*/bin; do
    path_append "$d"
done

# Vcpkg (installed by ~/.bin/setup_vcpkg.yml)
if [ -d "$HOME/.local/vcpkg" ]; then
    export VCPKG_ROOT="$HOME/.local/vcpkg"
    path_prepend "$VCPKG_ROOT"
fi

# User tool bins (win over system): go install, cargo/rustup, uv/pip/npm
path_prepend "$HOME/go/bin"
path_prepend "$HOME/.cargo/bin"
path_prepend "$HOME/.local/bin"
path_prepend "$HOME/bin"
export PATH

export EDITOR=vim

# Machine-specific settings (untracked)
# shellcheck source=/dev/null
[ -f "$HOME/.profile.local" ] && . "$HOME/.profile.local"
