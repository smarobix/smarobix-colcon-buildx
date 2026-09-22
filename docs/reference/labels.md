# Image labels

colcon-buildx reads four labels from a Docker image to decide how to build with it. This page is the contract between colcon-buildx and the images it uses. The images repository sets these labels on the images it publishes, and any image you build yourself can set them too.

All four are optional. An image without any of them is treated as an image that runs as the target, and its ROS 2 distro is guessed from its name.

| Label | Values | Used for |
|---|---|---|
| `org.smarobix.buildx.kind` | absent or `ros-apt`, `oe-sdk`, `yocto-native` | How the image is run. See below. |
| `org.smarobix.buildx.env-setup` | an absolute path in the image, or several separated by colons | The SDK environment scripts to source, in order. Required when `kind` is `oe-sdk`. |
| `org.smarobix.buildx.target-platform` | a Docker platform, for example `linux/arm64` | The platform the build's output runs on. colcon-buildx prints it for SDK images. |
| `org.smarobix.buildx.ros-distro` | a ROS 2 distro, for example `jazzy` | For an image that runs as the target, which `/opt/ros/<distro>/setup.bash` to source. It takes precedence over the distro in the image name. |

## `org.smarobix.buildx.kind`

**Absent, or `ros-apt`.** This is the default. The image runs *as* the target: colcon-buildx starts it with `--platform` set to `docker_platform`, natively or under QEMU, sources `/opt/ros/<distro>/setup.bash` and builds natively inside it. The published Ubuntu, PYNQ and Debian images are run this way.

**`oe-sdk`.** A cross SDK image that runs on the host. colcon-buildx:

- starts it without `--platform`;
- sources the scripts in `org.smarobix.buildx.env-setup`;
- stops with an error if `OE_CMAKE_TOOLCHAIN_FILE` is unset afterwards;
- builds with its toolchain wrapper and Ninja, as described in [Yocto targets](../yocto-targets.md#what-colcon-buildx-adds).

The published SDK images, such as `k26-oesdk-jazzy`, set this kind.

**`yocto-native`.** Set by the Yocto dev container that bitbake builds, such as `k26-yocto-jazzy`. colcon-buildx currently handles it like the default: the image runs as the target and builds natively.

Any other value is also handled like the default.

## Example

The images repository's SDK images carry:

| Label | `k26-oesdk-jazzy` |
|---|---|
| `org.smarobix.buildx.kind` | `oe-sdk` |
| `org.smarobix.buildx.env-setup` | `/opt/ros-sdk/environment-setup-cortexa72-cortexa53-oe-linux` |
| `org.smarobix.buildx.target-platform` | `linux/arm64` |
| `org.smarobix.buildx.ros-distro` | `jazzy` |

To see an image's labels:

```bash
docker image inspect --format '{{json .Config.Labels}}' ghcr.io/smarobix/smarobix-buildx-images:k26-oesdk-jazzy
```

To set them in a Dockerfile:

```dockerfile
LABEL org.smarobix.buildx.kind="oe-sdk" \
      org.smarobix.buildx.env-setup="/opt/ros-sdk/environment-setup-cortexa72-cortexa53-oe-linux" \
      org.smarobix.buildx.target-platform="linux/arm64" \
      org.smarobix.buildx.ros-distro="jazzy"
```

The images repository builds its SDK images in [`dockerfiles/oesdk`](https://github.com/smarobix/smarobix-buildx-images/tree/main/dockerfiles/oesdk).

## Bringing your own image

An image that runs as the target works with colcon-buildx if it has:

- ROS 2 in `/opt/ros/<distro>`, and colcon;
- bash, because the build runs `bash -c`;
- a distro colcon-buildx can find: the `org.smarobix.buildx.ros-distro` label, or `humble`, `jazzy`, `kilted` or `rolling` in the image name;
- nothing that needs a particular user. The build runs with your user and group ID and `HOME=/tmp`.

For `--install-deps` it also needs `rosdep` and the apt sources for your dependencies. For `--sync-from-device` it needs dpkg and apt, with the same apt sources as the board.

A cross SDK image needs the `oe-sdk` kind, an `env-setup` label, and an SDK built with `ros-sdk-env`; see [Yocto targets](../yocto-targets.md#what-the-sdk-has-to-contain).
