# Installation Guide

## Overview

This build tool can be used with any ROS 2 workspace to cross-compile for Kria boards using Docker.

## Quick Install (Recommended)

### Option 1: Install from Repository

```bash
# Clone to a tools directory
mkdir -p ~/tools
git clone https://git.smarobox.de/smarobix/kria-build-tools.git ~/tools/kria-build-tools

# Add to PATH (add to ~/.bashrc or ~/.zshrc for persistence)
export PATH="$HOME/tools/kria-build-tools/bin:$PATH"

# Verify installation
kria-build --help
```

### Option 2: One-Line Install via curl

```bash
curl -fsSL https://git.smarobox.de/smarobix/kria-build-tools/raw/main/install.sh | bash
```

This will:
- Download the script to `~/.local/bin/kria-build`
- Make it executable
- Add to PATH if needed

### Option 3: Manual Install

```bash
# Download the script
curl -fsSL https://git.smarobox.de/smarobix/kria-build-tools/raw/main/bin/kria-build -o kria-build
chmod +x kria-build

# Move to a directory in your PATH
sudo mv kria-build /usr/local/bin/
# OR
mv kria-build ~/.local/bin/
```

## Prerequisites

### 1. Docker Installation

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-buildx
sudo usermod -aG docker $USER
# Log out and back in for group changes to take effect
```

**macOS:**
```bash
brew install docker docker-buildx
# Or install Docker Desktop
```

### 2. ARM64 Emulation (x86_64 hosts only)

⚠️ **IMPORTANT**: If you're running on an x86_64 machine, you **must** enable ARM64 emulation before using this tool or pulling ARM64 Docker images.

**Check your architecture:**
```bash
uname -m
# If output is x86_64 or amd64, you need emulation
# If output is aarch64 or arm64, you can skip this step
```

**Enable QEMU (x86_64 only):**
```bash
docker run --rm --privileged multiarch/qemu-user-static --reset -p yes

# Verify it works
docker run --rm --platform linux/arm64 alpine uname -m
# Should output: aarch64
```

**Verify emulation is enabled:**
```bash
ls /proc/sys/fs/binfmt_misc/ | grep qemu
# Should show qemu-aarch64 and other architectures
```

**Common errors without QEMU:**
```
exec /bin/sh: exec format error
# OR
Error response from daemon: image with reference ... was found but does not match the specified platform
```

### 3. GitLab Registry Authentication (for pre-built images)

```bash
# Create personal access token at: https://git.smarobox.de/-/user_settings/personal_access_tokens
# Scopes needed: read_registry

export GITLAB_TOKEN="glpat-xxxxxxxxxxxxxxxxxxxx"
echo $GITLAB_TOKEN | docker login git.smarobox.de:5050 -u <your-username> --password-stdin
```

### 4. Pull the Docker Image

```bash
# After enabling QEMU (if needed) and authenticating
docker pull --platform linux/arm64 git.smarobox.de:5050/smarobix/automatica-2025/kria_ros_cross_compile:jazzy-base
```

## Usage

Once installed, navigate to **any** ROS 2 workspace and run:

```bash
cd ~/my_ros2_workspace

# Test build
kria-build --dry-run

# Build and deploy
kria-build --sync-to kria-board:~/ros2_ws/install/
```

The tool automatically:
- Detects the workspace root
- Validates workspace structure
- Mounts the correct directories
- Uses persistent Docker volumes for speed

## Workspace Configuration (Optional)

Create `.kria-build.conf` in your workspace root for project-specific settings:

```bash
# .kria-build.conf
KRIA_IMAGE=git.smarobox.de:5050/smarobix/automatica-2025/kria_ros_cross_compile:jazzy-base
KRIA_DEFAULT_TARGET=kria-robotics:~/ros2_ws/install/
KRIA_CONTAINER_NAME=my-project-builder
```

## Uninstall

```bash
# Remove the tool
rm ~/.local/bin/kria-build
# OR
sudo rm /usr/local/bin/kria-build

# Remove Docker volumes (optional)
docker volume rm ros2_kria_build ros2_kria_install

# Remove container (optional)
docker rm -f ros2-kria-builder
```

## Platform-Specific Notes

### macOS (Apple Silicon M1/M2/M3)

✅ **No QEMU needed** - Apple Silicon is ARM64 native!

```bash
uname -m  # Should show: arm64
# Skip the QEMU setup entirely
```

### macOS (Intel)

⚠️ **QEMU required** - Intel Macs are x86_64:

```bash
# Enable emulation first
docker run --rm --privileged multiarch/qemu-user-static --reset -p yes

# Then pull and use normally
```

### Linux (x86_64)

⚠️ **QEMU required**:

```bash
# One-time setup
docker run --rm --privileged multiarch/qemu-user-static --reset -p yes

# Make persistent across reboots (optional)
sudo apt-get install qemu-user-static
```

### Linux (ARM64 / Raspberry Pi 4/5)

✅ **No QEMU needed** - Already ARM64!

## Troubleshooting

### "exec format error"

**Cause:** ARM64 emulation not enabled on x86_64.

**Solution:**
```bash
docker run --rm --privileged multiarch/qemu-user-static --reset -p yes
```

### "Cannot connect to Docker daemon"

**Cause:** Docker not running or user not in docker group.

**Solution:**
```bash
# Start Docker (Linux)
sudo systemctl start docker

# Add user to docker group
sudo usermod -aG docker $USER
# Log out and back in
```

### "Image not found" when pulling

**Cause:** Not authenticated to GitLab registry.

**Solution:**
```bash
docker login git.smarobox.de:5050
```

## Next Steps

After installation, see:
- `kria-build --help` - Command reference
- `README_USAGE.md` - Detailed usage guide
- `BUILD_OPTIMIZATION.md` - Performance optimization tips
