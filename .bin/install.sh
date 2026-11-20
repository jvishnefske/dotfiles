#!/usr/bin/env bash
# Bootstrap dotfiles as a bare git repo checked out into $HOME, then run the
# user-level ansible playbook. Safe to re-run.
#
#   curl -fsSL https://raw.githubusercontent.com/jvishnefske/dotfiles/main/.bin/install.sh | bash
#
# Environment overrides:
#   DOTFILES_REPO    repo to clone (default: GitHub; CI points it at the checkout)
#   DOTFILES_BRANCH  branch to check out (default: the repo's default branch)
#   SKIP_ANSIBLE=1   only check out the dotfiles
set -euo pipefail

DOTFILES_REPO="${DOTFILES_REPO:-https://github.com/jvishnefske/dotfiles.git}"
DOTFILES_DIR="$HOME/.dotfiles"
BACKUP_DIR="$HOME/.dotfiles-backup"

dotfiles() { git --git-dir="$DOTFILES_DIR" --work-tree="$HOME" "$@"; }

clone_bare_repo() {
    if git --git-dir="$DOTFILES_DIR" rev-parse --is-bare-repository &>/dev/null; then
        echo "Bare repo already at $DOTFILES_DIR."
        return
    fi
    if [ -e "$DOTFILES_DIR" ]; then
        echo "Error: $DOTFILES_DIR exists but is not a bare repo; move it aside." >&2
        exit 1
    fi
    git clone --bare ${DOTFILES_BRANCH:+--branch "$DOTFILES_BRANCH"} "$DOTFILES_REPO" "$DOTFILES_DIR"
    dotfiles config status.showUntrackedFiles no
}

# Move files that would be overwritten into $BACKUP_DIR, then check out.
checkout_dotfiles() {
    if dotfiles checkout 2>/dev/null; then
        return
    fi
    echo "Backing up conflicting files to $BACKUP_DIR..."
    { dotfiles checkout 2>&1 || true; } | awk '/^\t/ {print $1}' | while read -r file; do
        mkdir -p "$BACKUP_DIR/$(dirname "$file")"
        mv "$HOME/$file" "$BACKUP_DIR/$file"
        echo "  $file"
    done
    dotfiles checkout
}

# A bare-repo checkout does not fetch submodules (oh-my-zsh lives in one).
init_submodules() {
    (cd "$HOME" && dotfiles submodule update --init --recursive) \
        || echo "Warning: submodule update failed; zsh will lack oh-my-zsh." >&2
}

ensure_uv() {
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    command -v uv &>/dev/null && return
    echo "Installing uv (user-local, no sudo)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    command -v uv &>/dev/null || { echo "Error: uv install failed." >&2; exit 1; }
}

run_ansible() {
    # Prefer the playbook next to this script (a checkout under test), then
    # the one just checked out into $HOME (curl | bash has no script dir).
    local here playbook
    here="$(cd "$(dirname "${BASH_SOURCE[0]:-.}")" && pwd)"
    playbook="$here/install.yml"
    [ -f "$playbook" ] || playbook="$HOME/.bin/install.yml"
    # The full 'ansible' package bundles community.general (npm/cargo/homebrew).
    uvx --from ansible ansible-playbook "$playbook" "$@"
}

clone_bare_repo
checkout_dotfiles
init_submodules

if [ "${SKIP_ANSIBLE:-0}" != 1 ]; then
    ensure_uv
    run_ansible "$@"
fi

echo
echo "Done. Open a new shell; manage files with: dotfiles status"
echo "System packages (needs sudo): ~/.bin/install-system.sh"
