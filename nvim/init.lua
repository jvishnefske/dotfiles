-- ~/.config/nvim/init.lua

-- Source common configuration
vim.cmd('source ~/.vim/common.vim')


cmp.setup({
  mapping = {
    ['<Tab>'] = cmp.mapping(function(fallback)
      if cmp.visible() then
        cmp.select_next_item()
      elseif luasnip.expand_or_jumpable() then
        luasnip.expand_or_jump()
      else
        fallback()
      end
    end, { 'i', 's' }),
  }
})
