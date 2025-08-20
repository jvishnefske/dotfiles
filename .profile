pathadd() {
    if [ -d "$1" ] && [[ ":$PATH:" != *":$1:"* ]]; then
        PATH="${PATH:+"$PATH:"}$1"
    fi
}
export PATH=/usr/bin:/bin:/usr/local/bin
export PATH=$HOME/bin:$HOME/jdk-current/bin:$HOME/go-current/bin:$HOME/.local/bin:$PATH
#[ -x $HOME/.dotfiles/auto-nfs.sh ] && $HOME/.dotfiles/auto-nfs.sh 2>&1 >/dev/null
    . "$HOME/.cargo/env"

pathadd() {
    if [ -d "$1" ] && [[ ":$PATH:" != *":$1:"* ]]; then
        PATH="${PATH:+"$PATH:"}$1"
    fi
}
pathadd $HOME/.local/arm-gnu-toolchain-13.2.Rel1-x86_64-arm-none-eabi/bin/
pathadd $HOME/jdk-current/bin
pathadd $HOME/go-current/bin
pathadd $HOME/.local/bin
pathadd $HOME/.local/node-v22.17.0-linux-x64/bin
pathadd /opt/rocm-6.2.0/lib/llvm/bin/
