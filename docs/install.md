# Install

## The package

```bash
pip install "git+https://github.com/smarobix/smarobix-colcon-buildx.git"
colcon buildx --help
```

This pulls in `colcon-core`, `colcon-cmake` and PyYAML. It needs Python 3.9 or newer.

Recent Debian and Ubuntu releases refuse `pip install` into the system Python (PEP 668). On those, install into a virtual environment and run `colcon` from it:

```bash
python3 -m venv ~/.venvs/buildx
~/.venvs/buildx/bin/pip install "git+https://github.com/smarobix/smarobix-colcon-buildx.git"
~/.venvs/buildx/bin/colcon buildx --help
```

## Prerequisites

What else you need depends on the [backend](backends.md) and on the options you use.

| For | You need |
|---|---|
| `--method docker` (the default) | Docker, and a target image. The images repository publishes one for each supported board. |
| `--method sdk` | A Linux host with a Yocto/OE SDK installed, built with `ros-sdk-env`. See [Yocto targets](yocto-targets.md). |
| `--method sysroot` | A Linux host with `sshfs` and FUSE `user_allow_other`, a CMake toolchain file, and an aarch64 board. See [Backends](backends.md#sysroot-experimental). |
| `--deploy` | `rsync` on the host and on the board, and SSH access to the board. |
| `--sync-from-device`, `--install-deps-on-device` | SSH access to the board. The board must use apt. `--install-deps-on-device` also needs `rosdep` and `sudo` on the board. |

## Docker and QEMU

An image that runs *as* the target architecture needs a host that can run that architecture's binaries.

- **Apple Silicon Macs and arm64 Linux hosts** run arm64 images natively. They need no QEMU for them.
- **x86_64 hosts** need QEMU registered with the kernel's binfmt handlers. Docker Desktop already includes it. On Linux with Docker Engine, register it once:

  ```bash
  docker run --rm --privileged multiarch/qemu-user-static --reset -p yes
  ```

- **armhf images** (`linux/arm/v7`) need QEMU on any host whose CPU can't run 32-bit ARM code. The same command registers it.

Check that it works:

```bash
docker run --rm --platform linux/arm64 alpine uname -m   # aarch64
docker run --rm --platform linux/arm/v7 alpine uname -m  # armv7l
```

Emulated builds work, but they are slow: every compiler process runs under QEMU.

### SDK images on x86_64

colcon-buildx starts cross SDK images, such as `k26-oesdk-jazzy`, without `--platform`. The published SDK tags have only an arm64 entry, so on an x86_64 host pull them for arm64 before the first build:

```bash
docker pull --platform linux/arm64 ghcr.io/smarobix/smarobix-buildx-images:k26-oesdk-jazzy
```

Without this, the build fails with "no matching manifest". The images repository's guide to [building on x86_64](https://smarobix.github.io/smarobix-buildx-images/how-to/build-on-x86_64/) covers this in more detail.

## Development install

To work on colcon-buildx itself, install it editable from a clone:

```bash
git clone https://github.com/smarobix/smarobix-colcon-buildx.git
cd smarobix-colcon-buildx
pip install -e ".[test]"
colcon buildx --help
```

[Development](development.md) describes the tests and the code layout.
