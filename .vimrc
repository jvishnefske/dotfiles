" Set this variable to 1 to fix files when you save them.
call plug#begin('~/.vim/plugged')
Plug 'morhetz/gruvbox'
Plug 'scrooloose/nerdtree', { 'on':  'NERDTreeToggle' }
Plug 'dense-analysis/ale'
Plug 'vim-airline/vim-airline'
Plug 'tpope/vim-fugitive'
Plug 'garbas/vim-snipmate'
Plug 'honza/vim-snippets'
Plug 'MarcWeber/vim-addon-mw-utils'
Plug 'tomtom/tlib_vim'
Plug 'godlygeek/tabular'
Plug 'vim-scripts/VOoM' " only loads with python
Plug 'kien/ctrlp.vim'
" Initialize plugin system
call plug#end()
let g:ale_completion_enabled = 1
let g:airline#extensions#ale#enabled = 1
let g:ale_fix_on_save = 0
let g:ale_fixers = {
\   '*': ['remove_trailing_lines', 'trim_whitespace'],
\   'cpp': ['clang-format'],
\   'rust': ['rustfmt'],
\   'javascript': ['eslint'],
\}

" have Vim jump to the last position
au BufReadPost * if line("'\"") > 1 && line("'\"") <= line("$") | exe "normal! g'\"" | endif
filetype plugin indent on " indentation rules and plugins according to the detected filetype.
silent! colo gruvbox
syntax on               " enable syntax highlighting by default.
set nocompatible
set background=dark
set showcmd		" Show (partial) command in status line.
set showmatch		" Show matching brackets.
set ignorecase		" Do case insensitive matching
set smartcase		" Do smart case matching
set incsearch		" Incremental search
set autowrite		" Automatically save before commands like :next and :make
set hidden		" Hide buffers when they are abandoned
set mouse=a		" Enable mouse usage (all modes)
set wildmenu		" autocomplete vim commands
set autoindent
set ruler
set number		" line numbers
set shiftwidth=4
set softtabstop=4
set expandtab
set foldmethod=syntax
" Turn click-me warnings about swapfiles into discreet little messages
set shortmess+=A

" note leader is \ by default.
map <leader>l :ALEFix<CR>
map <leader>c :ALEComplete<CR>
map <leader>r :ALERename<CR>
map <leader>g :ALEGoToDefinition<CR>
map <leader>q :ALEPopulateQuickfix<CR>
map <leader>-<Space> :AleCodeAction<CR>
map <leader>n :NERDTreeToggle<CR>
map <leader>m :make<CR>
map <leader>p :CtrlP<CR>
map <leader>v :Voom<CR>

" note that by default snipmate binds to <tab> and <c-r><tab>
function! StartUp()
    if 0 == argc()
        NERDTree
    end
endfunction
autocmd VimEnter * call StartUp()

" Exit Vim if NERDTree is the only window remaining in the only tab.
autocmd BufEnter * if tabpagenr('$') == 1 && winnr('$') == 1 && exists('b:NERDTree') && b:NERDTree.isTabTree() | quit | endif
" Close the tab if NERDTree is the only window remaining in it.
autocmd BufEnter * if winnr('$') == 1 && exists('b:NERDTree') && b:NERDTree.isTabTree() | quit | endif

