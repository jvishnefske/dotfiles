" ~/.vim/ale.vim — ALE flavor.
" Switch to coc by repointing ~/.vimrc to ~/.vim/common.vim.

" These MUST be set before ALE loads.
" ALE's own automatic completion stays off: it opens the popup menu with
" language server items only, which would race with the merged LSP + snippet
" menu built further down. Completions are still requested from ALE, through
" ale#completion#GetCompletions(), which works with this set to 0.
let g:ale_completion_enabled = 0
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
" Completion sources: ALE (LSP) + snipMate snippets, merged into one popup.
" See AleSnipComplete() below.
set omnifunc=AleSnipComplete
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

" ---- LSP + snippet completion --------------------------------------------
" ALE's omnifunc offers language server items only. AleSnipComplete() wraps it
" and puts the snipMate triggers that match what has been typed in front of
" them, so a single popup carries both, snippets first. Snippet items are marked with kind 'S' and are expanded
" as soon as they are confirmed (see s:ExpandCompletedSnippet below).
"
" This is the manual path, used by <TAB>, CTRL-X CTRL-O and CTRL-Space. The
" popup that appears while typing is driven by s:StartAutoComplete() below.

let g:snipMate = get(g:, 'snipMate', {})
let g:snipMate.description_in_completion = 1

" Seconds to wait for the language server before showing the popup anyway.
let g:ale_snip_lsp_timeout = 1.0

function! s:SnippetItems(base) abort
  " Called, not exists()-checked: an autoload function only reports itself as
  " existing once its file has been sourced, which calling it takes care of.
  try
    let l:matches = snipMate#GetSnippetsForWordBelowCursorForComplete(a:base)
  catch /E117:/
    " snipMate is not installed.
    return []
  endtry

  let l:items = []

  for l:snip in l:matches
    call add(l:items, {
    \  'word': l:snip.word,
    \  'menu': get(l:snip, 'menu', 'snippet'),
    \  'kind': 'S',
    \  'dup': 1,
    \  'user_data': json_encode({'snipmate': 1}),
    \})
  endfor
  return l:items
endfunction

" A bounded version of ALE's own busy-wait, so that a slow or missing language
" server never holds the snippets hostage.
function! s:LspItems() abort
  let l:waited = reltime()
  let l:result = ale#completion#GetCompletionResult()

  while l:result is v:null
  \ && !complete_check()
  \ && reltimefloat(reltime(l:waited)) < g:ale_snip_lsp_timeout
    sleep 2m
    let l:result = ale#completion#GetCompletionResult()
  endwhile

  return l:result isnot v:null ? l:result : []
endfunction

" Many ftplugins (python, html, css, ...) set a buffer-local 'omnifunc' of their
" own, which would shadow the global one set above. Take the option back after
" the ftplugin has run, remembering what it wanted so it can still be used as a
" fallback when no language server answers.
function! s:ClaimOmnifunc() abort
  if &l:omnifunc isnot# 'AleSnipComplete'
    let b:ale_snip_fallback = &l:omnifunc
  endif

  setlocal omnifunc=AleSnipComplete
endfunction

augroup AleSnipOmnifunc
  autocmd!
  autocmd FileType * call s:ClaimOmnifunc()
augroup END

function! AleSnipComplete(findstart, base) abort
  if a:findstart
    let l:start = ale#completion#OmniFunc(1, a:base)
    let b:ale_snip_lsp = l:start >= 0

    if b:ale_snip_lsp
      let b:ale_snip_fallback_active = 0

      return l:start
    endif

    " No language server here (ALE returned -3). Defer to the omnifunc the
    " ftplugin installed, if there was one, and otherwise complete snippets
    " alone from the keyword under the cursor.
    let l:fallback = get(b:, 'ale_snip_fallback', '')
    let b:ale_snip_fallback_active = !empty(l:fallback)

    if b:ale_snip_fallback_active
      return call(l:fallback, [1, a:base])
    endif

    let l:before = col('.') > 1 ? getline('.')[: col('.') - 2] : ''

    return match(l:before, '\k*$')
  endif

  if get(b:, 'ale_snip_lsp', 0)
    let l:items = s:LspItems()
  elseif get(b:, 'ale_snip_fallback_active', 0)
    let l:items = call(b:ale_snip_fallback, [0, a:base])
  else
    let l:items = []
  endif

  " Snippets first: they are the shortest path to a whole construct.
  return s:SnippetItems(a:base) + l:items
endfunction

" Expand a snippet as soon as its completion item is confirmed.
function! s:ExpandCompletedSnippet() abort
  if get(v:completed_item, 'kind', '') isnot# 'S'
    return
  endif

  let l:data = ale#util#FuzzyJSONDecode(get(v:completed_item, 'user_data', ''), {})

  if type(l:data) is v:t_dict && get(l:data, 'snipmate', 0)
    call feedkeys("\<Plug>snipMateTrigger")
  endif
