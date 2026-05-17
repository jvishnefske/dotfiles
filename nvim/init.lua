-- ~/.config/nvim/init.lua
-- Follow whichever flavor ~/.vimrc points at, so a single symlink swap
-- (~/.vimrc -> common.vim | ale.vim) switches both editors.
vim.cmd('source ~/.vimrc')
