# Colcon-Buildx Extension Guide

## Overview

`colcon-buildx` is a colcon extension that adds cross-compilation support for embedded ARM64 boards. It provides a unified interface for building ROS 2 workspaces targeting boards like Xilinx Kria, Raspberry Pi, NVIDIA Jetson, and other ARM64 platforms.

## Features

- **Two Build Methods**: SSHFS (sysroot mounting) and Docker (containerized)
- **Configuration Files**: `.buildx.conf` or `.buildx.yml` for project-specific settings
- **Automatic Deployment**: Optional rsync deployment to target boards
- **Generic**: Works with any ARM64 board, not just Kria
- **Native Colcon Integration**: Feels like a built-in colcon command

## Installation

### From GitLab (Development)

```bash
# Install in editable mode for development
cd kria_ros_cross_compile
pip install -e .

# Or install directly from GitLab
pip install git+ssh://git@git.smarobox.de/smarobix/automatica-2025/kria_ros_cross_compile.git
```

### From PyPI (Future)

```bash
pip install colcon-buildx
```

### Verify Installation

```bash
colcon buildx --help
```

## Quick Start

### 1. Create Configuration File

In your ROS 2 workspace root, create `.buildx.conf`:

```bash
# Docker method (recommended)
method = docker
docker_image = git.smarobox.de:5050/smarobix/automatica-2025/kria_ros_cross_compile:jazzy-base
deploy_target = ubuntu@kria-vision-home:~/ros2_ws/install/
```

### 2. Build

```bash
cd ~/my_ros2_workspace
colcon buildx
```

### 3. Deploy

```bash
colcon buildx --deploy
```

## Build Methods

### Docker Method (Recommended)

Uses pre-built Docker containers for cross-compilation. **Advantages:**
- ✅ Consistent environment
- ✅ No sysroot mounting complexity
- ✅ Works on any host platform
- ✅ No custom library path issues

**Example:**

```bash
colcon buildx --method docker \
  --docker-image git.smarobox.de:5050/.../jazzy-base
```

**Configuration:**

```bash
# .buildx.conf
method = docker
docker_image = git.smarobox.de:5050/smarobix/automatica-2025/kria_ros_cross_compile:jazzy-base
docker_platform = linux/arm64
```

### SSHFS Sysroot Method

Mounts the target board's filesystem via SSHFS and cross-compiles against it. **Advantages:**
- ✅ Faster builds (no Docker overhead)
- ✅ Direct access to target filesystem
- ✅ Better for debugging

**Disadvantages:**
- ⚠️ Requires SSHFS setup
- ⚠️ Custom library paths can be problematic
- ⚠️ Network-dependent

**Example:**

```bash
colcon buildx --method sysroot \
  --sysroot-host kria-vision-home \
  --toolchain toolchainfile.cmake
```

**Configuration:**

```bash
# .buildx.conf
method = sysroot
sysroot_host = kria-vision-home
sysroot_mount = ~/mnt/kria-sysroot
toolchain = toolchainfile.cmake
```

## Configuration Files

### Format 1: Simple Key=Value (.buildx.conf)

```bash
# Cross-compilation method
method = docker

# Docker settings
docker_image = git.smarobox.de:5050/.../jazzy-base
docker_platform = linux/arm64

# Build directories
build_base = cross_build
install_base = cross_install

# Deployment
deploy = false
deploy_target = ubuntu@kria-vision-home:~/ros2_ws/install/
```

### Format 2: YAML (.buildx.yml)

```yaml
# Cross-compilation method
method: docker

# Docker settings
docker_image: git.smarobox.de:5050/.../jazzy-base
docker_platform: linux/arm64

# Build directories
build_base: cross_build
install_base: cross_install

# Deployment
deploy: false
deploy_target: ubuntu@kria-vision-home:~/ros2_ws/install/
```

### Configuration Priority

1. Command-line arguments (highest priority)
2. Configuration file
3. Default values

## Usage Examples

### Basic Build

```bash
colcon buildx
```

### Build Specific Packages

```bash
colcon buildx --packages-select my_package another_package
```

