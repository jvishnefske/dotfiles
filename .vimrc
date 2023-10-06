" Specify a directory for plugins (for Neovim: ~/.local/share/nvim/plugged) 
call plug#begin('~/.vim/plugged') 
" Async-vim is only here because it is required by vim-lsp
Plug 'prabirshrestha/async.vim'
" Languages server protocol connection
Plug 'prabirshrestha/vim-lsp'
" Autocomplete functionality
Plug 'prabirshrestha/asyncomplete.vim'
" Autocomplete source - the buffer
Plug 'prabirshrestha/asyncomplete-buffer.vim'
" Autocomplete source - files
Plug 'prabirshrestha/asyncomplete-file.vim'
" Autocomplete source - language server protocol
Plug 'prabirshrestha/asyncomplete-lsp.vim'
" Autocomplete source - Ultisnips
Plug 'prabirshrestha/asyncomplete-ultisnips.vim'
" Autocomplete source - ctags
Plug 'prabirshrestha/asyncomplete-tags.vim'
"Plug 'ycm-core/YouCompleteMe'
"Plug 'tom-doerr/vim_codex' 
"Plug 'vim-syntastic/syntastic' 
" Shorthand notation; fetches https://github.com/junegunn/vim-easy-align 
"Plug 'junegunn/vim-easy-align' 
" Any valid git URL is allowed 
"Plug 'https://github.com/junegunn/vim-github-dashboard.git' 
" Multiple Plug commands can be written in a single line using | separators 
Plug 'SirVer/ultisnips' | Plug 'honza/vim-snippets' 
"Plug 'davidhalter/jedi' 
" On-demand loading 
Plug 'scrooloose/nerdtree', { 'on':  'NERDTreeToggle' } 
"Plug 'tpope/vim-fireplace', { 'for': 'clojure' } 
"Plug 'pangloss/vim-javascript' 
" Using a non-master branch 
"Plug 'rdnetto/YCM-Generator', { 'branch': 'stable' } 
"Plug 'Shougo/neocomplete.vim' 
"Plug 'mjbrownie/pythoncomplete.vim' 
" Using a tagged release; wildcard allowed (requires git 1.9.2 or above) 
"Plug 'fatih/vim-go', { 'tag': '*' } 
Plug 'tpope/vim-fugitive' 
" Plugin options 
"Plug 'nsf/gocode', { 'tag': 'v.20150303', 'rtp': 'vim' } 
" Plugin outside ~/.vim/plugged with post-update hook 
"Plug 'junegunn/fzf', { 'dir': '~/.fzf', 'do': './install --all' } 
" Initialize plugin system 
call plug#end()

" Vim will load $VIMRUNTIME/defaults.vim if the user does not have a vimrc.
" This happens after /etc/vim/vimrc(.local) are loaded, so it will override
" any settings in these files.
" If you don't want that to happen, uncomment the below line to prevent
" defaults.vim from being loaded.
" let g:skip_defaults_vim = 1

" have Vim jump to the last position 
au BufReadPost * if line("'\"") > 1 && line("'\"") <= line("$") | exe "normal! g'\"" | endif
" The following are commented out as they cause vim to behave a lot
" differently from regular Vi. They are highly recommended though.
filetype plugin indent on " indentation rules and plugins according to the detected filetype.
set termguicolors       " Truecolor in terminal
syntax on               " enable syntax highlighting by default.
set nocompatible
set background=dark
set showcmd		" Show (partial) command in status line.
set showmatch		" Show matching brackets.
"set ignorecase		" Do case insensitive matching
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
"set foldclose=
set foldmethod=syntax
" Turn click-me warnings about swapfiles into discreet little messages
set shortmess+=A
"set foldtext=getline(v\:foldstart),foldtext() 
" enable Plugins on newer vim only if not found already
let s:is_neovim = has( 'nvim' )

if exists( "loaded_youcompleteme" )
    finish
elseif ( v:version < 801 || (v:version == 801 && !has( 'patch2269' )) ) &&
      \ !s:is_neovim
    "echohl WarningMsg | 
    "            \ echomsg "vim is incompatible with trunc you complete me. try installing with apt install vim-addon-manager"
    finish
