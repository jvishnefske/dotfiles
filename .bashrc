export PATH=$HOME/bin:$HOME/jdk-current/bin:$HOME/go-current/bin:/usr/bin:/usr/sbin:$HOME/bin/node-current/bin
#export PS1="\[\e[32m\]\u\[\e[m\]\[\e[32m\]@\[\e[m\]\[\e[32m\]\h\[\e[m\]\[\e[32m\]:\[\e[m\]\[\e[32m\]\W\[\e[m\]\[\e[34m\]\\$\[\e[m\] "
export PS1="\[\e[32m\]\u@\h:\W$\[\e[m\]"

[ -x /usr/bin/lesspipe.sh ] && eval "$(SHELL=/bin/sh lesspipe.sh)"
export PCLINT_PATH=$HOME/bin/pclint9/
alias vi=vim
alias rm='rm -i'
alias mv='mv -i'

