# Kria Build Tools

Cross-compilation tools for ROS 2 targeting embedded ARM64 boards (Xilinx Kria, Raspberry Pi, NVIDIA Jetson, etc.).

## Overview

`colcon-buildx` is a colcon extension that adds cross-compilation support for embedded ARM64 boards. It provides native colcon integration with support for Docker-based and SSHFS-based cross-compilation.

**Features:**
- **Native Colcon Integration** - `colcon buildx` command with full colcon argument support
- **Two Build Methods** - Docker (containerized) and SSHFS (sysroot mounting - untested)
- **Configuration Files** - `.buildx.conf` or `.buildx.yml` for project-specific settings
- **Automatic Deployment** - Optional rsync deployment to target boards
- **Generic** - Works with any ARM64 board with a Docker image

## Installation

### Colcon Extension (Recommended)

```bash
# Install directly from GitLab
pip install git+ssh://git@git.smarobox.de:smarobix/automatica-2025/kria_ros_buildx_compile.git

# Or install in editable mode for development
cd kria_ros_cross_compile
pip install -e .

# Verify installation
colcon buildx --help
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

This will:
- Use the Docker image
- Cross-compile for ARM64
- Output to `cross_build/` and `cross_install/`

### 3. Deploy (Optional)

```bash
colcon buildx --deploy
```

## Build Methods

### Docker Method (Recommended)

Uses pre-built Docker containers for cross-compilation.

**Configuration:**

```bash
# .buildx.conf
method = docker
docker_image = git.smarobox.de:5050/smarobix/automatica-2025/kria_ros_cross_compile:jazzy-base
docker_platform = linux/arm64
build_base = cross_build
install_base = cross_install
```

**Usage:**

```bash
colcon buildx --method docker \
  --docker-image git.smarobox.de:5050/.../jazzy-base
```

### SSHFS Sysroot Method

Mounts the target board's filesystem via SSHFS and cross-compiles against it.

**Configuration:**

```bash
# .buildx.conf
method = sysroot
sysroot_host = kria-vision-home
sysroot_mount = ~/mnt/kria-sysroot
toolchain = toolchainfile.cmake
deploy_target = ubuntu@kria-vision-home:~/ros2_ws/install/
```

**Usage:**

```bash
colcon buildx --method sysroot \
  --sysroot-host kria-vision-home \
  --toolchain toolchainfile.cmake
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

### Build with Custom CMake Args

```bash
colcon buildx --cmake-args -DCMAKE_BUILD_TYPE=Release
```

### Override Configuration

```bash
colcon buildx --method docker --docker-image custom:image
```

### Deploy to Different Target

```bash
colcon buildx --deploy --deploy-target ubuntu@other-board:~/install/
```

### Clean Build

```bash
# Remove build directories first
rm -rf cross_build cross_install
colcon buildx
```

### Selective Builds

```bash
# Build only one package
colcon buildx --packages-select my_package

# Skip packages (e.g., skip visualization on headless Kria)
colcon buildx --packages-skip visualization_pkg --deploy
```

## CI/CD Integration

### GitLab CI Example

```yaml
cross_compile:
  stage: build
  image: docker:24-dind
  services:
    - docker:24-dind
  before_script:
    - pip install git+ssh://git@git.smarobox.de:smarobix/automatica-2025/kria_ros_buildx_compile.git
  script:
    - colcon buildx --method docker --docker-image $CI_REGISTRY/...
  artifacts:
    paths:
      - cross_install/
```

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

### "colcon: command not found"

**Cause:** ROS environment not activated.

**Solution:**
```bash
source /opt/ros/humble/setup.bash  # or jazzy
```

### "Docker image not found"

**Cause:** Not authenticated to GitLab registry.

**Solution:**
```bash
docker login git.smarobox.de:5050
```

### "No configuration found"

**Cause:** Missing `.buildx.conf` in workspace root.

**Solution:**
```bash
cd ~/my_ros2_workspace
cp kria_ros_cross_compile/.buildx.conf.example .buildx.conf
# Edit as needed
```

### Builds are slow

**Cause:** Container is being rebuilt or cache is lost.

**Solution:** Don't use `--rebuild-container` unless necessary. The tool uses persistent Docker volumes for fast incremental builds.

## Advanced Usage

### Custom Images

```bash
# Use Humble instead of Jazzy
colcon buildx --docker-image git.smarobox.de:5050/.../humble-base

# Use specific commit
colcon buildx --docker-image git.smarobox.de:5050/.../jazzy-base-abc1234
```

### Container Management

```bash
# List containers
docker ps -f name=buildx

# Clean and rebuild
rm -rf cross_build cross_install
colcon buildx

# Remove Docker volumes if needed
docker volume ls | grep buildx
```

## Legacy Standalone Tool

The original `kria-build` script is maintained for deployment scripts and CI/CD pipelines that don't use colcon directly.

**Installation:**
```bash
curl -fsSL git@git.smarobox.de:smarobix/automatica-2025/kria_ros_buildx_compile.git/-/raw/main/install.sh | bash
```

**Usage:**
```bash
cd ~/ros2_workspace
kria-build --dry-run
kria-build --sync-to kria-board:~/ros2_ws/install/
```

The standalone tool uses the same configuration files (`.buildx.conf`) and Docker images as the colcon extension.
