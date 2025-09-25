# dotfiles

Personal terminal and development environment configuration files for a productive development setup.

## Features

- **Shell Configuration**: Zsh with Oh-My-Zsh, Bash, and shared profile settings
- **Text Editors**: Vim and Neovim configurations with plugin management
- **Git Configuration**: Personal Git settings and aliases
- **Development Tools**: Python virtual environment wrapper, NATS tools
- **System Configuration**: Network mounting, systemd services
- **Automated Installation**: Ansible-based setup with dependency management

## Quick Start

### Prerequisites

The installer will automatically check for and offer to install `uv` if not present. You can also install it manually:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Installation

1. Clone the repository:
   ```bash
   git clone <repository-url> ~/.dotfiles
   cd ~/.dotfiles
   ```

2. Run the installer:
   ```bash
   ./install.sh
   ```

The installer will:
- Check for `uv` and prompt to install if missing
- Use Ansible (via `uvx`) to configure your system
- Create symbolic links for all configuration files
- Install Vim/Neovim plugins automatically
- Set up development tools (Rust, Python, Go, NATS)

## File Structure

```
.
├── install.sh          # Main installation script
├── install.yml         # Ansible playbook for system setup
├── install.py          # Deprecated Python installer
├── .bashrc             # Bash configuration
├── .zshrc              # Zsh configuration  
├── .profile            # Shared shell profile
├── .gitconfig          # Git configuration
├── .vimrc              # Vim configuration
├── vim/                # Vim configuration directory
├── nvim/               # Neovim configuration
├── ohmyzsh/            # Oh-My-Zsh framework (git submodule)
├── system.yml          # System-level Ansible configuration
├── setup_vcpkg.yml     # C++ package manager setup
└── virtualenvwrapper.sh # Python virtual environment tools
```

## What Gets Installed

### Shell Environment
- Zsh with Oh-My-Zsh framework
- Custom aliases and functions
- Enhanced prompt and completion

### Development Tools
- **Rust**: rustup toolchain manager
- **Python**: uv package manager and uvx runner
- **Go**: NATS ecosystem tools (nats-cli, nats-server, nkeys)
- **Vim/Neovim**: Vim-Plug plugin manager with automatic plugin installation

### Configuration Files
All configuration files are symlinked from this repository to your home directory:
- `~/.bashrc` → `.bashrc`
- `~/.zshrc` → `.zshrc`
- `~/.profile` → `.profile`
- `~/.gitconfig` → `.gitconfig`
- `~/.vimrc` → `.vimrc`
- `~/.vim/` → `vim/`
- `~/.config/nvim/` → `nvim/`
- `~/.oh-my-zsh/` → `ohmyzsh/`

## Manual Usage

### Using Ansible Directly

You can run specific parts of the setup:

```bash
# Install only Python tools
uvx --from ansible-core ansible-playbook install.yml --tags python

# Install only shell configuration
uvx --from ansible-core ansible-playbook install.yml --tags shell

# Install only Vim/Neovim
uvx --from ansible-core ansible-playbook install.yml --tags vim,nvim
```

### Legacy Installation

The Python installer (`install.py`) is deprecated but still functional. It will show a deprecation warning and recommend using `install.sh` instead.

## Customization

- Edit configuration files directly in the repository
- Changes are immediately reflected via symbolic links
- Add custom Vim plugins to `.vimrc`
- Modify shell aliases in `.zshrc` or `.bashrc`
- Update Ansible playbooks for system-level changes

## Platform Support

- **Primary**: macOS, Linux
- **Tested**: Ubuntu, CentOS/RHEL, macOS
- **Requirements**: curl, bash, git

## Troubleshooting

- **uv not found**: The installer will prompt to install it automatically
- **Ansible errors**: Ensure `uvx --from ansible-core` works in your environment
- **Permission issues**: Some system configurations may require sudo access
- **Plugin installation fails**: Run `:PlugInstall` manually in Vim/Neovim

## Contributing

This is a personal dotfiles repository, but feel free to fork and adapt for your own use. Pull requests for bug fixes are welcome.
