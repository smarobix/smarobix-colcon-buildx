# An SDK installed on the computer (open question)

> **Not part of the supported workflow.** This page keeps a route that colcon buildx has, but that
> SMAROBIX does not use or support today: the only workflow we use is the Docker one, with an OEROS
> SDK image. It is on this branch to ask the OEROS maintainers whether it makes sense for production
> teams, and how they would want it to look.

## The idea

A team that ships may keep its SDK as an installer, with its SBOM, rather than as a Docker image. On
a Linux computer with that SDK installed, colcon buildx builds against it directly, with the same
toolchain wrapper as the Docker route:

```bash
sh oecore-*.sh -y -d /opt/oeros-sdk
colcon buildx --method sdk --sdk-env /opt/oeros-sdk/environment-setup-armv8a-oeros-linux
```

`--emit-mixin` also writes the settings as a colcon mixin, so a plain `colcon build --mixin buildx`
gives the same build without colcon buildx.

## What it needs

- An SDK built with `ros-sdk-env` (`nativesdk-ros-sdk-env` in `TOOLCHAIN_HOST_TASK`), which sets the
  toolchain file, `PYTHON_SOABI` and `AMENT_PREFIX_PATH`. Without it, name the SDK's toolchain file
  with `--toolchain`. Unlike an SDK image, an installed SDK is not prepared: what it lacks, such as
  `ament_cmake_ros_core` for Kilted and later, stays missing.
- A Linux computer whose architecture matches the SDK's `SDKMACHINE`.

## Questions for OEROS

1. Do production teams use the SDK installer this way, or do they build in the dev container or CI?
2. Is a colcon mixin the right hand-off, or would a toolchain file shipped in the SDK be better?
3. Should the installer and the SDK image be the same artefact, so that one test covers both?

## Messages you may see

**`OE_CMAKE_TOOLCHAIN_FILE unset after sourcing the SDK environment`.** The SDK was built without
`ros-sdk-env`. Rebuild it with `nativesdk-ros-sdk-env` in `TOOLCHAIN_HOST_TASK`, or name its toolchain
file with `--toolchain`.

**`Could not find a package configuration file provided by "ament_cmake_ros_core"`.** The SDK lacks
`ament_cmake_ros_core` (meta-ros Kilted and later). Add `ament-cmake-ros-core` to the SDK.

**`--method sdk requires a Linux host`.** An OE SDK is a Linux program.

**`SDK environment script not found`** or **`Failed to source the SDK environment`.** `--sdk-env` must
point at the SDK's `environment-setup-*` script, and the SDK's host tools must match the computer.
