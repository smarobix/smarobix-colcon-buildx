# ROS2 Kria Build Optimization Guide

This workspace provides multiple build strategies to optimize ROS2 package builds for Kria, focusing on incremental builds and caching to avoid rebuilding unchanged packages.

**🆕 New Features:**
- Uses pre-built Docker images from GitLab Container Registry (`git.smarobox.de:5050`)
- `--dry-run` flag for building without syncing to remote
- `--sync-to <target>` flag for flexible deployment targets
- `--image` flag to use custom Docker images (ROS distro auto-detected from image name)
- Automatic workspace detection - run from anywhere in the workspace
- Workspace source validation before build starts

## 🚀 Quick Start - Choose Your Build Strategy

### Option 1: Persistent Container (Recommended for Development)
```bash
# Dry run - build without syncing to remote
./build_persistent.sh --dry-run

# Build and sync to Kria board
./build_persistent.sh --sync-to kria-robotics:~/ros2_ws/install/

# Build and sync to custom target
./build_persistent.sh --sync-to user@192.168.1.100:~/ros2_demo_ws/install/

# Subsequent builds (incremental, very fast)
./build_persistent.sh --sync-to kria-robotics:~/ros2_ws/install/

# Clean build artifacts when needed
./build_persistent.sh --clean --sync-to kria-robotics:~/ros2_ws/install/

# Force container rebuild
./build_persistent.sh --rebuild-container --sync-to kria-robotics:~/ros2_ws/install/

# See all options
./build_persistent.sh --help
```

### Option 2: Improved Docker Caching
```bash
# Uses improved Dockerfile with better layer caching
./build_cached.sh

# Disable cache for fresh build
./build_cached.sh --no-cache

# Update dependencies
./build_cached.sh --update-deps
```

### Option 3: Package-layered Caching
```bash
# Uses package-specific layers for optimal caching
docker buildx build --platform linux/arm64 \
  -f Dockerfile.layered \
  --target export \
  --output type=local,dest=./kria_products .
```

## 📊 Performance Comparison

| Strategy | First Build | Subsequent Builds | Use Case |
|----------|-------------|-------------------|----------|
| Original | ~10-15 min | ~10-15 min | One-off builds |
| Persistent Container | ~10-15 min | ~2-5 min | Development workflow |
| Improved Docker | ~10-15 min | ~5-8 min | CI/CD pipeline |
| Package Layered | ~10-15 min | ~3-6 min | Complex dependencies |

## 🛠 Build Strategies Explained

### 1. Persistent Container (`build_persistent.sh`)
- **How it works**: Creates a long-running container with mounted volumes for build artifacts
- **Pros**: True incremental builds, fastest subsequent builds, colcon's built-in caching works perfectly
- **Cons**: Requires managing container lifecycle, uses Docker volumes
- **Best for**: Active development where you build frequently

### 2. Improved Docker Caching (`build_cached.sh` + `Dockerfile.incremental`)
- **How it works**: Optimizes Docker layer caching by copying dependencies separately
- **Pros**: No persistent containers, good for CI/CD, respects Docker best practices
- **Cons**: Still rebuilds more than necessary, limited by Docker layer caching
- **Best for**: CI/CD pipelines, occasional builds

### 3. Package-layered Caching (`Dockerfile.layered`)
- **How it works**: Separates packages into layers based on change frequency
- **Pros**: Optimal caching for package dependencies, interface packages cached separately
- **Cons**: More complex Dockerfile, requires understanding package dependencies
- **Best for**: Complex workspaces with clear package hierarchies

## 📁 Package Organization Strategy

The layered approach organizes packages by change frequency:

1. **Interface packages** (rarely change): `*_msgs` packages
2. **Core packages** (occasionally change): `axi_dma_cpp`, transport packages
3. **Application packages** (frequently change): demo and application packages

## 📂 Workspace Structure & Build Artifacts

### Where to Run the Script

The script can be run from either:
- **Workspace root**: `/path/to/ros2_ws/`
- **Script directory**: `/path/to/ros2_ws/kria_ros_cross_compile/`

The script automatically detects the workspace root and validates that `src/` exists.

### Build Artifact Locations

```
ros2_ws/                           # Workspace root (auto-detected)
├── src/                          # Your ROS packages (mounted read-only in container)
├── kria_products/                # Build output directory (created by script)
│   └── install/                  # Install folder to deploy
└── kria_ros_cross_compile/
    └── build_persistent.sh       # This script
```

**Key Points:**
- Source code is mounted as **read-only** (`src/` → `/opt/ros_ws/src:ro`)
- Build artifacts go to Docker volumes (persistent between builds)
- Install folder is extracted to `ros2_ws/kria_products/install/`
- The script validates workspace structure before starting

## 🔧 Advanced Usage

### Common Workflows

