" ~/.vim/ale.vim — ALE flavor.
" Switch to coc by repointing ~/.vimrc to ~/.vim/common.vim.

" These MUST be set before ALE loads
let g:ale_completion_enabled = 1
let g:ale_completion_autoimport = 1

source ~/.vim/core.vim

" ---- Plugins (vim-plug) ---------------------------------------------------
call plug#begin('~/.vim/plugged')
Plug 'morhetz/gruvbox'
Plug 'vim-airline/vim-airline'
Plug 'scrooloose/nerdtree', { 'on': 'NERDTreeToggle' }
Plug 'tpope/vim-fugitive'
Plug 'ctrlpvim/ctrlp.vim'
Plug 'rust-lang/rust.vim'
Plug 'dense-analysis/ale'
" Snippet stack (snipMate format, no coc-snippets here)
Plug 'MarcWeber/vim-addon-mw-utils'
Plug 'tomtom/tlib_vim'
Plug 'garbas/vim-snipmate'
Plug 'honza/vim-snippets'
call plug#end()

" ---- Visuals & generic keymaps -------------------------------------------
syntax on
filetype plugin indent on
silent! colorscheme gruvbox
let g:airline_powerline_fonts = 0
let g:airline#extensions#ale#enabled = 1

map <leader>n :NERDTreeToggle<CR>
map <leader>m :make<CR>
map <leader>p :CtrlP<CR>
let g:ctrlp_map = '<c-p>'
let g:ctrlp_cmd = 'CtrlP'
autocmd BufEnter * if tabpagenr('$') == 1 && winnr('$') == 1 && exists('b:NERDTree') && b:NERDTree.isTabTree() | quit | endif

" ---- ALE ------------------------------------------------------------------
set omnifunc=ale#completion#OmniFunc
let g:ale_lint_on_text_changed = 'normal'
let g:ale_lint_on_insert_leave = 1
let g:ale_fix_on_save = 1
let g:ale_sign_error = '✗'
let g:ale_sign_warning = '⚠'
let g:ale_echo_msg_format = '[%linter%] %s [%severity%]'
let g:ale_floating_preview = 1
let g:ale_hover_to_floating_preview = 1
let g:ale_detail_to_floating_preview = 1

" Rust / cargo
let g:ale_rust_cargo_use_clippy = executable('cargo-clippy')
let g:ale_rust_cargo_check_all_targets = 1

let g:ale_linters = {
\   'rust':       ['analyzer'],
\   'python':     ['pylsp', 'ruff'],
\   'c':          ['clangd'],
\   'cpp':        ['clangd'],
\   'sh':         ['shellcheck', 'bash-language-server'],
\   'javascript': ['eslint', 'tsserver'],
\   'typescript': ['eslint', 'tsserver'],
\   'json':       ['jsonlint'],
\   'yaml':       ['yamllint'],
\}
let g:ale_fixers = {
\   '*':          ['remove_trailing_lines', 'trim_whitespace'],
\   'rust':       ['rustfmt'],
\   'python':     ['black', 'isort'],
\   'c':          ['clang-format'],
\   'cpp':        ['clang-format'],
\   'javascript': ['prettier', 'eslint'],
\   'typescript': ['prettier', 'eslint'],
\   'json':       ['prettier'],
\   'yaml':       ['prettier'],
\}

" TAB: cycle the omni popup or trigger it; CR confirms
inoremap <silent><expr> <TAB>
      \ pumvisible() ? "\<C-n>" :
      \ <SID>check_backspace() ? "\<TAB>" :
      \ "\<C-x>\<C-o>"
inoremap <expr><S-TAB> pumvisible() ? "\<C-p>" : "\<C-h>"
inoremap <expr><CR>   pumvisible() ? "\<C-y>" : "\<CR>"

function! s:check_backspace() abort
  let col = col('.') - 1
  return !col || getline('.')[col - 1] =~# '\s'
endfunction

" LSP navigation
nmap <silent> gd <Plug>(ale_go_to_definition)
nmap <silent> gy <Plug>(ale_go_to_type_definition)
nmap <silent> gi <Plug>(ale_go_to_implementation)
nmap <silent> gr <Plug>(ale_find_references)
nnoremap <silent> K :ALEHover<CR>

" Rename / code action / format
nmap <leader>rn <Plug>(ale_rename)
nmap <leader>ca <Plug>(ale_code_action)
nmap <leader>f  :ALEFix<CR>

" Diagnostics navigation
nmap <silent> [g <Plug>(ale_previous_wrap)
nmap <silent> ]g <Plug>(ale_next_wrap)

" snipMate trigger (default is <Tab>, but TAB is used for completion above)
imap <C-l> <Plug>snipMateNextOrTrigger
smap <C-l> <Plug>snipMateNextOrTrigger
imap <C-k> <Plug>snipMateBack
smap <C-k> <Plug>snipMateBack

let g:rustfmt_autosave = 0
