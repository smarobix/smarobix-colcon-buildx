# SPDX-FileCopyrightText: 2026 SMAROBIX GmbH
# SPDX-License-Identifier: Apache-2.0
#
# A cross image: the host's architecture, the target image's filesystem as /sysroot, and the same
# Ubuntu release's cross gcc. Copying from a foreign-platform stage executes nothing, so nothing
# runs under emulation. Compiler, glibc and libstdc++ match the board by construction. The ROS
# generators are pure Python and run on the host's Python, the same version as the target's; the
# target's sysconfig data makes that interpreter report the target's ABI. colcon-buildx builds this
# once per target image (colcon-buildx:cross-<id>); verified on arm64 and armhf targets (E15).
ARG TARGET_IMAGE
ARG TARGET_PLATFORM=linux/arm64
ARG HOST_IMAGE=ubuntu:24.04
FROM --platform=${TARGET_PLATFORM} ${TARGET_IMAGE} AS target

FROM ${HOST_IMAGE}
ARG TARGET_IMAGE
ARG TARGET_PLATFORM
ARG TRIPLET=aarch64-linux-gnu
ARG PROCESSOR=aarch64
ENV DEBIAN_FRONTEND=noninteractive

# Cross compiler and build tools for the host; colcon from the ROS repository, the generators'
# Python dependencies from the release itself, so the same versions as on the target.
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
 && curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.asc \
      | gpg --dearmor -o /usr/share/keyrings/ros-archive-keyring.gpg \
 && . /etc/os-release \
 && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu ${VERSION_CODENAME} main" \
      > /etc/apt/sources.list.d/ros2.list \
 && apt-get update && apt-get install -y --no-install-recommends \
      gcc-${TRIPLET} g++-${TRIPLET} cmake make ninja-build pkg-config file \
      python3 python3-numpy python3-empy python3-lark python3-yaml python3-setuptools \
      python3-colcon-common-extensions \
 && rm -rf /var/lib/apt/lists/*

COPY --from=target / /sysroot/

# The target's multiarch directories, /opt/ros and plain /usr/lib are linked into the host at their
# real paths, entry by entry, keeping the host's own entries. Absolute symlinks inside the sysroot
# and absolute paths in installed CMake configs (XRT names /usr/lib/libxrt_coreutil.so.2.18.0) then
# resolve without rewriting anything. The cross binutils keep their linker scripts and LTO plugin in
# /usr/lib/<triplet>, which is why the link is per entry.
RUN for d in /usr/lib/${TRIPLET} /usr/include/${TRIPLET} /opt/ros /usr/lib; do \
      if [ -d "$d" ] && [ ! -L "$d" ]; then \
        for e in "/sysroot$d"/* "/sysroot$d"/.[!.]*; do \
          [ -e "$e" ] || [ -L "$e" ] || continue; \
          [ -e "$d/${e##*/}" ] || ln -s "$e" "$d/"; \
        done; \
      else \
        ln -s "/sysroot$d" "$d"; \
      fi; \
    done \
 && distro=$(ls /sysroot/opt/ros | head -n 1) \
 && pyver=$(cd /sysroot/usr/lib && ls -d python3.* | head -n 1) \
 && host_pyver=$(python3 -c 'import sys; print("python%d.%d" % sys.version_info[:2])') \
 && if [ "$pyver" != "$host_pyver" ]; then \
      echo "target $pyver, host $host_pyver: the host release must match the target's" >&2; exit 1; \
    fi \
 && cp "/sysroot/usr/lib/${pyver}/_sysconfigdata__${TRIPLET}.py" "/usr/lib/${pyver}/" \
 && for f in /sysroot/usr/bin/${TRIPLET}-python*-config; do ln -s "$f" /usr/bin/; done \
 && mkdir -p /opt/buildx \
 && printf 'export ROS_DISTRO=%s BUILDX_SYSROOT=/sysroot BUILDX_TRIPLET=%s BUILDX_PROCESSOR=%s\n' \
      "$distro" "${TRIPLET}" "${PROCESSOR}" > /opt/buildx/facts.sh
# FindPython does not ask the interpreter when cross-compiling; it runs <triplet>-pythonX.Y-config,
# which Ubuntu ships as a shell script that resolves its own location, so it reports sysroot paths.

COPY toolchain.cmake env.sh /opt/buildx/
LABEL org.smarobix.buildx.kind="sysroot-cross" \
      org.smarobix.buildx.env-setup="/opt/buildx/env.sh" \
      org.smarobix.buildx.toolchain="/opt/buildx/toolchain.cmake" \
      org.smarobix.buildx.target-platform="${TARGET_PLATFORM}" \
      org.smarobix.buildx.source-image="${TARGET_IMAGE}"
