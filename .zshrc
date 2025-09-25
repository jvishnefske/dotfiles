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
    docker
    docker-compose
    taskwarrior
    ssh-agent
    systemd
    colored-man-pages
    colorize
    command-not-found
    dnf
    dotenv
)

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

. "$HOME/.local/bin/env"
