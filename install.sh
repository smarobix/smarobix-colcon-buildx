#!/bin/bash
set -e

# Kria Build Tool Installer
# Installs kria-build to ~/.local/bin

INSTALL_DIR="${HOME}/.local/bin"
SCRIPT_NAME="kria-build"
REPO_URL="git@git.smarobox.de:smarobix/automatica-2025/kria_ros_buildx_compile.git"

echo "🚀 Installing Kria Build Tool..."

# Create install directory if it doesn't exist
mkdir -p "$INSTALL_DIR"

# Download the main script
echo "📥 Downloading $SCRIPT_NAME..."
if command -v curl &> /dev/null; then
    curl -fsSL "${REPO_URL}/bin/${SCRIPT_NAME}" -o "${INSTALL_DIR}/${SCRIPT_NAME}"
elif command -v wget &> /dev/null; then
    wget -q "${REPO_URL}/bin/${SCRIPT_NAME}" -O "${INSTALL_DIR}/${SCRIPT_NAME}"
else
    echo "❌ Error: Neither curl nor wget found. Please install one of them."
    exit 1
fi

# Make executable
chmod +x "${INSTALL_DIR}/${SCRIPT_NAME}"

# Check if ~/.local/bin is in PATH
if [[ ":$PATH:" != *":$INSTALL_DIR:"* ]]; then
    echo ""
    echo "⚠️  ${INSTALL_DIR} is not in your PATH"
    echo ""
    echo "Add this to your ~/.bashrc or ~/.zshrc:"
    echo ""
    echo "    export PATH=\"\$HOME/.local/bin:\$PATH\""
    echo ""
    echo "Then run: source ~/.bashrc  (or source ~/.zshrc)"
fi

echo ""
echo "✅ Installation complete!"
echo ""
echo "Next steps:"
echo "  1. Verify installation: kria-build --help"
echo "  2. Enable ARM64 emulation (x86_64 only):"
echo "     docker run --rm --privileged multiarch/qemu-user-static --reset -p yes"
echo "  3. Pull Docker image:"
echo "     docker pull --platform linux/arm64 git.smarobox.de:5050/smarobix/automatica-2025/kria_ros_cross_compile:jazzy-base"
echo "  4. Navigate to your ROS 2 workspace and run: kria-build --dry-run"
echo ""
