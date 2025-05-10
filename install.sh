#!/bin/bash
set -e  # Exit on error

# Get the script's directory
DOTFILES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "Installing dotfiles from $DOTFILES_DIR"

# Create function to safely create symbolic links
create_link() {
    local source="$DOTFILES_DIR/$1"
    local target="$2"
    local target_dir="$(dirname "$target")"
    
    # Check if source exists
    if [[ ! -e "$source" ]]; then
        echo "Warning: Source file not found: $source"
        return 1
    fi
    
    # Create target directory if it doesn't exist
    if [[ ! -d "$target_dir" ]]; then
        echo "Creating directory: $target_dir"
        mkdir -p "$target_dir"
    fi
    
    # Create or update symlink
    if [[ -L "$target" ]]; then
        # Symlink exists, update if needed
        local current_link="$(readlink "$target")"
        if [[ "$current_link" != "$source" ]]; then
            echo "Updating existing symlink: $target -> $source"
            ln -sf "$source" "$target"
        else
            echo "Symlink already points to correct location: $target"
        fi
    elif [[ -e "$target" ]]; then
        # File exists but is not a symlink, create backup and link
        echo "Backing up existing file: $target -> $target.backup"
        mv "$target" "$target.backup"
        echo "Creating symlink: $target -> $source"
        ln -s "$source" "$target"
    else
        # Target doesn't exist, create symlink
        echo "Creating symlink: $target -> $source"
        ln -s "$source" "$target"
    fi
}

# Install shell configuration files
echo "Setting up shell configuration..."
create_link ".profile" "$HOME/.profile"
create_link ".bashrc" "$HOME/.bashrc"
create_link ".zshrc" "$HOME/.zshrc"
create_link "ohmyzsh" "$HOME/.oh-my-zsh"
create_link "zsh" "$HOME/.config/zsh"

# Install Git configuration
echo "Setting up Git configuration..."
create_link ".gitconfig" "$HOME/.gitconfig"

# Setup Vim configuration
echo "Setting up Vim configuration..."
create_link "vim" "$HOME/.vim"
create_link ".vimrc" "$HOME/.vimrc"

# Setup Neovim configuration (if needed)
if command -v nvim &> /dev/null; then
    echo "Neovim detected, setting up Neovim configuration..."
    create_link "nvim" "$HOME/.config/nvim"
    
    # Create common.vim directory if it doesn't exist
    if [[ ! -d "$HOME/.vim" ]]; then
        mkdir -p "$HOME/.vim"
    fi
    
    # Ensure common.vim exists
    if [[ ! -f "$DOTFILES_DIR/vim/common.vim" ]]; then
        echo "Warning: common.vim not found, make sure to create it for shared configuration"
    fi
fi

# Install Vim-Plug for Vim
if command -v vim &> /dev/null; then
    echo "Installing Vim-Plug for Vim..."
    if [[ ! -f "$HOME/.vim/autoload/plug.vim" ]]; then
        curl -fLo "$HOME/.vim/autoload/plug.vim" --create-dirs \
            https://raw.githubusercontent.com/junegunn/vim-plug/master/plug.vim
        
        echo "Vim-Plug installed for Vim"
    else
        echo "Vim-Plug already installed for Vim"
    fi
    
    # Automatically install plugins
    echo "Installing Vim plugins..."
    vim -es -u "$HOME/.vimrc" -i NONE -c "PlugInstall" -c "qa"
else
    echo "Vim not detected, skipping Vim-Plug installation for Vim"
fi

# Install Vim-Plug for Neovim (if needed)
if command -v nvim &> /dev/null; then
    echo "Installing Vim-Plug for Neovim..."
    if [[ ! -f "$HOME/.local/share/nvim/site/autoload/plug.vim" ]]; then
        curl -fLo "$HOME/.local/share/nvim/site/autoload/plug.vim" --create-dirs \
            https://raw.githubusercontent.com/junegunn/vim-plug/master/plug.vim
            
        echo "Vim-Plug installed for Neovim"
    else
        echo "Vim-Plug already installed for Neovim"
    fi
    
    # Automatically install plugins
    echo "Installing Neovim plugins..."
    nvim --headless -c 'autocmd User PlugComplete quitall' -c 'PlugInstall' -c 'sleep 500m'
else
    echo "Neovim not detected, skipping Vim-Plug installation for Neovim"
fi

echo "Dotfiles installation complete!"
