# ~/.zshrc — interactive zsh. Environment lives in ~/.profile.
emulate sh -c '. "$HOME/.profile"'

# Oh My Zsh is a submodule checked out at ~/ohmyzsh; fall back to a
# conventional ~/.oh-my-zsh install on machines set up some other way.
if [ -d "$HOME/ohmyzsh" ]; then
    export ZSH="$HOME/ohmyzsh"
else
    export ZSH="$HOME/.oh-my-zsh"
fi

ZSH_THEME="robbyrussell"
zstyle ':omz:update' mode disabled   # updates come from the submodule
DISABLE_MAGIC_FUNCTIONS="true"       # avoids paste issues
COMPLETION_WAITING_DOTS="true"
DISABLE_UNTRACKED_FILES_DIRTY="true" # faster prompt in big repos

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

# Only load plugins whose tools exist (otherwise they print errors).
if (( $+commands[docker] )); then
    plugins+=(docker)
    (( $+commands[docker-compose] )) && plugins+=(docker-compose)
fi
# ssh-agent only when there is a private key to manage
if [[ -n $HOME/.ssh/id_*~*.pub(N[1]) ]]; then
    plugins+=(ssh-agent)
fi

if [ -f "$ZSH/oh-my-zsh.sh" ]; then
    source "$ZSH/oh-my-zsh.sh"
else
    print -u2 "oh-my-zsh missing: run 'dotfiles submodule update --init'"
fi

[ -e "$HOME/.nix-profile/etc/profile.d/nix.sh" ] && . "$HOME/.nix-profile/etc/profile.d/nix.sh"

# Manage tracked dotfiles with: dotfiles <git-cmd>
alias dotfiles='git --git-dir=$HOME/.dotfiles --work-tree=$HOME'

[ -f "$HOME/.zshrc.local" ] && source "$HOME/.zshrc.local"
