" ~/.vim/common.vim — coc.nvim flavor (the default).
" Switch to ALE by repointing ~/.vimrc to ~/.vim/ale.vim.

source ~/.vim/core.vim

" ---- Plugins (vim-plug) ---------------------------------------------------
call plug#begin('~/.vim/plugged')
Plug 'morhetz/gruvbox'
Plug 'vim-airline/vim-airline'
Plug 'scrooloose/nerdtree', { 'on': 'NERDTreeToggle' }
Plug 'tpope/vim-fugitive'
Plug 'ctrlpvim/ctrlp.vim'
Plug 'rust-lang/rust.vim'
Plug 'neoclide/coc.nvim', { 'branch': 'release' }
Plug 'honza/vim-snippets'
call plug#end()

" ---- Visuals & generic keymaps -------------------------------------------
syntax on
filetype plugin indent on
silent! colorscheme gruvbox
let g:airline_powerline_fonts = 0

map <leader>n :NERDTreeToggle<CR>
map <leader>m :make<CR>
map <leader>p :CtrlP<CR>
let g:ctrlp_map = '<c-p>'
let g:ctrlp_cmd = 'CtrlP'
autocmd BufEnter * if tabpagenr('$') == 1 && winnr('$') == 1 && exists('b:NERDTree') && b:NERDTree.isTabTree() | quit | endif

" ---- coc.nvim -------------------------------------------------------------
let g:coc_global_extensions = [
      \ 'coc-rust-analyzer',
      \ 'coc-json',
      \ 'coc-toml',
      \ 'coc-pyright',
      \ 'coc-clangd',
      \ 'coc-sh',
      \ 'coc-yaml',
      \ 'coc-cmake',
      \ 'coc-html',
      \ 'coc-tsserver',
      \ 'coc-snippets',
      \ ]

" TAB: confirm popup selection -> expand/jump snippet -> indent -> refresh
inoremap <silent><expr> <TAB>
      \ coc#pum#visible() ? coc#_select_confirm() :
      \ coc#expandableOrJump() ?
      \ "\<C-r>=coc#rpc#request('doKeymap', ['snippets-expand-jump',''])\<CR>" :
      \ <SID>check_backspace() ? "\<TAB>" :
      \ coc#refresh()
inoremap <expr><S-TAB> coc#pum#visible() ? coc#pum#prev(1) : "\<C-h>"
inoremap <silent><expr> <CR> coc#pum#visible() ? coc#pum#confirm() : "\<CR>"
inoremap <silent><expr> <C-Space> coc#refresh()

" Snippet placeholder navigation
let g:coc_snippet_next = '<c-j>'
let g:coc_snippet_prev = '<c-k>'
imap <C-j> <Plug>(coc-snippets-expand-jump)
vmap <C-j> <Plug>(coc-snippets-select)

function! s:check_backspace() abort
  let col = col('.') - 1
  return !col || getline('.')[col - 1] =~# '\s'
endfunction

" LSP navigation
nmap <silent> gd <Plug>(coc-definition)
nmap <silent> gy <Plug>(coc-type-definition)
nmap <silent> gi <Plug>(coc-implementation)
nmap <silent> gr <Plug>(coc-references)
nnoremap <silent> K :call CocActionAsync('doHover')<CR>

" Rename / code action / format
nmap <leader>rn <Plug>(coc-rename)
nmap <leader>ca <Plug>(coc-codeaction-cursor)
nmap <leader>f  <Plug>(coc-format)

" Diagnostics navigation
nmap <silent> [g <Plug>(coc-diagnostic-prev)
nmap <silent> ]g <Plug>(coc-diagnostic-next)

autocmd User CocJumpPlaceholder call CocActionAsync('showSignatureHelp')

let g:rustfmt_autosave = 0
