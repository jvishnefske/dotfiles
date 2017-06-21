#!/bin/sh
#vim-plug


cd $(dirname $0)
working_dir=$PWD



function safe_link(){
  local target=$working_dir/$1
  local link=$HOME/$1
  if [[ ! -e $target ]] ; then 
    echo "file not found: $target."
  fi
  ln --symbolic --interactive $target $link
}
safe_link .profile
safe_link .bashrc
safe_link .vimrc
safe_link .gitconfig
# if vim is installed, then install vim-plug
if $(which vim > /dev/null)
then

if [[ ! -e $HOME/.vim/autoload/plug.vim ]] ; then
  curl -fLo $HOME/.vim/autoload/plug.vim --create-dirs \
    https://raw.githubusercontent.com/junegunn/vim-plug/master/plug.vim
fi
fi
