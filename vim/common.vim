" ~/.vim/common.vim
" Shared config for vim and nvim. Single completion stack: coc.nvim.

" ---- Core settings --------------------------------------------------------
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

" coc.nvim recommendations
set updatetime=300
set signcolumn=yes
set cmdheight=2
set completeopt=menuone,noinsert,noselect
set pumheight=15

let mapleader = "\\"

" ---- Plugins (vim-plug) ---------------------------------------------------
call plug#begin('~/.vim/plugged')

" UI
Plug 'morhetz/gruvbox'
Plug 'vim-airline/vim-airline'
Plug 'scrooloose/nerdtree', { 'on': 'NERDTreeToggle' }

" Editing / navigation
Plug 'tpope/vim-fugitive'
Plug 'ctrlpvim/ctrlp.vim'

" Language
Plug 'rust-lang/rust.vim'

" Completion / LSP — single source of truth
Plug 'neoclide/coc.nvim', { 'branch': 'release' }

call plug#end()

" ---- Visuals --------------------------------------------------------------
syntax on
filetype plugin indent on
silent! colorscheme gruvbox
let g:airline_powerline_fonts = 0

" ---- Generic keymaps ------------------------------------------------------
map <leader>n :NERDTreeToggle<CR>
map <leader>m :make<CR>
map <leader>p :CtrlP<CR>

let g:ctrlp_map = '<c-p>'
let g:ctrlp_cmd = 'CtrlP'

" Jump to last position when reopening a file
au BufReadPost * if line("'\"") > 1 && line("'\"") <= line("$") | exe "normal! g'\"" | endif

" Close vim if NERDTree is the only window remaining
autocmd BufEnter * if tabpagenr('$') == 1 && winnr('$') == 1 && exists('b:NERDTree') && b:NERDTree.isTabTree() | quit | endif

" ---- coc.nvim -------------------------------------------------------------
let g:coc_global_extensions = ['coc-rust-analyzer', 'coc-json']

" TAB cycles the popup; CR confirms; <C-Space> manually refreshes
inoremap <silent><expr> <TAB>
      \ coc#pum#visible() ? coc#pum#next(1) :
      \ <SID>check_backspace() ? "\<Tab>" :
      \ coc#refresh()
inoremap <expr><S-TAB> coc#pum#visible() ? coc#pum#prev(1) : "\<C-h>"
inoremap <silent><expr> <CR> coc#pum#visible() ? coc#pum#confirm() : "\<CR>"
inoremap <silent><expr> <C-Space> coc#refresh()

function! s:check_backspace() abort
  let col = col('.') - 1
  return !col || getline('.')[col - 1] =~# '\s'
endfunction

" LSP navigation
nmap <silent> gd <Plug>(coc-definition)
nmap <silent> gy <Plug>(coc-type-definition)
nmap <silent> gi <Plug>(coc-implementation)
nmap <silent> gr <Plug>(coc-references)

" Hover documentation
nnoremap <silent> K :call CocActionAsync('doHover')<CR>

" Rename / code action / format
nmap <leader>rn <Plug>(coc-rename)
nmap <leader>ca <Plug>(coc-codeaction-cursor)
nmap <leader>f  <Plug>(coc-format)

" Diagnostics navigation
nmap <silent> [g <Plug>(coc-diagnostic-prev)
nmap <silent> ]g <Plug>(coc-diagnostic-next)

" Show signature help on placeholder jump
autocmd User CocJumpPlaceholder call CocActionAsync('showSignatureHelp')

" ---- Rust -----------------------------------------------------------------
" rust-analyzer (via coc-rust-analyzer) handles formatting; disable rust.vim's
" autoformat so we don't double-format on save.
let g:rustfmt_autosave = 0
