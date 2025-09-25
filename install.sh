#!/bin/bash
set -e  # Exit on error

# Get the script's directory
DOTFILES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "Installing dotfiles from $DOTFILES_DIR"

# Function to check if uv is installed
check_uv() {
    if command -v uv &> /dev/null; then
        echo "uv is already installed"
        return 0
    else
        return 1
    fi
}

# Function to install uv
install_uv() {
    echo "uv is not installed."
    read -p "Would you like to install uv? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Installing uv..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
        
        # Source the shell configuration to make uv available
        if [[ -f "$HOME/.cargo/env" ]]; then
            source "$HOME/.cargo/env"
        fi
        
        # Add to PATH for current session
        export PATH="$HOME/.cargo/bin:$PATH"
        
        # Verify installation
        if command -v uv &> /dev/null; then
            echo "uv installed successfully"
            return 0
        else
            echo "Error: uv installation failed"
            return 1
        fi
    else
        echo "uv installation cancelled. Cannot proceed with ansible installation."
        exit 1
    fi
}

# Function to run ansible playbook
run_ansible() {
    echo "Running ansible playbook to install dotfiles..."
    
    # Check if install.yml exists
    if [[ ! -f "$DOTFILES_DIR/install.yml" ]]; then
        echo "Error: install.yml not found in $DOTFILES_DIR"
        exit 1
    fi
    
    # Run ansible playbook using uvx
    uvx --from ansible-core ansible-playbook "$DOTFILES_DIR/install.yml"
}

# Main installation flow
echo "Checking for uv installation..."

if ! check_uv; then
    install_uv
fi

# Run the ansible playbook
run_ansible

echo "Dotfiles installation complete!"
