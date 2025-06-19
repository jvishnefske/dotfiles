" ~/.vimrc

" Source common configuration
source ~/.vim/common.vim

" Vim-specific plugin manager (vim-plug)
call plug#begin('~/.vim/plugged')
Plug 'morhetz/gruvbox'
Plug 'scrooloose/nerdtree', { 'on':  'NERDTreeToggle' }
Plug 'dense-analysis/ale'
Plug 'vim-airline/vim-airline'
Plug 'tpope/vim-fugitive'
Plug 'garbas/vim-snipmate'
Plug 'honza/vim-snippets'
Plug 'MarcWeber/vim-addon-mw-utils'
Plug 'tomtom/tlib_vim'
Plug 'godlygeek/tabular'
Plug 'vim-scripts/VOoM'
Plug 'kien/ctrlp.vim'
call plug#end()

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
autocmd VimEnter * call StartUp()
