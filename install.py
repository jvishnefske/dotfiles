#!/usr/bin/env python3

import os
import shutil
import subprocess
import sys
from pathlib import Path

# Get the directory where the script is located
DOTFILES_DIR = Path(__file__).parent.resolve()
HOME_DIR = Path.home()

def create_link(source_rel, target_rel=None):
    """Create a symbolic link from DOTFILES_DIR/source to HOME_DIR/target"""
    source = DOTFILES_DIR / source_rel
    target = HOME_DIR / (target_rel if target_rel else source_rel)
    
    # Check if source exists
    if not source.exists():
        print(f"Warning: Source file not found: {source}")
        return False
    
    # Create target directory if it doesn't exist
    target_dir = target.parent
    if not target_dir.exists():
        print(f"Creating directory: {target_dir}")
        target_dir.mkdir(parents=True)
    
    # Handle existing target
    if target.is_symlink():
        current_link = target.resolve()
        if current_link != source:
            print(f"Updating existing symlink: {target} -> {source}")
            target.unlink()
            target.symlink_to(source)
        else:
            print(f"Symlink already points to correct location: {target}")
    elif target.exists():
        backup = Path(f"{target}.backup")
        print(f"Backing up existing file: {target} -> {backup}")
        shutil.move(target, backup)
        print(f"Creating symlink: {target} -> {source}")
        target.symlink_to(source)
    else:
        print(f"Creating symlink: {target} -> {source}")
        target.symlink_to(source)
    
    return True

def command_exists(cmd):
    """Check if a command exists in PATH"""
    return shutil.which(cmd) is not None

def install_vim_plug(vim_type):
    """Install vim-plug for either Vim or Neovim"""
    if vim_type == "vim":
        plug_path = HOME_DIR / ".vim/autoload/plug.vim"
        curl_cmd = f"curl -fLo {plug_path} --create-dirs https://raw.githubusercontent.com/junegunn/vim-plug/master/plug.vim"
        install_cmd = "vim -es -u ~/.vimrc -i NONE -c 'PlugInstall' -c 'qa'"
    else:  # neovim
        plug_path = HOME_DIR / ".local/share/nvim/site/autoload/plug.vim"
        curl_cmd = f"curl -fLo {plug_path} --create-dirs https://raw.githubusercontent.com/junegunn/vim-plug/master/plug.vim"
        install_cmd = "nvim --headless -c 'autocmd User PlugComplete quitall' -c 'PlugInstall'"
    
    if not plug_path.exists():
        print(f"Installing Vim-Plug for {vim_type.capitalize()}...")
        subprocess.run(curl_cmd, shell=True, check=True)
        print(f"Vim-Plug installed for {vim_type.capitalize()}")
    else:
        print(f"Vim-Plug already installed for {vim_type.capitalize()}")
    
    # Install plugins
    print(f"Installing {vim_type.capitalize()} plugins...")
    try:
        subprocess.run(install_cmd, shell=True, check=True)
    except subprocess.CalledProcessError:
        print(f"Warning: Plugin installation for {vim_type.capitalize()} failed, you may need to run it manually")

def main():
    print(f"Installing dotfiles from {DOTFILES_DIR}")
    
    # Install shell configuration files
    print("Setting up shell configuration...")
    create_link(".profile")
    create_link(".bashrc")
    create_link(".zshrc")
    create_link("ohmyzsh", ".oh-my-zsh")
    create_link("zsh", ".config/zsh")
    
    # Install Git configuration
    print("Setting up Git configuration...")
    create_link(".gitconfig")
    
    # Setup Vim configuration
    print("Setting up Vim configuration...")
    create_link("vim", ".vim")
    create_link(".vimrc")
    
    # Setup Neovim configuration (if needed)
    if command_exists("nvim"):
        print("Neovim detected, setting up Neovim configuration...")
        create_link("nvim", ".config/nvim")
        
        # Ensure common.vim directory exists
        vim_dir = HOME_DIR / ".vim"
        if not vim_dir.exists():
            vim_dir.mkdir(parents=True)
        
        # Check for common.vim
        common_vim = DOTFILES_DIR / "vim/common.vim"
        if not common_vim.exists():
            print("Warning: common.vim not found, make sure to create it for shared configuration")
    
    # Install Vim-Plug for Vim
    if command_exists("vim"):
        install_vim_plug("vim")
    else:
        print("Vim not detected, skipping Vim-Plug installation for Vim")
    
    # Install Vim-Plug for Neovim
    if command_exists("nvim"):
        install_vim_plug("neovim")
    else:
        print("Neovim not detected, skipping Vim-Plug installation for Neovim")
    
    print("Dotfiles installation complete!")

if __name__ == "__main__":
    main()
