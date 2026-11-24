# SPDX-FileCopyrightText: 2026 SMAROBIX GmbH
# SPDX-License-Identifier: Apache-2.0
#
# Sourced in a cross image before every build. POSIX sh.
. /opt/buildx/facts.sh
. "/opt/ros/${ROS_DISTRO}/setup.sh"
# The target's library path is for the target's loader: the cross linker gets it as -rpath-link
# (toolchain.cmake), host programs do not get it at all. A source-built ROS needs this for the
# vendored libraries under /opt/ros/<distro>/opt/*/lib, which its libraries reach without RUNPATH.
export BUILDX_TARGET_LIBRARY_PATH="${LD_LIBRARY_PATH:-}"
unset LD_LIBRARY_PATH
# The host Python reports the target's sysconfig: extension suffix, include and library dirs.
export _PYTHON_SYSCONFIGDATA_NAME="_sysconfigdata__${BUILDX_TRIPLET}"
export _PYTHON_HOST_PLATFORM="linux-${BUILDX_PROCESSOR}"
