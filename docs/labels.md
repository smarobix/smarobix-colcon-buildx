# Image labels

colcon-buildx reads a few labels from a Docker image, together with the image's architecture, to decide how to build with it. This page is the contract between colcon-buildx and the images it uses. The images repository sets the labels on what it publishes, and an image you build yourself can set them too. All are optional. An image without them is a board image: it runs as it is if it has your computer's architecture, and otherwise becomes the sysroot of a cross image. Its ROS 2 distro is taken from its name.

colcon-buildx never runs an image of another architecture. See [What colcon buildx does with an image](https://github.com/smarobix/smarobix-colcon-buildx#what-colcon-buildx-does-with-an-image).

| Label | Values | Effect |
|---|---|---|
| `org.smarobix.buildx.kind` | absent, `ros-apt`, `yocto-native`, `oe-sdk` or `sysroot-cross` | Absent and `ros-apt`: a board image. It runs as it is on a computer of its architecture, sourcing `/opt/ros/<distro>/setup.sh`, and otherwise becomes the sysroot of a cross image. `yocto-native`: a Yocto image that runs as the target; it is refused on a computer of another architecture. `oe-sdk`: an SDK image that runs on the computer and cross-compiles. colcon-buildx prepares it once, sources the `env-setup` scripts and builds with its toolchain wrapper and Ninja. `sysroot-cross`: a cross image colcon-buildx built; it sources `env-setup` and builds with the `toolchain` label's file. |
| `org.smarobix.buildx.env-setup` | absolute paths inside the image, separated by colons | The SDK environment scripts to source, in that order. Required when `kind` is `oe-sdk`. |
| `org.smarobix.buildx.toolchain` | an absolute path inside the image | The CMake toolchain file of a `sysroot-cross` image. |
| `org.smarobix.buildx.target-platform` | a Docker platform such as `linux/arm64` | What the build's output runs on. Printed for SDK images. |
| `org.smarobix.buildx.ros-distro` | a ROS 2 distro such as `jazzy` | Which `/opt/ros/<distro>` to source. It takes precedence over a distro in the image name. |
| `io.oeros.sdk`, `io.oeros.ros-distro` | set by the OEROS images | `io.oeros.sdk=cross` is taken as `oe-sdk`. Any `io.oeros.*` label also marks an image that runs as the target as one to prepare. The distro names the image to suggest when one is refused. |

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

A board image works with colcon-buildx if it has ROS 2 in `/opt/ros/<distro>` and a distro colcon-buildx can find: the `ros-distro` label, or `humble`, `jazzy`, `kilted`, `lyrical` or `rolling` in the name. The build runs with your user and group ID and `HOME=/tmp`, so the image must not need a particular user. To become a cross image's sysroot it must be Ubuntu-based, as the cross compiler comes from the same Ubuntu release. For `--install-deps` it also needs `rosdep` and the apt sources for your dependencies; for `--sync-from-device`, dpkg and apt with the same sources as the board. Both need an image of your computer's architecture.

An SDK image needs the `oe-sdk` kind or `io.oeros.sdk=cross`, and an SDK made by `populate_sdk`, with ROS 2 in the target sysroot. Everything else is optional: a shell, `ros-sdk-env` and the build tools' quirks are taken care of when colcon-buildx prepares the image. [OEROS images](oeros.md) has the details.
