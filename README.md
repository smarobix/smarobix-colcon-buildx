# Kria Build Tool

A workspace-agnostic build tool for cross-compiling ROS 2 packages for Xilinx Kria boards using Docker.

## Features

- **Workspace Auto-Detection** - Run from anywhere in your ROS 2 workspace
- **Persistent Build Caching** - Incremental builds using Docker volumes (2-5min rebuilds vs 10-15min)
- **Platform Detection** - Auto-detects x86_64/ARM64 and sets up emulation if needed
- **Flexible Deployment** - Deploy to any remote target via rsync
- **Dry Run Mode** - Test builds locally before deploying
- **Configurable** - Per-workspace configuration via `.kria-build.conf`
- **Pre-built Images** - Uses GitLab Container Registry for fast setup

## Quick Start

### Installation

**One-line install:**
```bash
curl -fsSL git@git.smarobox.de:smarobix/automatica-2025/kria_ros_buildx_compile.git/-/raw/main/install.sh | bash
```

### Prerequisites

**⚠️ IMPORTANT for x86_64 users:**

If you're on an **Intel/AMD processor** (x86_64), you **must** enable ARM64 emulation:

```bash
# Check your architecture
uname -m
# If x86_64 or amd64, run:
docker run --rm --privileged multiarch/qemu-user-static --reset -p yes

# Verify it worked
docker run --rm --platform linux/arm64 alpine uname -m
# Should output: aarch64
```

**Note:** ARM64 machines (Apple Silicon M1/M2/M3, Raspberry Pi, etc.) don't need emulation!

**Authenticate and pull Docker image:**
```bash
# Login to GitLab registry
docker login git.smarobox.de:5050

# Pull the image (after enabling QEMU if on x86_64)
docker pull --platform linux/arm64 git.smarobox.de:5050/smarobix/automatica-2025/kria_ros_cross_compile:jazzy-base
```

### Usage

```bash
# Navigate to any ROS 2 workspace
cd ~/my_ros2_workspace

# Test build (no deployment)
kria-build --dry-run

# Build and deploy to Kria board
kria-build --sync-to kria-board:~/ros2_ws/install/

# Build specific packages
kria-build --dry-run --packages-select my_package
```

## Installation Methods

### Method 1: Standalone Tool (Recommended)

Install globally and use with any ROS 2 workspace:

```bash
# Install
curl -fsSL git@git.smarobox.de:smarobix/automatica-2025/kria_ros_buildx_compile.git/-/raw/main/install.sh | bash

# Use from any workspace
cd ~/workspace_A && kria-build --dry-run
cd ~/workspace_B && kria-build --sync-to kria:~/install/
```

### Method 2: Per-Workspace Install

Copy the script into each workspace:

```bash
cd ~/my_ros2_workspace
curl -fsSL git@git.smarobox.de:smarobix/automatica-2025/kria_ros_buildx_compile.git/-/raw/main/bin/kria-build -o kria-build
chmod +x kria-build

./kria-build --dry-run
```

## Configuration

Create `.kria-build.conf` in your workspace root:

```bash
# .kria-build.conf
KRIA_IMAGE=git.smarobox.de:5050/smarobix/automatica-2025/kria_ros_cross_compile:jazzy-base
KRIA_DEFAULT_TARGET=kria-robotics:~/ros2_ws/install/
KRIA_CONTAINER_NAME=my-project-builder
```

See `.kria-build.conf.example` for all options.

## Architecture Support

| Architecture | Status | QEMU Needed | Notes |
|--------------|--------|-------------|-------|
| x86_64 (Intel/AMD) | ✅ | **Yes** | Must enable QEMU before use |
| ARM64 (Apple Silicon) | ✅ | No | Native ARM64, no emulation |
| ARM64 (Linux/RPi) | ✅ | No | Native ARM64, no emulation |
| ARM64 (Kria board) | ✅ | No | Can build natively on device |

### CI/CD Integration

```yaml
# .gitlab-ci.yml
build:
  script:
    - curl -fsSL https://.../install.sh | bash
    - kria-build --dry-run
    - rsync -avz kria_products/install/ ${DEPLOY_TARGET}
```

## Documentation

- **[INSTALLATION.md](INSTALLATION.md)** - Complete installation guide with platform-specific instructions

## Troubleshooting

### "exec format error"

**Cause:** ARM64 emulation not enabled on x86_64.

**Solution:**
```bash
docker run --rm --privileged multiarch/qemu-user-static --reset -p yes
```

### "Could not find ROS 2 workspace"

**Cause:** Not running from within a ROS 2 workspace.

**Solution:** Navigate to a directory containing a `src/` folder or create one.

### Builds are slow

**Cause:** Container is being rebuilt or cache is lost.

**Solution:** Don't use `--rebuild-container` unless necessary. The tool uses persistent Docker volumes for fast incremental builds.

## Advanced Usage

### Custom Images

```bash
# Use Humble instead of Jazzy
kria-build --image git.smarobox.de:5050/.../humble-base --dry-run

# Use specific commit
kria-build --image git.smarobox.de:5050/.../jazzy-base-abc1234 --dry-run
```

### Selective Builds

```bash
# Build only one package
kria-build --dry-run --packages-select my_package

# Skip packages (e.g., skip visualization on headless Kria)
kria-build --sync-to kria:~/install/ --packages-skip visualization_pkg
```

### Container Management

```bash
# List containers
docker ps -f name=ros2-kria-builder

# Clean and rebuild
kria-build --clean --rebuild-container --dry-run

# Remove all build data
docker rm -f ros2-kria-builder
docker volume rm ros2_kria_build ros2_kria_install
```
