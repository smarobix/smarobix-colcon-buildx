# SPDX-FileCopyrightText: 2026 SMAROBIX GmbH
# SPDX-License-Identifier: Apache-2.0

"""What colcon-buildx does with an image, decided without Docker."""

import pytest

from colcon_buildx.docker import images
from colcon_buildx.toolchain import wrapper_text

OEROS_CROSS = {
    'io.oeros.sdk': 'cross', 'io.oeros.sdk-host-arch': 'x86_64', 'io.oeros.ros-distro': 'lyrical'}
OEROS_TARGET = {
    'io.oeros.sdk': 'target', 'io.oeros.sdk-host-arch': 'aarch64', 'io.oeros.ros-distro': 'lyrical'}
OUR_SDK = {images.LABEL_KIND: images.KIND_OE_SDK, images.LABEL_ENV_SETUP: '/opt/ros-sdk/env'}


@pytest.mark.parametrize('labels, arch, host, expected', [
    # SDK images run on their host and are prepared
    (OEROS_CROSS, 'amd64', 'amd64', (images.PREPARE, images.KIND_OE_SDK)),
    (OUR_SDK, 'arm64', 'arm64', (images.PREPARE, images.KIND_OE_SDK)),
    # a dev container of the host's architecture runs as it is, prepared if OEROS
    (OEROS_TARGET, 'arm64', 'arm64', (images.PREPARE, images.KIND_YOCTO_NATIVE)),
    ({}, 'arm64', 'arm64', (images.RUN_AS_IS, images.KIND_ROS_APT)),
    # a board image of another architecture becomes a cross image's sysroot
    ({}, 'arm64', 'amd64', (images.CROSS, images.KIND_SYSROOT_CROSS)),
    ({}, 'arm', 'amd64', (images.CROSS, images.KIND_SYSROOT_CROSS)),
    ({}, 'arm', 'arm64', (images.CROSS, images.KIND_SYSROOT_CROSS)),
    # a cross image colcon-buildx built runs as it is
    ({images.LABEL_KIND: images.KIND_SYSROOT_CROSS}, 'amd64', 'amd64',
     (images.RUN_AS_IS, images.KIND_SYSROOT_CROSS)),
])
def test_classify(labels, arch, host, expected):
    assert images.classify(labels, arch, host) == expected


@pytest.mark.parametrize('labels, arch, host, hint', [
    # an SDK for another host would run under emulation
    (OEROS_CROSS, 'amd64', 'arm64', 'oeros-sdk-target:lyrical-arm64'),
    # an OEROS image of another architecture: use the cross SDK
    (OEROS_TARGET, 'arm64', 'amd64', 'oeros-sdk-cross:lyrical-arm64'),
    ({images.LABEL_KIND: images.KIND_YOCTO_NATIVE}, 'arm64', 'amd64', 'kind oe-sdk'),
])
def test_classify_refuses_emulation_and_says_what_to_use(labels, arch, host, hint):
    with pytest.raises(images.ImageError, match='emulation') as error:
        images.classify(labels, arch, host)
    assert hint in str(error.value)


@pytest.mark.parametrize('inspected, platform', [
    ({'Architecture': 'arm64', 'Variant': 'v8'}, 'linux/arm64'),
    ({'Architecture': 'arm', 'Variant': 'v7'}, 'linux/arm/v7'),
    ({'Architecture': 'arm'}, 'linux/arm/v7'),
    ({'Architecture': 'amd64'}, 'linux/amd64'),
])
def test_image_platform(inspected, platform):
    assert images.image_platform(inspected) == platform


def test_cross_build_args_follow_the_targets_release():
    os_release = images.parse_os_release('ID=ubuntu\nVERSION_ID="22.04"\nPRETTY_NAME="Ubuntu 22.04.5 LTS"\n')
    assert images.cross_build_args(os_release, 'linux/arm/v7') == {
        'TARGET_PLATFORM': 'linux/arm/v7', 'HOST_IMAGE': 'ubuntu:22.04',
        'TRIPLET': 'arm-linux-gnueabihf', 'PROCESSOR': 'armv7l'}


def test_cross_build_args_refuse_other_distributions():
    with pytest.raises(images.ImageError, match='Ubuntu board images only'):
        images.cross_build_args({'ID': 'debian', 'PRETTY_NAME': 'Raspbian'}, 'linux/arm/v7')


def test_facts_fill_the_env_script():
    facts = images.parse_facts(
        'ENV_SETUP=/usr/local/sdk/environment-setup-armv8a-oeros-linux\n'
        'SYSROOT=/usr/local/sdk/sysroots/armv8a-oeros-linux\nROS_DISTRO=lyrical\n'
        'PYTHON=python3.14\nPYTHON_SOABI=cpython-314-aarch64-linux-gnu\n')
    text = images.render_env_sh(facts, 'ghcr.io/x/sdk:1')
    assert '@' not in text.replace('# SPDX', '')
    assert 'BUILDX_ENV_SETUP="/usr/local/sdk/environment-setup-armv8a-oeros-linux"' in text
    assert 'export PYTHON_SOABI="cpython-314-aarch64-linux-gnu"' in text
    assert '/usr/lib/python3.14/site-packages' in text


def test_prepared_image_adds_ament_cmake_ros_core_only_when_missing():
    base = {'ENV_SETUP': '/sdk/env', 'TARGET_ARCH': 'aarch64', 'ROS_DISTRO': 'lyrical'}
    without = images.render_prepared_dockerfile('probe', base, images.KIND_OE_SDK, 'img', '/usr/bin')
    assert 'ament_cmake_ros' not in without
    assert 'org.smarobix.buildx.target-platform="linux/arm64"' in without
    assert 'ENV PATH=/usr/bin:/opt/buildx/bin' in without

    needed = dict(base, AMENT_CMAKE_ROS_CORE='0.15.8')
    text = images.render_prepared_dockerfile('probe', needed, images.KIND_OE_SDK, 'img', '/usr/bin')
    assert ('ADD https://github.com/ros2/ament_cmake_ros/archive/refs/tags/0.15.8.tar.gz'
            in text)


def test_wrapper_keeps_programs_on_the_host_and_python_on_the_target():
    text = wrapper_text('/workspace/cross_install')
    assert 'set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)' in text
    assert 'Python3_INCLUDE_DIR' in text
    assert 'PYTHON_MODULE_EXTENSION ".$ENV{PYTHON_SOABI}.so"' in text
