# Image labels

colcon-buildx reads four labels from a Docker image to decide how to build with it. This page is the contract between colcon-buildx and the images it uses. The images repository sets the labels on what it publishes, and an image you build yourself can set them too. All four are optional: an image without them runs as the target, and its ROS 2 distro is taken from its name.

| Label | Values | Effect |
|---|---|---|
| `org.smarobix.buildx.kind` | absent, `ros-apt`, `yocto-native` or `oe-sdk` | Absent, `ros-apt` and `yocto-native`: the image runs *as* the target, with `--platform` set to `docker_platform`, natively or under QEMU, and the build sources `/opt/ros/<distro>/setup.bash`. `oe-sdk`: a cross SDK image that runs on the host. colcon-buildx starts it without `--platform`, sources the `env-setup` scripts, stops with an error if `OE_CMAKE_TOOLCHAIN_FILE` is still unset, and builds with its toolchain wrapper and Ninja. |
| `org.smarobix.buildx.env-setup` | absolute paths inside the image, separated by colons | The SDK environment scripts to source, in that order. Required when `kind` is `oe-sdk`. |
| `org.smarobix.buildx.target-platform` | a Docker platform such as `linux/arm64` | What the build's output runs on. Printed for SDK images. |
| `org.smarobix.buildx.ros-distro` | a ROS 2 distro such as `jazzy` | Which `/opt/ros/<distro>` to source. It takes precedence over a distro in the image name. |

To see an image's labels, and to set them in a Dockerfile:

```bash
docker image inspect --format '{{json .Config.Labels}}' ghcr.io/smarobix/smarobix-buildx-images:k26-oesdk-jazzy
```

```dockerfile
LABEL org.smarobix.buildx.kind="oe-sdk" \
      org.smarobix.buildx.env-setup="/opt/ros-sdk/environment-setup-cortexa72-cortexa53-oe-linux" \
      org.smarobix.buildx.target-platform="linux/arm64" \
      org.smarobix.buildx.ros-distro="jazzy"
```

## Bringing your own image

An image that runs as the target works with colcon-buildx if it has ROS 2 in `/opt/ros/<distro>`, colcon and bash, a distro colcon-buildx can find (the `ros-distro` label, or `humble`, `jazzy`, `kilted` or `rolling` in the name), and nothing that needs a particular user: the build runs with your user and group ID and `HOME=/tmp`. For `--install-deps` it also needs `rosdep` and the apt sources for your dependencies; for `--sync-from-device`, dpkg and apt with the same sources as the board.

A cross SDK image needs the `oe-sdk` kind, an `env-setup` label, and an SDK built with `ros-sdk-env` (`nativesdk-ros-sdk-env` in `TOOLCHAIN_HOST_TASK`), which is what sets `OE_CMAKE_TOOLCHAIN_FILE`, `PYTHON_SOABI` and `AMENT_PREFIX_PATH`. An SDK without it still works if you name its toolchain file with `--toolchain`.
