# dotfiles

Shell (bash/zsh), Vim/Neovim, git and dev-tool setup, managed as a **bare git
repo** whose work tree is `$HOME`. No symlink farm, no copying.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/jvishnefske/dotfiles/main/.bin/install.sh | bash
```

This:

1. clones the repo bare into `~/.dotfiles` and checks it out into `$HOME`
   (files it would overwrite are moved to `~/.dotfiles-backup/`);
2. fetches the oh-my-zsh submodule into `~/ohmyzsh`;
3. installs [uv](https://docs.astral.sh/uv/) if missing (user-local, no sudo);
4. runs `~/.bin/install.yml`, which installs user-level tooling — never sudo.

System packages (git, vim, neovim, gcc, go, node, clangd, shellcheck, gh) need
root and are a separate step:

```bash
~/.bin/install-system.sh
```

Both are idempotent; re-run them any time.

## Daily use

```bash
dotfiles status
dotfiles add ~/.vimrc
dotfiles commit -m "vim: ..."
dotfiles push
dotfiles pull && dotfiles submodule update --init   # on another machine
```

`dotfiles` is an alias for `git --git-dir=$HOME/.dotfiles --work-tree=$HOME`,
defined in `.bashrc` and `.zshrc`. Untracked files are hidden from `status`.

## What the playbook installs

| Tag    | Tools                                                                 |
|--------|-----------------------------------------------------------------------|
| `rust` | rustup, rustfmt, rust-analyzer, clippy, stylua                        |
| `python` | ruff, black, isort, flake8, yamllint, vint (via `uv tool`)          |
| `go`   | gopls, goimports, golangci-lint, shfmt (needs Go ≥ 1.21)             |
| `npm`  | prettier, eslint, typescript(-language-server), pyright, bash/yaml/json LSPs, markdownlint, clang-format |
| `vim`, `nvim` | vim-plug, plugins, `~/.vim/*.vim` and `~/.config/nvim/init.lua` links |
| `ale`  | every linter/formatter/LSP above                                      |

Run a subset, or opt in to extras:

```bash
uvx --from ansible ansible-playbook ~/.bin/install.yml --tags vim,rust
uvx --from ansible ansible-playbook ~/.bin/install.yml \
    -e install_pdm=true -e install_nats_tools=true -e update_rustup=true
uvx --from ansible-core ansible-playbook ~/.bin/setup_vcpkg.yml   # vcpkg
```

## Layout

```
.profile        environment: PATH, EDITOR, VCPKG_ROOT (POSIX sh, sourced by both shells)
.bashrc         interactive bash: prompt, aliases
.zshrc          interactive zsh: oh-my-zsh + plugins
.gitconfig      identity, gh credential helper
.vimrc          one line choosing a Vim flavor (also used by Neovim)
vim/core.vim    editor settings shared by both flavors
vim/common.vim  coc.nvim flavor (default)
vim/ale.vim     ALE flavor — point .vimrc here to switch
nvim/init.lua   sources ~/.vimrc
ohmyzsh/        oh-my-zsh (submodule)
.bin/           install.sh, install.yml (user), system.yml (root), setup_vcpkg.yml
.config/system/ machine-specific systemd units, fstab and samba snippets (not installed)
```

## Machine-specific settings

Put untracked overrides in `~/.profile.local`, `~/.bashrc.local` or
`~/.zshrc.local`; each is sourced last if present. Per-directory git identity:

```gitconfig
[includeIf "gitdir:~/work/"]
    path = ~/.gitconfig.work
```

## Troubleshooting

- **zsh says oh-my-zsh is missing:** `dotfiles submodule update --init`.
- **Go tools skipped:** Go is older than 1.21; upgrade it, then `--tags go`.
- **coc.nvim "build/index.js not found":** re-run the playbook with `--tags vim`.
- **IDEs don't see the repo:** expected for bare repos; use the `dotfiles` alias.
