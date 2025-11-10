# Getting Started with Colcon-Buildx

## What We Built

`colcon-buildx` is now a **dual-purpose tool**:

1. **Colcon Extension** - Native `colcon buildx` command
2. **Standalone Tool** - Original `kria-build` script (still works!)

## Installation

### Install the Colcon Extension

```bash
# Navigate to the package directory
cd kria_ros_cross_compile

# Activate your ROS 2 environment
micromamba activate ros_jazzy  # or your ROS environment

# Install in editable mode (for development)
pip install -e .

# Verify installation
colcon buildx --help
```

## Quick Start - Docker Method (Recommended)

### 1. Create Configuration File

In your ROS 2 workspace root (where `src/` is), create `.buildx.conf`:

```bash
# .buildx.conf
method = docker
docker_image = git.smarobox.de:5050/smarobix/automatica-2025/kria_ros_cross_compile:jazzy-base
deploy_target = ubuntu@kria-vision-home:~/ros2_ws/install/
```

### 2. Build

```bash
cd ~/ros2_ws  # Your workspace root
colcon buildx
```

This will:
- ✅ Use the Docker image
- ✅ Cross-compile for ARM64
- ✅ Output to `cross_build/` and `cross_install/`

### 3. Deploy (Optional)

```bash
colcon buildx --deploy
```

This will rsync the `cross_install/` folder to `kria-vision-home`.

## Quick Start - SSHFS Method

If you prefer SSHFS (faster but requires sysroot setup):

### 1. Create Configuration

```bash
# .buildx.conf
method = sysroot
sysroot_host = kria-vision-home
sysroot_mount = ~/mnt/kria-sysroot
toolchain = toolchainfile.cmake
deploy_target = ubuntu@kria-vision-home:~/ros2_ws/install/
```

### 2. Build

```bash
colcon buildx
```

This will:
- ✅ Mount kria-vision-home:/ via SSHFS
- ✅ Cross-compile against the sysroot
- ✅ Unmount when done

## Common Commands

```bash
# Build everything
colcon buildx

# Build specific packages
colcon buildx --packages-select object_tracking_demo

# Build with Release mode
colcon buildx --cmake-args -DCMAKE_BUILD_TYPE=Release

# Override config file
colcon buildx --method docker --docker-image custom:image

# Build and deploy
colcon buildx --deploy

# Deploy to different target
colcon buildx --deploy --deploy-target ubuntu@other-board:~/install/
```

## Configuration Options

### Docker Method

```bash
method = docker
docker_image = git.smarobox.de:5050/.../jazzy-base
docker_platform = linux/arm64
build_base = cross_build
install_base = cross_install
```

### SSHFS Method

```bash
method = sysroot
sysroot_host = kria-vision-home
sysroot_mount = ~/mnt/kria-sysroot
toolchain = toolchainfile.cmake
no_mount = false  # Set to true if already mounted
```

### Deployment

```bash
deploy = false  # Set to true to auto-deploy after build
deploy_target = ubuntu@kria-vision-home:~/ros2_ws/install/
```

## Testing Setup

### Test Docker Method

```bash
# From workspace root
cd ~/automatica/ros2_ws

# Ensure Docker image is available
docker pull --platform linux/arm64 git.smarobox.de:5050/smarobix/automatica-2025/kria_ros_cross_compile:jazzy-base

# Test build (reads .buildx.conf)
colcon buildx

# Should create cross_build/ and cross_install/
ls -la cross_install/
```

### Test SSHFS Method

```bash
# Ensure SSH access works
ssh ubuntu@kria-vision-home

# Test build
colcon buildx --method sysroot \
  --sysroot-host kria-vision-home \
  --toolchain toolchainfile.cmake
```

### Test Deployment

```bash
# Deploy to kria-vision-home
colcon buildx --deploy

# Verify on Kria
ssh ubuntu@kria-vision-home
ls -la ~/ros2_ws/install/
```

## Advantages Over Standalone Tool

| Feature | colcon buildx | kria-build |
|---------|---------------|------------|
| Colcon integration | ✅ Native | ❌ Separate |
| Pass colcon args | ✅ Direct | ⚠️ Via flag |
| Configuration files | ✅ Yes | ✅ Yes |
| Docker support | ✅ Yes | ✅ Yes |
| SSHFS support | ✅ Yes | ✅ Yes |
| Use case | Development | Deployment |

## Why Docker Method is Recommended

✅ **No custom library path issues** - Everything is in the image
✅ **Consistent environment** - Same build every time
✅ **No SSHFS setup** - Just need Docker
✅ **Works offline** - Once image is pulled
✅ **Portable** - Works on any platform with Docker

⚠️ **SSHFS Issues**: You mentioned having problems with custom libraries (like OpenCV in `/opt/install`). Docker method solves this because everything is baked into the image.

## Next Steps

1. ✅ Extension is installed and working
2. ✅ Configuration file created in workspace
3. ✅ Ready to test build

**Try it now:**

```bash
cd ~/automatica/ros2_ws
colcon buildx --packages-select object_tracking_msgs
```

This should cross-compile just the messages package as a quick test!

## Troubleshooting

### "colcon: command not found"

Activate your ROS environment:
```bash
micromamba activate ros_jazzy
```

### "Docker image not found"

Login to GitLab registry:
```bash
docker login git.smarobox.de:5050
```

### "No configuration found"

Create `.buildx.conf` in workspace root:
```bash
cd ~/automatica/ros2_ws
cp kria_ros_cross_compile/.buildx.conf.example .buildx.conf
# Edit as needed
```

## Full Documentation

- **Colcon Extension**: See [COLCON_EXTENSION_GUIDE.md](COLCON_EXTENSION_GUIDE.md)
- **Standalone Tool**: See [README_USAGE.md](README_USAGE.md)
- **Build Optimization**: See [BUILD_OPTIMIZATION.md](BUILD_OPTIMIZATION.md)
