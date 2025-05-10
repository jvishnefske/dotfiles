-- ~/.config/nvim/init.lua

-- Source common configuration
vim.cmd('source ~/.vim/common.vim')

-- Neovim-specific plugin manager (vim-plug)
vim.cmd("call plug#begin()")
vim.fn['plug#']('morhetz/gruvbox')
vim.fn['plug#']('scrooloose/nerdtree')
vim.fn['plug#']('MarcWeber/vim-addon-mw-utils')
vim.fn['plug#']('garbas/vim-snipmate')
vim.fn['plug#']('honza/vim-snippets')
vim.fn['plug#']('vim-airline/vim-airline')
vim.fn['plug#']('tpope/vim-fugitive')
vim.fn['plug#']('kien/ctrlp.vim')

-- Neovim-specific plugins

--vim.fn['plug#']('nomnivore/ollama.nvim')
vim.fn['plug#']('neovim/nvim-lspconfig')
vim.fn['plug#']('hrsh7th/nvim-cmp')
vim.fn['plug#']('hrsh7th/cmp-nvim-lsp')
vim.fn['plug#']('VonHeikemen/lsp-zero.nvim')
vim.fn['plug#']('nvim-treesitter/nvim-treesitter')
vim.fn['plug#']('nvim-treesitter/nvim-treesitter-textobjects')
vim.fn['plug#']('hrsh7th/cmp-buffer')
vim.fn['plug#']('hrsh7th/cmp-path')
vim.fn['plug#']('hrsh7th/cmp-cmdline')
vim.fn['plug#']('L3MON4D3/LuaSnip')
vim.fn['plug#']('saadparwaiz1/cmp_luasnip')
vim.cmd("call plug#end()")

-- Neovim-specific settings
vim.cmd("colorscheme gruvbox")
vim.opt.termguicolors = true

-- LSP Configuration
vim.opt.signcolumn = 'yes'

-- Setup nvim-cmp
local cmp = require('cmp')
cmp.setup({
  snippet = {
    expand = function(args)
      require('luasnip').lsp_expand(args.body)
    end,
  },
  mapping = cmp.mapping.preset.insert({
    ['<C-b>'] = cmp.mapping.scroll_docs(-4),
    ['<C-f>'] = cmp.mapping.scroll_docs(4),
    ['<C-Space>'] = cmp.mapping.complete(),
    ['<C-e>'] = cmp.mapping.abort(),
    ['<CR>'] = cmp.mapping.confirm({ select = true }),
  }),
  sources = cmp.config.sources({
    { name = 'nvim_lsp' },
    { name = 'luasnip' },
    { name = 'buffer' },
    { name = 'path' }
  })
})

-- Add LSP capabilities to lspconfig
local lspconfig_defaults = require('lspconfig').util.default_config
lspconfig_defaults.capabilities = vim.tbl_deep_extend(
  'force',
  lspconfig_defaults.capabilities,
  require('cmp_nvim_lsp').default_capabilities()
)

-- LSP keybindings
vim.api.nvim_create_autocmd('LspAttach', {
  desc = 'LSP actions',
  callback = function(event)
    local opts = {buffer = event.buf}

    vim.keymap.set('n', 'K', '<cmd>lua vim.lsp.buf.hover()<cr>', opts)
    vim.keymap.set('n', 'gd', '<cmd>lua vim.lsp.buf.definition()<cr>', opts)
    vim.keymap.set('n', 'gD', '<cmd>lua vim.lsp.buf.declaration()<cr>', opts)
    vim.keymap.set('n', 'gi', '<cmd>lua vim.lsp.buf.implementation()<cr>', opts)
    vim.keymap.set('n', 'go', '<cmd>lua vim.lsp.buf.type_definition()<cr>', opts)
    vim.keymap.set('n', 'gr', '<cmd>lua vim.lsp.buf.references()<cr>', opts)
    vim.keymap.set('n', 'gs', '<cmd>lua vim.lsp.buf.signature_help()<cr>', opts)
    vim.keymap.set('n', '<F2>', '<cmd>lua vim.lsp.buf.rename()<cr>', opts)
    vim.keymap.set({'n', 'x'}, '<F3>', '<cmd>lua vim.lsp.buf.format({async = true})<cr>', opts)
    vim.keymap.set('n', '<F4>', '<cmd>lua vim.lsp.buf.code_action()<cr>', opts)
  end,
})

-- Configure language servers
-- Configure language servers
local servers = {
  'pyright',           -- Python
  'ts_ls', -- TypeScript/JavaScript (updated from tsserver)
  'rust_analyzer',     -- Rust
  'clangd',            -- C/C++
  'gopls',             -- Go
--  'lua_ls'             -- Lua
}

-- Setup each language server
for _, lsp in ipairs(servers) do
  require('lspconfig')[lsp].setup({})
end

-- Treesitter configuration
require('nvim-treesitter.configs').setup({
  ensure_installed = {
    "lua",
    "vim",
    "vimdoc",
    "query",
    "python",
    "javascript",
    "typescript",
    "c",
    "cpp",
    "rust",
    "go",
  },
  highlight = {
    enable = true,
  },
  indent = {
    enable = true,
  },
  incremental_selection = {
    enable = true,
    keymaps = {
      init_selection = "gnn",
      node_incremental = "grn",
      scope_incremental = "grc",
      node_decremental = "grm",
    },
  },
  textobjects = {
    select = {
      enable = true,
      lookahead = true,
      keymaps = {
        -- You can use the capture groups defined in textobjects.scm
        ["af"] = "@function.outer",
        ["if"] = "@function.inner",
        ["ac"] = "@class.outer",
        ["ic"] = "@class.inner",
      },
    },
  },
})