endfunction

" Trigger the merged popup explicitly (CTRL-Space arrives as CTRL-@ in a
" terminal, so map both).
inoremap <silent> <C-Space> <C-x><C-o>
inoremap <silent> <C-@>     <C-x><C-o>

" ---- Popup while typing ---------------------------------------------------
" The same flow ALE uses for its automatic popup, with the snippets merged in:
" ask ALE for completions asynchronously, put the matching snippets in front of
" the reply when it arrives, then hand the merged list to the menu through
" 'completefunc'.
" Set g:ale_snip_auto_complete to 0 for a <TAB>-only setup.

let g:ale_snip_auto_complete = 1
let g:ale_snip_auto_delay = 100
" ALE only calls back when the language server returned something, so give up
" waiting for it after this many milliseconds and show the snippets on their
" own. Late language server items are merged in when they turn up.
let g:ale_snip_auto_wait = 400

let s:auto_timer = -1
let s:auto_pos = [0, 0]
let s:done_pos = [0, 0]
let s:request_id = 0
let s:waiting = 0

function! s:StopAutoTimer() abort
  if s:auto_timer != -1
    call timer_stop(s:auto_timer)
    let s:auto_timer = -1
  endif
endfunction

function! s:QueueAutoComplete() abort
  call s:StopAutoTimer()

  " Not while a snippet is being filled in, and not on the position a
  " completion was just accepted at.
  if !g:ale_snip_auto_complete
  \|| pumvisible()
  \|| exists('b:snip_state')
  \|| getpos('.')[1:2] == s:done_pos
    return
  endif

  let s:auto_timer = timer_start(g:ale_snip_auto_delay, function('s:StartAutoComplete'))
endfunction

function! s:StartAutoComplete(...) abort
  let s:auto_timer = -1

  if mode() isnot# 'i' || pumvisible()
    return
  endif

  let [l:line, l:column] = getpos('.')[1:2]

  " Nothing worth completing before the cursor.
  if empty(ale#completion#GetPrefix(&filetype, l:line, l:column))
    return
  endif

  let s:auto_pos = [l:line, l:column]
  let s:request_id += 1

  if !ale#completion#GetCompletions('ale-callback', {'callback': function('s:ShowMergedMenu')})
    " No language server for this buffer: show the snippets on their own.
    let s:waiting = 0
    call s:ShowMergedMenu([])

    return
  endif

  let l:id = s:request_id
  let s:waiting = 1

  call timer_start(g:ale_snip_auto_wait, {-> s:ShowSnippetsAlone(l:id)})
endfunction

" ALE calls back through s:ShowMergedMenu() only when the language server
" answered with at least one item, so nothing at all is shown for a word it
" does not know. Fill that gap once the wait is up.
function! s:ShowSnippetsAlone(request_id) abort
  if s:waiting && a:request_id == s:request_id
    call s:ShowMergedMenu([])
  endif
endfunction

function! s:ShowMergedMenu(items) abort
  let s:waiting = 0

  " The reply is asynchronous, so it can arrive after the cursor has moved on.
  if mode() isnot# 'i' || getpos('.')[1:2] != s:auto_pos
    return
  endif

  " An open menu is only replaced to merge language server items into a menu
  " that went up with snippets alone.
  if pumvisible()
  \&& (empty(a:items) || !get(b:, 'ale_snip_menu_snippets_only', 0))
    return
  endif

  let l:before = col('.') > 1 ? getline('.')[: col('.') - 2] : ''
  let l:merged = s:SnippetItems(matchstr(l:before, '\k*$')) + a:items

  if empty(l:merged)
    return
  endif

  let b:ale_snip_menu_items = l:merged
  let b:ale_snip_menu_snippets_only = empty(a:items)
  let b:ale_snip_menu_start = empty(a:items)
  \   ? match(l:before, '\k*$')
  \   : ale#completion#GetCompletionPosition()
  let &l:completefunc = 'AleSnipMenuComplete'

  call feedkeys("\<Plug>(ale_snip_show_menu)")
endfunction

" 'completefunc' that just hands over what s:ShowMergedMenu() prepared.
function! AleSnipMenuComplete(findstart, base) abort
  if a:findstart
    return get(b:, 'ale_snip_menu_start', -3)
  endif

  return get(b:, 'ale_snip_menu_items', [])
endfunction

inoremap <silent> <Plug>(ale_snip_show_menu) <C-x><C-u><C-p>

augroup AleSnipCompletion
  autocmd!
  autocmd TextChangedI * call s:QueueAutoComplete()
  autocmd InsertLeave  * call s:StopAutoTimer() | let s:waiting = 0
  autocmd CompleteDone * let s:done_pos = getpos('.')[1:2]
  autocmd CompleteDone * call s:ExpandCompletedSnippet()
augroup END

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
