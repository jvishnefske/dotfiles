#export PATH=$HOME/bin:$HOME/jdk-current/bin:$HOME/go-current/bin:/usr/bin:/usr/sbin:$HOME/bin/node-current/bin:/bin:/usr/local/bin:$HOME/.local/bin
[ -f /etc/profild.d/bash_completion.sh ] && . /etc/profile.d/bash_completion.sh 
#export PS1="\[\e[32m\][\u@\h:\W]\\$\[\e[m\]"
export PS1="\[\e[32m\]\u@\h:\W\\$\[\e[m\]"
[ -x /usr/bin/lesspipe.sh ] && eval "$(SHELL=/bin/sh lesspipe.sh)"
export WORKON_HOME=$HOME/.virtualenvs
export PROJECT_HOME=$HOME/src
export VIRTUALENVWRAPPER_SCRIPT=.dotfiles/virtualenvwrapper.sh
[ -f $VIRTUALENVWRAPPER_SCRIPT ] && source $VIRTUALENVWRAPPER_SCRIPT
export PCLINT_PATH=$HOME/bin/pclint9/
export GOPATH=$HOME
alias vi=vim
alias rm='rm -i'
alias mv='mv -i'
alias ls='ls --color'


# added by Anaconda3 4.4.0 installer
export PATH="/home/j/bin/anaconda3/bin:$PATH"
source /home/cnh/credentials.sh
source /home/cnh/build-scripts/cnh-env.sh
export PATH=/home/cnh/build-scripts:$PATH
