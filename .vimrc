" Set this variable to 1 to fix files when you save them.
call plug#begin('~/.vim/plugged')
Plug 'junegunn/seoul256.vim'
Plug 'scrooloose/nerdtree', { 'on':  'NERDTreeToggle' }
Plug 'dense-analysis/ale'
Plug 'vim-airline/vim-airline'
Plug 'tpope/vim-fugitive'
Plug 'SirVer/ultisnips' | Plug 'honza/vim-snippets'
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
" The following are commented out as they cause vim to behave a lot
" differently from regular Vi. They are highly recommended though.
filetype plugin indent on " indentation rules and plugins according to the detected filetype.
let g:seoul256_background = 233
colo seoul256
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
map <C-l> :ALEFix<CR>
map <C-r> :ALEComplete<CR>
map <leader>n :NERDTreeToggle<CR>
let g:UltiSnipsExpandTrigger="<tab>"
let g:UltiSnipsJumpForwardTrigger="<c-b>"
let g:UltiSnipsJumpBackwardTrigger="<c-z>"

function! StartUp()
    if 0 == argc()
        NERDTree
    end
endfunction
autocmd VimEnter * call StartUp()
