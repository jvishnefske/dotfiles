" All system-wide defaults are set in $VIMRUNTIME/debian.vim and sourced by
" the call to :runtime you can find below.  If you wish to change any of those
" settings, you should do it in this file (/etc/vim/vimrc), since debian.vim
" will be overwritten everytime an upgrade of the vim packages is performed.
" It is recommended to make changes after sourcing debian.vim since it alters
" the value of the 'compatible' option.

" This line should not be removed as it ensures that various options are
" properly set to work with the Vim-related packages available in Debian.
runtime! debian.vim

" Vim will load $VIMRUNTIME/defaults.vim if the user does not have a vimrc.
" This happens after /etc/vim/vimrc(.local) are loaded, so it will override
" any settings in these files.
" If you don't want that to happen, uncomment the below line to prevent
" defaults.vim from being loaded.
" let g:skip_defaults_vim = 1

" Uncomment the next line to make Vim more Vi-compatible
" NOTE: debian.vim sets 'nocompatible'.  Setting 'compatible' changes numerous
" options, so any other options should be set AFTER setting 'compatible'.
"set compatible

" Vim5 and later versions support syntax highlighting. Uncommenting the next
" line enables syntax highlighting by default.
if has("syntax")
  syntax on
endif

" If using a dark background within the editing area and syntax highlighting
" turn on this option as well
"set background=dark

" Uncomment the following to have Vim jump to the last position when
" reopening a file
"if has("autocmd")
"  au BufReadPost * if line("'\"") > 1 && line("'\"") <= line("$") | exe "normal! g'\"" | endif
"endif

" Uncomment the following to have Vim load indentation rules and plugins
" according to the detected filetype.
if has("autocmd")
  filetype plugin indent on
endif

" The following are commented out as they cause vim to behave a lot
" differently from regular Vi. They are highly recommended though.
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

" use plug
function! BuildYCM(info) 
    if a:info.status == 'installed' || a:info.force 
        " only use --all if jdk8 ,node/npm,, no xbuild, mono are installed 
            !./install.py --clangd-completer 
    endif 
endfunction 
 
" Trigger configuration. Do not use <tab> if you use YouCompleteMe. 
 let g:UltiSnipsExpandTrigger="<C-Space>" 
" let g:UltiSnipsExpandTrigger="<C-Enter>" 
 let g:UltiSnipsJumpForwardTrigger="<C-f>" 
 let g:UltiSnipsJumpBackwardTrigger="<C-b>" 
 
"autocmd FileType css setlocal omnifunc=csscomplete#CompleteCSS 
"autocmd FileType html,markdown setlocal omnifunc=htmlcomplete#CompleteTags 
"autocmd FileType javascript setlocal omnifunc=javascriptcomplete#CompleteJS 
"autocmd FileType python setlocal omnifunc=pythoncomplete#Complete 
"autocmd FileType xml setlocal omnifunc=xmlcomplete#CompleteTags 
 
 
" Specify a directory for plugins (for Neovim: ~/.local/share/nvim/plugged) 
call plug#begin('~/.vim/plugged') 
" support ubunu18.04 
Plug 'ycm-core/YouCompleteMe', {'commit': '93956d747abd9f1ac438c219eb27e4ecd94cdb82'} 
"Plug 'tom-doerr/vim_codex' 
" Make sure you use single quotes 
"Plug 'vim-syntastic/syntastic' 
" Shorthand notation; fetches https://github.com/junegunn/vim-easy-align 
"Plug 'junegunn/vim-easy-align' 
 
" Any valid git URL is allowed 
"Plug 'https://github.com/junegunn/vim-github-dashboard.git' 
 
 
" Multiple Plug commands can be written in a single line using | separators 
"Plug 'SirVer/ultisnips' | Plug 'honza/vim-snippets' 
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