**Development workflow:**
```bash
# 1. Test build locally first
./build_persistent.sh --dry-run

# 2. If successful, sync to Kria
./build_persistent.sh --sync-to kria-robotics:~/ros2_ws/install/

# 3. Make changes, then incremental build
./build_persistent.sh --sync-to kria-robotics:~/ros2_ws/install/
```

**Multiple target boards:**
```bash
# Build once, deploy to multiple boards
./build_persistent.sh --dry-run

# Deploy to board 1
rsync -avz ./kria_products/install/ kria-board-1:~/ros2_ws/install/

# Deploy to board 2
rsync -avz ./kria_products/install/ kria-board-2:~/ros2_ws/install/
```

**Using custom Docker images:**
```bash
# Use specific commit SHA (jazzy)
./build_persistent.sh --image git.smarobox.de:5050/smarobix/automatica-2025/kria_ros_cross_compile:jazzy-base-abc1234 --dry-run

# Use Humble-based image (ROS distro auto-detected from image name)
./build_persistent.sh --image git.smarobox.de:5050/smarobix/automatica-2025/kria_ros_cross_compile:humble-base --dry-run

# Use local custom image
./build_persistent.sh --image my-custom-ros2:latest --dry-run
```

**Important Notes:**
- The script automatically detects the workspace root (parent directory containing `src/`)
- ROS distribution is determined by the Docker image, not a command-line flag
- If using `--image` with "humble" in the name, it auto-detects ROS Humble
- Default image uses ROS 2 Jazzy

### Persistent Container Management
```bash
# Check container status
docker ps -a -f name=ros2-kria-builder

# Stop container
docker stop ros2-kria-builder

# Remove container and volumes
docker rm -f ros2-kria-builder
docker volume rm ros2_kria_build ros2_kria_install
```

### Selective Package Building
```bash
# Build only specific packages (dry run)
./build_persistent.sh --dry-run --packages-select object_tracking_demo

# Build up to a specific package and sync
./build_persistent.sh --sync-to kria-robotics:~/ros2_ws/install/ --packages-up-to object_tracking_demo

# Skip specific packages
./build_persistent.sh --sync-to kria-robotics:~/ros2_ws/install/ --packages-skip object_tracking_visualization

# Test build locally before syncing
./build_persistent.sh --dry-run --packages-select object_tracking_fpga
# Then if successful:
./build_persistent.sh --sync-to kria-robotics:~/ros2_ws/install/ --packages-select object_tracking_fpga
```

### Debugging Build Issues
```bash
# Access the persistent container
docker exec -it ros2-kria-builder bash

# Check build logs
docker exec ros2-kria-builder find /opt/ros_ws/log -name "*.log" -exec tail -20 {} \;
```

## 📈 Monitoring Build Performance

### Build Time Tracking
```bash
# Time your builds
time ./build_persistent.sh

# Check what packages were built
docker exec ros2-kria-builder colcon list --packages-select-built
```

### Cache Hit Analysis
```bash
# Check Docker layer cache usage
docker system df

# Analyze build cache
docker buildx du
```

## 🔄 Migration from Original Script

To migrate from your original `build_and_extract.sh`:

1. **For development**: Use `build_persistent.sh`
   ```bash
   # Replace this:
   ./build_and_extract.sh
   
   # With this:
   ./build_persistent.sh
   ```

2. **For CI/CD**: Use `build_cached.sh`
   ```bash
   # Replace this:
   ./build_and_extract.sh --update-deps
   
   # With this:
   ./build_cached.sh --update-deps
   ```

## 🐛 Troubleshooting

### Common Issues

1. **Container won't start**: Check Docker daemon and platform compatibility
   ```bash
   $ docker run --rm --platform=linux/arm64 alpine uname -m
   exec /bin/uname: exec format error # this means its not

   $ # then run
   $ docker run --rm --privileged multiarch/qemu-user-static --reset -p yes
   ```
2. **Build fails after source changes**: Try `--clean` flag
3. **Permission errors**: Ensure Docker has proper permissions
4. **Out of space**: Clean Docker cache with `docker system prune`

### Performance Issues

1. **Still slow builds**: Check if you're using the right strategy for your use case
2. **Cache misses**: Verify file timestamps and Docker layer invalidation
3. **Memory issues**: Increase Docker memory allocation

## 📋 Requirements

- Docker with buildx support
- Platform: linux/arm64 support
- rsync (for Kria deployment)
- Sufficient disk space for build artifacts

## 🎯 Best Practices

1. **Use persistent containers** for active development
2. **Layer your Dockerfile** based on change frequency
3. **Separate dependencies** from source code in Docker layers
4. **Use .dockerignore** to exclude unnecessary files
5. **Monitor build times** and cache hit rates
6. **Clean up regularly** to avoid disk space issues