### Build and Deploy

```bash
colcon buildx --deploy
```

### Override Config File Settings

```bash
# Use Docker even if config says sysroot
colcon buildx --method docker --docker-image custom:image

# Deploy to different target
colcon buildx --deploy --deploy-target ubuntu@192.168.1.100:~/install/
```

### Build with Custom CMake Args

```bash
colcon buildx --cmake-args -DCMAKE_BUILD_TYPE=Release
```

### Clean Build

```bash
# Remove build directories first
rm -rf cross_build cross_install
colcon buildx
```

## Board-Specific Configurations

### Xilinx Kria

```bash
# .buildx.conf
method = docker
docker_image = git.smarobox.de:5050/smarobix/automatica-2025/kria_ros_cross_compile:jazzy-base
deploy_target = ubuntu@kria-vision-home:~/ros2_ws/install/
```

### Raspberry Pi 4/5

```bash
# .buildx.conf
method = docker
docker_image = arm64v8/ros:jazzy-ros-base
deploy_target = pi@raspberrypi:~/ros2_ws/install/
```

### NVIDIA Jetson

```bash
# .buildx.conf
method = sysroot
sysroot_host = jetson-board
toolchain = jetson-toolchain.cmake
deploy_target = nvidia@jetson:~/ros2_ws/install/
```

## Troubleshooting

### Docker Image Not Found

```bash
# Login to GitLab registry
docker login git.smarobox.de:5050

# Verify image exists
docker pull --platform linux/arm64 git.smarobox.de:5050/.../jazzy-base
```

### SSHFS Mount Fails

```bash
# Install SSHFS
# macOS:
brew install macfuse sshfs

# Linux:
sudo apt install sshfs

# Test SSH access
ssh kria-vision-home
```

### Build Fails with "Package Not Found"

Ensure the Docker image or sysroot has all required dependencies:

```bash
# Check what's in the Docker image
docker run --rm -it --platform linux/arm64 your-image bash
apt list --installed | grep ros
```

### Deployment Permission Denied

```bash
# Ensure SSH key is configured
ssh-copy-id ubuntu@kria-vision-home

# Test SSH access
ssh ubuntu@kria-vision-home "ls ~/ros2_ws"
```

## Advanced Usage

### Using Environment Variables

```bash
# Override settings via environment
export BUILDX_METHOD=docker
export BUILDX_DOCKER_IMAGE=my-custom:image
colcon buildx
```

### Pre-mounted Sysroot

```bash
# Mount sysroot manually
sshfs kria-vision-home:/ ~/mnt/kria-sysroot -o allow_other

# Build without mounting
colcon buildx --method sysroot --no-mount
```

### Multiple Target Boards

```bash
# Build once
colcon buildx

# Deploy to multiple boards
for board in kria-1 kria-2 kria-3; do
    rsync -avz cross_install/ ubuntu@$board:~/ros2_ws/install/
done
```

## Integration with CI/CD

### GitLab CI Example

```yaml
cross_compile:
  stage: build
  image: docker:24-dind
  services:
    - docker:24-dind
  before_script:
    - pip install colcon-buildx
  script:
    - colcon buildx --method docker --docker-image $CI_REGISTRY/...
  artifacts:
    paths:
      - cross_install/
```

## Comparison with Standalone Tool

This repository also includes a standalone `kria-build` tool. Here's when to use each:

| Feature | colcon buildx | kria-build |
|---------|---------------|------------|
| Colcon integration | ✅ Native | ❌ Separate command |
| Configuration files | ✅ Yes | ✅ Yes |
| Docker support | ✅ Yes | ✅ Yes |
| SSHFS support | ✅ Yes | ✅ Yes |
| Installation | pip install | curl install script |
| Use case | ROS 2 development | Standalone deployment |

**Recommendation**: Use `colcon buildx` for active ROS 2 development, `kria-build` for automated deployment scripts.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.

## License

Apache License 2.0

## Support

- Issues: https://git.smarobox.de/smarobix/automatica-2025/kria_ros_cross_compile/-/issues
- Documentation: This guide + README.md
