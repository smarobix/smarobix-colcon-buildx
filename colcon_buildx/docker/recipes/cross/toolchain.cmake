# SPDX-FileCopyrightText: 2026 SMAROBIX GmbH
# SPDX-License-Identifier: Apache-2.0
#
# Cross-compile a ROS 2 workspace against a target image's filesystem (BUILDX_SYSROOT) with the
# host release's cross gcc, in a cross image (Dockerfile next to this file). Values come from the
# image (facts.sh, env.sh); colcon-buildx sets BUILDX_INSTALL_BASE to the workspace's install
# directory so packages find each other.
set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR $ENV{BUILDX_PROCESSOR})
set(CMAKE_LIBRARY_ARCHITECTURE $ENV{BUILDX_TRIPLET})
set(CMAKE_SYSROOT $ENV{BUILDX_SYSROOT})
set(CMAKE_C_COMPILER /usr/bin/$ENV{BUILDX_TRIPLET}-gcc)
set(CMAKE_CXX_COMPILER /usr/bin/$ENV{BUILDX_TRIPLET}-g++)

# Search the target only (programs: the host). The workspace's install prefix is a root of its
# own: paths already under a root are not re-rooted, so packages built earlier are found.
set(CMAKE_FIND_ROOT_PATH ${CMAKE_SYSROOT})
if(DEFINED ENV{BUILDX_INSTALL_BASE})
  list(APPEND CMAKE_FIND_ROOT_PATH $ENV{BUILDX_INSTALL_BASE})
endif()
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)

# ROS prefixes from the sourced environment (/opt/ros/<distro>, re-rooted into the sysroot).
if(DEFINED ENV{AMENT_PREFIX_PATH})
  string(REPLACE ":" ";" _buildx_ament "$ENV{AMENT_PREFIX_PATH}")
  list(APPEND CMAKE_PREFIX_PATH ${_buildx_ament})
endif()

# Indirect shared-library dependencies outside the linker's default directories: the ROS lib dir and
# whatever the target's setup put on LD_LIBRARY_PATH (env.sh keeps it as BUILDX_TARGET_LIBRARY_PATH).
set(_buildx_dirs "/opt/ros/$ENV{ROS_DISTRO}/lib")
if(DEFINED ENV{BUILDX_TARGET_LIBRARY_PATH})
  string(REPLACE ":" ";" _buildx_ld "$ENV{BUILDX_TARGET_LIBRARY_PATH}")
  list(APPEND _buildx_dirs ${_buildx_ld})
endif()
set(_buildx_rl "")
foreach(_buildx_d IN LISTS _buildx_dirs)
  if(_buildx_d AND EXISTS "${CMAKE_SYSROOT}${_buildx_d}")
    string(APPEND _buildx_rl " -Wl,-rpath-link,${CMAKE_SYSROOT}${_buildx_d}")
  endif()
endforeach()
string(APPEND CMAKE_EXE_LINKER_FLAGS_INIT " ${_buildx_rl}")
string(APPEND CMAKE_SHARED_LINKER_FLAGS_INIT " ${_buildx_rl}")
string(APPEND CMAKE_MODULE_LINKER_FLAGS_INIT " ${_buildx_rl}")

# The host interpreter runs the generators; env.sh makes it report the target's sysconfig.
set(Python3_EXECUTABLE /usr/bin/python3 CACHE FILEPATH "host Python, target sysconfig")
