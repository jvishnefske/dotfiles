"set nocompatable
"source ~/.dotfiles/ultimate.vim

function! BuildYCM(info)
    if a:info.status == 'installed' || a:info.force
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
Plug 'ycm-core/YouCompleteMe'
" Make sure you use single quotes
Plug 'vim-syntastic/syntastic'
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
Plug 'pangloss/vim-javascript'
" Using a non-master branch
"Plug 'rdnetto/YCM-Generator', { 'branch': 'stable' }
"Plug 'Shougo/neocomplete.vim'
"Plug 'mjbrownie/pythoncomplete.vim'

" Using a tagged release; wildcard allowed (requires git 1.9.2 or above)
Plug 'fatih/vim-go', { 'tag': '*' }
Plug 'tpope/vim-fugitive'
" Plugin options
"Plug 'nsf/gocode', { 'tag': 'v.20150303', 'rtp': 'vim' }

" Plugin outside ~/.vim/plugged with post-update hook
"Plug 'junegunn/fzf', { 'dir': '~/.fzf', 'do': './install --all' }

" Initialize plugin system
call plug#end()
