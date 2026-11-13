# SPDX-FileCopyrightText: 2025-2026 SMAROBIX GmbH
# SPDX-License-Identifier: Apache-2.0

"""Colcon extension for cross-compilation to embedded ARM boards."""

__version__ = '0.2.1'

# ROS 2 distros this extension recognises, in the order it prefers them when
# several would match. Iron reached end of life in November 2024; Lyrical is
# the May 2026 LTS release, and what the OEROS images ship.
ROS_DISTROS = ('jazzy', 'humble', 'kilted', 'lyrical', 'rolling')

# Used when nothing says which distro an image or a board carries.
DEFAULT_ROS_DISTRO = 'jazzy'
