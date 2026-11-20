# ~/.bashrc — interactive bash. Environment lives in ~/.profile.
# shellcheck shell=bash
# shellcheck source=/dev/null
[ -f "$HOME/.profile" ] && . "$HOME/.profile"

[ -f /etc/profile.d/bash_completion.sh ] && . /etc/profile.d/bash_completion.sh
[ -x /usr/bin/lesspipe.sh ] && eval "$(SHELL=/bin/sh lesspipe.sh)"

PS1='\[\e[32m\]\u@\h:\W\$\[\e[m\] '

alias vi=vim
alias rm='rm -i'
alias mv='mv -i'
if ls --color=auto / >/dev/null 2>&1; then
    alias ls='ls --color=auto'   # GNU ls
else
    alias ls='ls -G'             # BSD/macOS ls
fi

# Manage tracked dotfiles with: dotfiles <git-cmd>
alias dotfiles='git --git-dir=$HOME/.dotfiles --work-tree=$HOME'

[ -f "$HOME/.bashrc.local" ] && . "$HOME/.bashrc.local"
