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
" Completion via ALE's LSP integration (the 'completers' are the LSP linters
" listed in g:ale_linters below). Install backing tools via .bin/install.yml.
let g:ale_completion_enabled = 1
let g:ale_completion_autoimport = 1
let g:airline#extensions#ale#enabled = 1
let g:ale_fix_on_save = 0
" ALE only runs tools that are actually installed and skips the rest, so it is
" safe to list every fixer/linter here even on a minimal machine.

" Fixers (run with <leader>l / :ALEFix)
let g:ale_fixers = {
\   '*': ['remove_trailing_lines', 'trim_whitespace'],
\   'python': ['ruff', 'isort', 'black'],
\   'c': ['clang-format'],
\   'cpp': ['clang-format'],
\   'cuda': ['clang-format'],
\   'rust': ['rustfmt'],
\   'go': ['gofmt', 'goimports'],
\   'javascript': ['prettier', 'eslint'],
\   'javascriptreact': ['prettier', 'eslint'],
\   'typescript': ['prettier', 'eslint'],
\   'typescriptreact': ['prettier', 'eslint'],
\   'vue': ['prettier', 'eslint'],
\   'json': ['prettier'],
\   'jsonc': ['prettier'],
\   'yaml': ['prettier'],
\   'html': ['prettier'],
\   'css': ['prettier'],
\   'scss': ['prettier'],
\   'less': ['prettier'],
\   'markdown': ['prettier'],
\   'graphql': ['prettier'],
\   'sh': ['shfmt'],
\   'bash': ['shfmt'],
\   'zsh': ['shfmt'],
\   'lua': ['stylua'],
\   'sql': ['pgformatter'],
\   'toml': ['dprint'],
\}

" Linters / completers (LSP servers provide completion when present)
let g:ale_linters = {
\   'python': ['pyright', 'ruff', 'flake8'],
\   'c': ['clangd'],
\   'cpp': ['clangd'],
\   'rust': ['analyzer'],
\   'go': ['gopls', 'gofmt'],
\   'javascript': ['eslint', 'tsserver'],
\   'javascriptreact': ['eslint', 'tsserver'],
\   'typescript': ['eslint', 'tsserver'],
\   'typescriptreact': ['eslint', 'tsserver'],
\   'sh': ['shellcheck', 'language_server'],
\   'bash': ['shellcheck', 'language_server'],
\   'yaml': ['yamllint', 'yaml_language_server'],
\   'json': ['jsonlint'],
\   'lua': ['lua_language_server'],
\   'vim': ['vint'],
\   'markdown': ['markdownlint'],
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
