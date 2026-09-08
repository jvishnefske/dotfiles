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
" The coc release bundle needs Node >= 20 (its ansi-styles dependency uses the
" RegExp `v` flag). A system Node at /usr/local/bin often shadows a newer
" runtime in PATH, so fall back to the highest nvm-managed version instead of
" letting the language-server host crash on startup.
function! s:CocNodePath() abort
  let l:default = exepath('node')
  if !empty(l:default) && s:NodeMajor(l:default) >= 20
    return l:default
  endif
  let l:best = ''
  let l:best_major = 0
  for l:candidate in glob(expand('~/.nvm/versions/node') . '/v*/bin/node', 0, 1)
    let l:major = s:NodeMajor(l:candidate)
    if l:major > l:best_major
      let l:best = l:candidate
      let l:best_major = l:major
    endif
  endfor
  return l:best_major >= 20 ? l:best : l:default
endfunction

function! s:NodeMajor(node) abort
  if !executable(a:node)
    return 0
  endif
  return str2nr(matchstr(system(a:node . ' --version'), '^v\zs\d\+'))
endfunction

let g:coc_node_path = s:CocNodePath()

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
