#!/bin/bash
set -e

# Bare repository dotfiles management
# Usage: curl -Lks https://raw.githubusercontent.com/jvishnefske/dotfiles/main/install.sh | bash

DOTFILES_REPO="https://github.com/jvishnefske/dotfiles.git"
DOTFILES_DIR="$HOME/.dotfiles"
BACKUP_DIR="$HOME/.dotfiles-backup"
# shellcheck disable=SC2016
DOTFILES_ALIAS='alias dotfiles="git --git-dir=$HOME/.dotfiles --work-tree=$HOME"'

# ---------- Bare repo setup ----------

setup_bare_repo() {
    if [ -d "$DOTFILES_DIR" ] && git --git-dir="$DOTFILES_DIR" rev-parse --is-bare-repository &>/dev/null; then
        echo "Bare repo already exists at $DOTFILES_DIR, skipping clone."
        return 0
    fi

    if [ -d "$DOTFILES_DIR" ]; then
        echo "Error: $DOTFILES_DIR exists but is not a bare repo."
        echo "Please remove or rename it before running this script."
        exit 1
    fi

    echo "Cloning dotfiles bare repo into $DOTFILES_DIR..."
    git clone --bare "$DOTFILES_REPO" "$DOTFILES_DIR"
}

configure_bare_repo() {
    git --git-dir="$DOTFILES_DIR" --work-tree="$HOME" config status.showUntrackedFiles no
}

checkout_dotfiles() {
    echo "Checking out dotfiles into $HOME..."
    if git --git-dir="$DOTFILES_DIR" --work-tree="$HOME" checkout 2>/dev/null; then
        echo "Checkout successful."
    else
        echo "Checkout conflicts detected. Backing up existing files to $BACKUP_DIR..."
        mkdir -p "$BACKUP_DIR"

        # Collect conflicting files and back them up
        git --git-dir="$DOTFILES_DIR" --work-tree="$HOME" checkout 2>&1 \
            | grep -E "^\s+" \
            | awk '{print $1}' \
            | while read -r file; do
                dest="$BACKUP_DIR/$file"
                mkdir -p "$(dirname "$dest")"
                mv "$HOME/$file" "$dest"
                echo "  Backed up: $file"
            done

        # Retry checkout
        git --git-dir="$DOTFILES_DIR" --work-tree="$HOME" checkout
        echo "Checkout successful after backing up conflicts."
    fi
}

# ---------- Shell alias ----------

install_alias() {
    local shell_rc="$1"

    if [ ! -f "$shell_rc" ]; then
        return 0
    fi

    if grep -qF 'alias dotfiles=' "$shell_rc"; then
        echo "Dotfiles alias already present in $shell_rc"
    else
        {
            echo ""
            echo "# Dotfiles bare repo alias"
            echo "$DOTFILES_ALIAS"
        } >> "$shell_rc"
        echo "Added dotfiles alias to $shell_rc"
    fi
}

# ---------- uv ----------

check_uv() {
    if command -v uv &>/dev/null; then
        echo "uv is already installed."
        return 0
    else
        return 1
    fi
}

install_uv() {
    echo "uv is not installed."
    read -p "Would you like to install uv? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Installing uv..."
        curl -LsSf https://astral.sh/uv/install.sh | sh

        if [ -f "$HOME/.cargo/env" ]; then
            # shellcheck source=/dev/null
            source "$HOME/.cargo/env"
        fi
        export PATH="$HOME/.cargo/bin:$PATH"

        if command -v uv &>/dev/null; then
            echo "uv installed successfully."
        else
            echo "Error: uv installation failed."
            return 1
        fi
    else
        echo "uv installation cancelled. Cannot proceed with ansible."
        exit 1
    fi
}

# ---------- Ansible ----------

run_ansible() {
    local script_dir
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    local playbook="$script_dir/install.yml"

    if [ ! -f "$playbook" ]; then
        echo "Warning: install.yml not found, skipping ansible playbook."
        return 0
    fi

    echo "Running ansible playbook..."
    # This playbook contains non-root tasks only
    # For system-level packages requiring root (e.g., GitHub CLI), run install-system.yml separately with:
    # uvx --from ansible ansible-playbook install-system.yml --ask-become-pass -e "install_github_cli=true"
    # Use the full 'ansible' package (not ansible-core) so the playbook's
    # community.general modules (npm, cargo, homebrew) are available.
    # This installer already ensures uv is present, so use it as the Python
    # package manager (PDM's installer needs python3-venv, which isn't always
    # available). Override with PKG_MANAGER=pdm if you prefer PDM.
    uvx --from ansible ansible-playbook "$playbook" -e "pkg_manager=${PKG_MANAGER:-uv}"
}

# ---------- airprompt ----------

AIRPROMPT_SRC="$HOME/.bin/airprompt"

install_airprompt() {
    if [ ! -f "$AIRPROMPT_SRC/Cargo.toml" ]; then
        echo "Warning: $AIRPROMPT_SRC not found, skipping airprompt."
        return 0
    fi

    # rustup may have just been installed by the playbook in another shell.
    if [ -f "$HOME/.cargo/env" ]; then
        # shellcheck source=/dev/null
        source "$HOME/.cargo/env"
    fi
    if ! command -v cargo &>/dev/null; then
        echo "Warning: cargo not found, skipping airprompt (install rustup first)."
        return 0
    fi

    echo "Building and installing airprompt..."
    if ! cargo install --locked --path "$AIRPROMPT_SRC"; then
        echo "Warning: airprompt build failed, keeping the existing prompt."
        return 0
    fi

    # Vim statusline plugin (native package, loaded automatically by Vim 9).
    local pack="$HOME/.vim/pack/airprompt/start"
    local link="$pack/airprompt"
    if [ -e "$link" ] && [ ! -L "$link" ]; then
        echo "Warning: $link exists and is not a symlink, leaving it alone."
    else
        mkdir -p "$pack"
        ln -sfn "$AIRPROMPT_SRC/vim" "$link"
        echo "Linked Vim statusline: $link -> $AIRPROMPT_SRC/vim"
    fi
}

install_airprompt_init() {
    local shell_rc="$1" shell="$2"

    if [ ! -f "$shell_rc" ]; then
        return 0
    fi

    if grep -qF 'airprompt init' "$shell_rc"; then
        echo "airprompt init already present in $shell_rc"
    else
        {
            echo ""
            echo "# airprompt prompt"
            echo "command -v airprompt >/dev/null && eval \"\$(airprompt init $shell)\""
        } >> "$shell_rc"
        echo "Added airprompt init to $shell_rc"
    fi
}

# ---------- Main ----------

echo "=== Dotfiles installer (bare repo) ==="

# 1. Set up bare repository
setup_bare_repo
configure_bare_repo
checkout_dotfiles

# 2. Install the dotfiles alias into shell configs
install_alias "$HOME/.bashrc"
install_alias "$HOME/.zshrc"

# 3. Install uv
echo ""
echo "Checking for uv..."
if ! check_uv; then
    install_uv
fi

# 4. Run ansible playbook for additional tooling
run_ansible

# 5. Build airprompt (needs cargo from the playbook) and hook it into the shells
echo ""
install_airprompt
if command -v airprompt &>/dev/null; then
    install_airprompt_init "$HOME/.bashrc" bash
    install_airprompt_init "$HOME/.zshrc" zsh
fi

echo ""
echo "Dotfiles installation complete!"
echo "Open a new shell or run: source ~/.bashrc (or ~/.zshrc)"
echo "Then use 'dotfiles' as a git alias for managing your dotfiles."
