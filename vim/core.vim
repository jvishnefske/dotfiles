" ~/.vim/core.vim
" Editor settings shared between flavors. No plugins, no completion config.

set nocompatible
set background=dark
set showcmd
set showmatch
set ignorecase
set smartcase
set incsearch
set autowrite
set hidden
set mouse=a
set wildmenu
set autoindent
set ruler
set number
set shiftwidth=4
set softtabstop=4
set expandtab
set foldmethod=syntax
set shortmess+=A
set shortmess+=c
set nowrap

" LSP-friendly defaults (apply to both flavors)
set updatetime=300
set signcolumn=yes
set cmdheight=2
set completeopt=menuone,noinsert,noselect
set pumheight=15

let mapleader = "\\"

" Jump to last cursor position when reopening a file
au BufReadPost * if line("'\"") > 1 && line("'\"") <= line("$") | exe "normal! g'\"" | endif

" Open NERDTree on startup when launched with no file arguments
function! s:StartUp() abort
  if 0 == argc()
    NERDTree
  endif
endfunction
autocmd VimEnter * call s:StartUp()