elseif !has( 'python3' )
  echohl WarningMsg |
        \ echomsg "YouCompleteMe unavailable: unable to load Python." |
        \ echohl None
  finish
endif
map <leader>n :NERDTreeToggle<CR>
" use plug
function! BuildYCM(info) 
    if a:info.status == 'installed' || a:info.force 
        " only use --all if jdk8 ,node/npm,, no xbuild, mono are installed 
            !./install.py --clangd-completer 
    endif 
endfunction 
" vim-lsp setup
function! s:on_lsp_buffer_enabled() abort
  setlocal omnifunc=lsp#complete
  setlocal signcolumn=yes
  echom "loaded"
  " Find definition of word under cursor
  nnoremap <buffer> <leader>ld :LspDefinition<CR>
  " Find callers of word under cursor
  nnoremap <buffer> <leader>lr :LspReferences<CR>
  " Rename symbol throughout project
  nnoremap <buffer> <leader>lR :LspRename<CR>
  " Show docs (e.g. from libraries)
  nnoremap <buffer> <leader>lK :LspHover<CR>
  " Format document layout
  nnoremap <buffer> <leader>lf :LspDocumentFormat<CR>
  let g:lsp_diagnostics_enabled = 1
  nmap <buffer> [g <plug>(lsp-previous-diagnostic)
  nmap <buffer> ]g <plug>(lsp-next-diagnostic)
endfunction
augroup lsp_install
    au!
    " call s:on_lsp_buffer_enabled only for languages that has the server registered.
    autocmd User lsp_buffer_enabled call s:on_lsp_buffer_enabled()
augroup END
if executable('pylsp')
    " pip install python-lsp-server
    au User lsp_setup call lsp#register_server({
        \ 'name': 'pylsp',
        \ 'cmd': {server_info->['pylsp']},
        \ 'allowlist': ['python'],
        \ })
endif
if executable('clangd')
    au User lsp_setup call lsp#register_server({
     \ 'name': 'clangd',
     \ 'cmd': {server_info->['clangd']},
     \ 'allowlist': ['c', 'cpp'],
     \ })
endif

" Using asyncomplete-buffer.vim
call asyncomplete#register_source(asyncomplete#sources#buffer#get_source_options({
    \ 'name': 'buffer',
    \ 'whitelist': ['*'],
    \ 'completor': function('asyncomplete#sources#buffer#completor'),
    \ 'config': {
    \    'max_buffer_size': 5000000,
    \  },
    \ }))


" Using asyncomplete-file.
au User asyncomplete_setup call asyncomplete#register_source(asyncomplete#sources#file#get_source_options({
    \ 'name': 'file',
    \ 'whitelist': ['*'],
    \ 'priority': 10,
    \ 'completor': function('asyncomplete#sources#file#completor')
    \ }))


" Using Ultisnips
call asyncomplete#register_source(asyncomplete#sources#ultisnips#get_source_options({
      \ 'name': 'ultisnips',
      \ 'whitelist': ['*'],
      \ 'completor': function('asyncomplete#sources#ultisnips#completor'),
      \ }))

" Using Ctags
au User asyncomplete_setup call asyncomplete#register_source(asyncomplete#sources#tags#get_source_options({
    \ 'name': 'tags',
    \ 'whitelist': ['ruby'],
    \ 'completor': function('asyncomplete#sources#tags#completor'),
    \ 'config': {
    \    'max_file_size': 50000000,
    \  },
    \ }))
" Log vim lsp actions
let g:lsp_log_verbose = 1
let g:lsp_log_file = expand('/tmp/vim-lsp.log')

" Tab to autocomplete with Asyncomplete
inoremap <expr> <Tab>   pumvisible() ? "\<C-n>" : "\<Tab>"
inoremap <expr> <S-Tab> pumvisible() ? "\<C-p>" : "\<S-Tab>"
inoremap <expr> <C-e> pumvisible() ? asyncomplete#cancel_popup() : "\<C-e>"



