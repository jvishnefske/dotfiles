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
set wildmenu
set foldmethod=syntax
set shortmess+=A        " Turn click-me warnings about swapfiles into discreet messages
set nowrap


" Enable completion where available.
" This setting must be set before ALE is loaded.
"
" You should not turn this setting on if you wish to use ALE as a completion
" source for other completion plugins, like Deoplete.
let g:ale_completion_enabled = 1

" Set this variable to 1 to fix files when you save them.
let g:ale_fix_on_save = 1

" Set this. Airline will handle the rest.
let g:airline#extensions#ale#enabled = 1
"let g:ale_floating_window_border = ['│', '─', '╭', '╮', '╯', '╰', '│', '─']
"let g:ale_open_list = 1
let g:deoplete#enable_at_startup = 1
"let g:ycm_min_num_of_chars_for_completion = 9
let g:UltiSnipsExpandTrigger = '<C-Space>'
"let g:UltiSnipsJumpForwardTrigger = '<C-j>'
"let g:UltiSnipsJumpBackwardTrigger = '<C-k>'

call plug#begin('~/.vim/plugged')
Plug 'morhetz/gruvbox'
Plug 'altercation/vim-colors-solarized'
Plug 'scrooloose/nerdtree', { 'on':  'NERDTreeToggle' }
Plug 'dense-analysis/ale'
Plug 'vim-airline/vim-airline'
Plug 'tpope/vim-fugitive'
Plug 'SirVer/ultisnips'
Plug 'honza/vim-snippets'
"Plug 'tomtom/tlib_vim'
"Plug 'godlygeek/tabular'
"Plug 'vim-scripts/VOoM'
"Plug 'kien/ctrlp.vim'
"Plug 'wincent/command-t', { 'branch': '5-x-release' } 

if has('nvim')
  Plug 'Shougo/deoplete.nvim', { 'do': ':UpdateRemotePlugins' }
else
  Plug 'ycm-core/YouCompleteMe', {'branch': 'legacy-vim-8.1'}
endif

call plug#end()


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

" Vim-specific settings
syntax on
filetype plugin indent on
silent! colorscheme gruvbox

" ALE configuration (Vim-specific)
let g:ale_completion_enabled = 1
let g:airline#extensions#ale#enabled = 1
let g:ale_fix_on_save = 0
let g:ale_fixers = {
\   '*': ['remove_trailing_lines', 'trim_whitespace'],
\   'cpp': ['clang-format'],
\   'rust': ['rustfmt'],
\   'javascript': ['eslint'],
\   'python': ['black']
\}

" ALE keybindings (Vim-specific)
map <leader>l :ALEFix<CR>
map <leader>c :ALEComplete<CR>
map <leader>r :ALERename<CR>
map <leader>g :ALEGoToDefinition<CR>
map <leader>q :ALEPopulateQuickfix<CR>
map <leader>-<Space> :AleCodeAction<CR>

" Open NERDTree on startup if no files specified
function! StartUp()
    if 0 == argc()
        NERDTree
    end
endfunction
"autocmd VimEnter * call StartUp()
