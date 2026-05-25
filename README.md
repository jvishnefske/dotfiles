# dotfiles

Personal terminal and development environment configuration files for a productive development setup. Shell configs (Zsh/Bash), Vim/Neovim settings, Git configuration, and development tools - all automated with Ansible.

## Quick Start

```bash
git clone https://github.com/jvishnefske/dotfiles ~/.dotfiles
cd ~/.dotfiles
./install.sh
```

## Features

- **Shell Configuration**: Zsh with Oh-My-Zsh, Bash, and shared profile settings
- **Text Editors**: Vim and Neovim configurations with plugin management
- **Git Configuration**: Personal Git settings and aliases
- **Development Tools**: Python virtual environment wrapper, NATS tools
- **System Configuration**: Network mounting, systemd services
- **Automated Installation**: Ansible-based setup with dependency management
Personal terminal and development environment configuration managed as a bare git repository.

## Quick Start

Bootstrap on a fresh machine (no clone needed):

```bash
curl -Lks https://raw.githubusercontent.com/jvishnefske/dotfiles/main/install.sh | bash
```

Or manually:

```bash
git clone --bare https://github.com/jvishnefske/dotfiles.git $HOME/.cfg
alias dotfiles='git --git-dir=$HOME/.cfg --work-tree=$HOME'
dotfiles config --local status.showUntrackedFiles no
dotfiles checkout
```

If checkout fails due to existing files, back them up:

```bash
mkdir -p $HOME/.dotfiles-backup
dotfiles checkout 2>&1 | grep -E "^\s+" | awk '{print $1}' | \
  xargs -I{} bash -c 'mkdir -p "$HOME/.dotfiles-backup/$(dirname {})" && mv "$HOME/{}" "$HOME/.dotfiles-backup/{}"'
dotfiles checkout
```

## How It Works

This repo uses the bare git repository technique:

- `$HOME/.cfg` is a bare git repo (no working tree of its own)
- `$HOME` is the working tree — dotfiles live directly where programs expect them
- The `dotfiles` alias wraps git with `--git-dir` and `--work-tree` flags
- `status.showUntrackedFiles no` keeps `git status` clean (only shows tracked files)

No symlinks. No copying. Files are managed in-place.

## Daily Usage

```bash
dotfiles status
dotfiles add ~/.vimrc
dotfiles commit -m "update vim config"
dotfiles push
```

## What Gets Installed

The `install.sh` bootstrap script:
1. Clones the bare repo into `$HOME/.cfg`
2. Checks out dotfiles into `$HOME`
3. Adds the `dotfiles` alias to `.bashrc` and `.zshrc`
4. Installs `uv` (needed to run ansible)
5. Runs the ansible playbook for additional tooling

### Ansible Playbook

The playbook installs development tools (idempotent — safe to re-run):

- **Rust**: rustup toolchain manager
- **Python**: pdm (default) or uv (`-e pkg_manager=uv`)
- **GitHub CLI**: gh
- **Go tools**: NATS ecosystem (`-e install_nats_tools=true`)
- **Vim/Neovim**: Vim-Plug + plugins

Run specific tags:

```bash
uvx --from ansible-core ansible-playbook ~/install.yml --tags python
uvx --from ansible-core ansible-playbook ~/install.yml --tags rust
uvx --from ansible-core ansible-playbook ~/install.yml --tags vim,nvim
```

## Tracked Files

```
~/.bashrc           # Bash configuration
~/.zshrc            # Zsh configuration
~/.profile          # Shared shell profile
~/.gitconfig        # Git configuration
~/.vimrc            # Vim configuration
~/vim/              # Vim extras
~/nvim/             # Neovim configuration
~/ohmyzsh/          # Oh-My-Zsh framework (submodule)
~/install.sh        # Bootstrap script
~/install.yml       # Ansible playbook
```

## Machine-Specific Config

For settings that differ per machine, use local override files (not tracked):

```bash
# In .zshrc or .bashrc
[[ -f ~/.zshrc.local ]] && source ~/.zshrc.local
```

Or git's includeIf for per-directory git identity:

```gitconfig
[includeIf "gitdir:~/work/"]
    path = ~/.gitconfig.work
```

## Platform Support

- macOS, Linux (Debian, RHEL)
- Requirements: curl, bash, git, python3

## Troubleshooting

- **Checkout conflicts**: Back up existing files (see Quick Start above)
- **uv not found**: The installer prompts to install it
- **Ansible errors**: Ensure `uvx --from ansible-core` works
- **Plugin install fails**: Run `:PlugInstall` manually in Vim/Neovim
- **IDE doesn't see repo**: VSCode doesn't detect bare repos — use the terminal alias
