" ~/.vim/common.vim

" Common settings for both Vim and Neovim
set nocompatible
set background=dark
set showcmd             " Show (partial) command in status line.
set showmatch           " Show matching brackets.
set ignorecase          " Do case insensitive matching
set smartcase           " Do smart case matching
set incsearch           " Incremental search
set autowrite           " Automatically save before commands like :next and :make
set hidden              " Hide buffers when they are abandoned
set mouse=a             " Enable mouse usage (all modes)
set wildmenu            " autocomplete vim commands
set autoindent
set ruler
set number              " line numbers
set shiftwidth=4
set softtabstop=4
set expandtab
set foldmethod=syntax
set shortmess+=A        " Turn click-me warnings about swapfiles into discreet messages

" Jump to the last position when reopening a file
au BufReadPost * if line("'\"") > 1 && line("'\"") <= line("$") | exe "normal! g'\"" | endif

" Common key mappings
let mapleader = "\\"
map <leader>n :NERDTreeToggle<CR>
map <leader>m :make<CR>
map <leader>p :CtrlP<CR>
map <leader>v :Voom<CR>

" NERDTree configuration
" Exit Vim if NERDTree is the only window remaining in the only tab.
autocmd BufEnter * if tabpagenr('$') == 1 && winnr('$') == 1 && exists('b:NERDTree') && b:NERDTree.isTabTree() | quit | endif
" Close the tab if NERDTree is the only window remaining in it.
autocmd BufEnter * if winnr('$') == 1 && exists('b:NERDTree') && b:NERDTree.isTabTree() | quit | endif

" Common plugin configurations
let g:ctrlp_map = '<c-p>'
let g:ctrlp_cmd = 'CtrlP'

" Airline configuration
let g:airline_powerline_fonts = 0
