# Path to your oh-my-zsh installation
export ZSH="$HOME/.oh-my-zsh"

# Theme
ZSH_THEME="robbyrussell"

# Disable automatic updates
zstyle ':omz:update' mode disabled

# Disable URL magic functions which can cause paste issues
DISABLE_MAGIC_FUNCTIONS="true"

# Show waiting dots during completion
COMPLETION_WAITING_DOTS="true"

# Performance improvement for large git repositories
DISABLE_UNTRACKED_FILES_DIRTY="true"

# Carefully selected plugins for a balance of features and speed
plugins=(
    git
    web-search
    pip
    jsontools
    taskwarrior
    systemd
    colored-man-pages
    colorize
    command-not-found
    dnf
    dotenv
)

# Load docker plugins only when docker is installed (otherwise the docker
# completion plugin errors with "command not found: docker").
if command -v docker &>/dev/null; then
    plugins+=(docker)
    command -v docker-compose &>/dev/null && plugins+=(docker-compose)
fi

# Load ssh-agent only when there is at least one SSH private key to manage
# (avoids an unnecessary agent/passphrase prompt on machines without keys).
if [ -n "$(find "$HOME/.ssh" -maxdepth 1 -name 'id_*' ! -name '*.pub' 2>/dev/null | head -1)" ]; then
    plugins+=(ssh-agent)
fi

# Load Oh My Zsh
source $ZSH/oh-my-zsh.sh

# Custom prompt (optional - only if you don't want to use the theme's prompt)
# PROMPT='%F{green}%n@%m:%~%#%f '


export MANPATH="/usr/local/man:$MANPATH"

# You may need to manually set your language environment
# export LANG=en_US.UTF-8

# Preferred editor for local and remote sessions
# if [[ -n $SSH_CONNECTION ]]; then
#   export EDITOR='vim'
# else
#   export EDITOR='mvim'
# fi

# Compilation flags
# export ARCHFLAGS="-arch x86_64"
 
# Set personal aliases, overriding those provided by oh-my-zsh libs,
# plugins, and themes. Aliases can be placed here, though oh-my-zsh
# users are encouraged to define aliases within the ZSH_CUSTOM folder.
# For a full list of active aliases, run `alias`.
#
# Example aliases
# alias zshconfig="mate ~/.zshrc"
# alias ohmyzsh="mate ~/.oh-my-zsh"
# 


#source $HOME/.profile
#export PATH=$PATH:$HOME/.local/ollama/bin
#export PATH=$HOME/build-scripts:$HOME/.local/bin:~/.local/venv/bin:$HOME/.local/build/depot_tools:$PATH

if [ -e /home/cnh/.nix-profile/etc/profile.d/nix.sh ]; then . /home/cnh/.nix-profile/etc/profile.d/nix.sh; fi # added by Nix installer
# alias code=flatpak run com.visualstudio.code
#alias docker-compose="docker compose"
#$. "$HOME/.cargo/env"
#export PATH=$PATH:$HOME/.local/arm-gnu-toolchain-13.2.Rel1-x86_64-arm-none-eabi/bin/
export PATH=$PATH:$HOME/.local/arm-gnu-toolchain-14.2.rel1-x86_64-arm-none-eabi/bin/
export PATH=$PATH:$HOME/.local/node-v22.17.0-linux-x64/bin

# Vcpkg environment variables
export VCPKG_ROOT="/home/j/.local/vcpkg"
export PATH="$VCPKG_ROOT:$PATH"

# Dotfiles bare repo alias — manage tracked dotfiles with: dotfiles <git-cmd>
alias dotfiles="git --git-dir=$HOME/.dotfiles --work-tree=$HOME"

# Tool binaries for vim/ALE fixers, linters and language servers
[ -f "$HOME/.cargo/env" ] && . "$HOME/.cargo/env"   # rustfmt, rust-analyzer, stylua
export PATH="$HOME/go/bin:$PATH"                     # gopls, goimports, shfmt

. "$HOME/.local/bin/env"                             # ~/.local/bin: prettier, black, pyright, ...
