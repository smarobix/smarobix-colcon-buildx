# SPDX-FileCopyrightText: 2026 SMAROBIX GmbH
# SPDX-License-Identifier: Apache-2.0

"""
The images colcon-buildx builds from the image it is given, once per image.

colcon buildx never runs an image of another architecture. The image it is
given is one of three things, told apart by its labels and its architecture:

- **An SDK image**, holding an OE/Yocto SDK, such as the OEROS
  ``oeros-sdk-cross`` images. It runs on the host and cross-compiles.
  colcon-buildx *prepares* it: a thin layer on top with a static shell, an
  environment script, and the fixes the SDK needs. The SDK image itself only
  has to carry the toolchain and the sysroot.
- **An image of the host's architecture** that runs as the target: a dev
  container such as ``oeros-sdk-target`` on an arm64 host. It runs as it is,
  and is prepared as well when it is an OEROS image.
- **An image of another architecture**, an Ubuntu or Debian image made for a
  board. It becomes the sysroot of a *cross image*, built for the host from
  the same release with its cross gcc. Copying the target's filesystem runs
  nothing, so no emulation is involved.

Derived images are tagged ``colcon-buildx:prepared-<id>-<recipes>`` and
``colcon-buildx:cross-<id>-<recipes>``, after the given image's ID and a hash of
the recipes here. A new version of the image, or of colcon-buildx's recipes,
therefore gets its own, and ``docker image prune`` can remove old ones.
"""

import hashlib
import io
import platform as host_platform_module
import posixpath
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

from colcon_core.logging import colcon_logger

logger = colcon_logger.getChild(__name__)

RECIPES = Path(__file__).parent / 'recipes'

# Static, small, and on Docker Hub for amd64, arm64 and armv7. Its wget cannot
# check certificates, so downloads go through the Dockerfile's ADD instead.
BUSYBOX_IMAGE = 'busybox:1.37.0-musl'
LOCAL_REPO = 'colcon-buildx'

# Our own labels; docs/labels.md is the contract.
LABEL_KIND = 'org.smarobix.buildx.kind'
LABEL_ENV_SETUP = 'org.smarobix.buildx.env-setup'
LABEL_TOOLCHAIN = 'org.smarobix.buildx.toolchain'
LABEL_TARGET_PLATFORM = 'org.smarobix.buildx.target-platform'
LABEL_ROS_DISTRO = 'org.smarobix.buildx.ros-distro'
LABEL_SOURCE_IMAGE = 'org.smarobix.buildx.source-image'

KIND_ROS_APT = 'ros-apt'
KIND_YOCTO_NATIVE = 'yocto-native'
KIND_OE_SDK = 'oe-sdk'
KIND_SYSROOT_CROSS = 'sysroot-cross'

# Labels on the OEROS images (github.com/oerosproject/meta-oeros).
OEROS_PREFIX = 'io.oeros.'
OEROS_SDK = 'io.oeros.sdk'
OEROS_DISTRO = 'io.oeros.ros-distro'

_ARCHES = {
    'x86_64': 'amd64', 'amd64': 'amd64',
    'aarch64': 'arm64', 'arm64': 'arm64',
    'armv7l': 'arm', 'armhf': 'arm', 'arm': 'arm',
}

# What a cross image needs per target: GNU triplet and CMake processor name.
CROSS_TARGETS = {
    'linux/arm64': ('aarch64-linux-gnu', 'aarch64'),
    'linux/arm/v7': ('arm-linux-gnueabihf', 'armv7l'),
}

# Action decided by classify().
RUN_AS_IS = 'run'
PREPARE = 'prepare'
CROSS = 'cross'


class ImageError(Exception):
    """The image cannot be used, and the message says what to use instead."""


def normalize_arch(arch):
    """Return Docker's name for *arch*: amd64, arm64 or arm."""
    arch = (arch or '').lower()
    return _ARCHES.get(arch, arch)


def host_arch():
    """Return the architecture the Docker daemon runs containers as natively."""
    try:
        out = subprocess.run(
            ['docker', 'info', '--format', '{{.Architecture}}'],
            capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        out = ''
    return normalize_arch(out or host_platform_module.machine())


def image_platform(inspected):
    """Return an inspected image's platform, such as linux/arm64 or linux/arm/v7."""
    arch = normalize_arch(inspected.get('Architecture'))
    if arch == 'arm':
        return f"linux/arm/{inspected.get('Variant') or 'v7'}"
    return f'linux/{arch}'


def labels_of(inspected):
    """Return an inspected image's labels."""
    return ((inspected or {}).get('Config') or {}).get('Labels') or {}


def env_of(inspected):
    """Return an inspected image's environment as a dict."""
    env = ((inspected or {}).get('Config') or {}).get('Env') or []
    return dict(e.split('=', 1) for e in env if '=' in e)


def short_id(inspected):
    """Return the first twelve hex digits of an inspected image's ID."""
    return (inspected.get('Id') or '').split(':')[-1][:12]


def recipes_hash():
    """Return eight hex digits that change whenever a recipe here changes."""
    digest = hashlib.sha256()
    for path in sorted(RECIPES.rglob('*')):
        if path.is_file():
            digest.update(path.relative_to(RECIPES).as_posix().encode() + b'\0')
            digest.update(path.read_bytes())
    return digest.hexdigest()[:8]


def is_oeros(labels):
    """Return True for an image published by the OEROS project."""
    return any(key.startswith(OEROS_PREFIX) for key in labels)


def classify(labels, arch, host):
    """
    Decide what to do with an image, from its labels and architecture.

    Returns:
        (action, kind): RUN_AS_IS, PREPARE or CROSS, and the kind of image
        colcon-buildx will build in.

    Raises:
        ImageError: for an image that would have to run under emulation
    """
    kind = labels.get(LABEL_KIND)
    if kind == KIND_SYSROOT_CROSS:
        return RUN_AS_IS, KIND_SYSROOT_CROSS

    if kind == KIND_OE_SDK or labels.get(OEROS_SDK) == 'cross':
        if arch != host:
            hint = ''
            if is_oeros(labels):
                distro = labels.get(OEROS_DISTRO, '<distro>')
                hint = (f" On an {host} host, use ghcr.io/oerosproject/oeros-sdk-target:"
                        f"{distro}-{host}, which builds for {host} without emulation.")
            raise ImageError(
                f"This SDK runs on {arch} hosts and this one is {host}; colcon buildx does not "
                f"run images under emulation.{hint}")
        return PREPARE, KIND_OE_SDK

    if arch == host:
        if is_oeros(labels):
            return PREPARE, KIND_YOCTO_NATIVE
        return RUN_AS_IS, kind or KIND_ROS_APT

    if is_oeros(labels):
        distro = labels.get(OEROS_DISTRO, '<distro>')
        raise ImageError(
            f"This OEROS image is {arch} and this host is {host}; colcon buildx does not run "
            f"images under emulation. Use the cross SDK image instead, "
            f"ghcr.io/oerosproject/oeros-sdk-cross:{distro}-{arch}, on an x86_64 host.")
    if kind == KIND_YOCTO_NATIVE:
        raise ImageError(
            f"This Yocto image is {arch} and this host is {host}; colcon buildx does not run "
            "images under emulation. Use an SDK image made from the same build (kind oe-sdk).")
    return CROSS, KIND_SYSROOT_CROSS


def inspect(image):
    """Return `docker image inspect` for *image*, or None."""
    import json
    result = subprocess.run(['docker', 'image', 'inspect', image], capture_output=True, text=True)
    if result.returncode != 0:
        return None
    try:
        parsed = json.loads(result.stdout)
    except ValueError:
        return None
    return parsed[0] if parsed else None


def read_image_file(image, path, platform=None):
    """
    Return the text of *path* inside *image*, read without running the image.

    Follows a few symbolic links, as /etc/os-release usually is one.
    """
    create = ['docker', 'create'] + (['--platform', platform] if platform else [])
    result = subprocess.run(create + [image, 'true'], capture_output=True, text=True)
    if result.returncode != 0:
        return None
    container = result.stdout.strip()
    try:
        for _ in range(4):
            copied = subprocess.run(['docker', 'cp', f'{container}:{path}', '-'], capture_output=True)
            if copied.returncode != 0:
                return None
            with tarfile.open(fileobj=io.BytesIO(copied.stdout)) as tar:
                member = tar.next()
                if member is None:
                    return None
                if member.issym():
                    path = posixpath.normpath(
                        posixpath.join(posixpath.dirname(path), member.linkname))
                    continue
                data = tar.extractfile(member)
                return data.read().decode('utf-8', 'replace') if data else None
        return None
    finally:
        subprocess.run(['docker', 'rm', container], capture_output=True)


def parse_os_release(text):
    """Return /etc/os-release as a dict."""
    values = {}
    for line in (text or '').splitlines():
        if '=' in line and not line.startswith('#'):
            key, value = line.split('=', 1)
            values[key.strip()] = value.strip().strip('"\'')
    return values


def cross_build_args(os_release, target_platform):
    """
    Return the --build-arg values for a cross image, or raise ImageError.

    The host side must be the target's own release: its cross gcc, glibc and
    Python then match the board.
    """
    if target_platform not in CROSS_TARGETS:
        raise ImageError(
            f"No cross route for {target_platform}; colcon buildx cross-builds for "
            f"{' and '.join(CROSS_TARGETS)}.")
    os_id = os_release.get('ID')
    if os_id == 'ubuntu' and os_release.get('VERSION_ID'):
        host_image = f"ubuntu:{os_release['VERSION_ID']}"
    elif os_id == 'debian' and os_release.get('VERSION_CODENAME'):
        host_image = f"debian:{os_release['VERSION_CODENAME']}"
    else:
        name = os_release.get('PRETTY_NAME') or 'an unknown distribution'
        raise ImageError(
            f"The image is {name}. colcon buildx builds a cross image from Ubuntu and Debian "
            "board images only, from the same release's cross gcc. For a Yocto/OEROS target, "
            "use its SDK image.")
    triplet, processor = CROSS_TARGETS[target_platform]
    return {
        'TARGET_PLATFORM': target_platform,
        'HOST_IMAGE': host_image,
        'TRIPLET': triplet,
        'PROCESSOR': processor,
    }


def target_platform_of(target_arch):
    """Return the Docker platform for an OE SDK's OECORE_TARGET_ARCH."""
    arch = normalize_arch(target_arch)
    if arch == 'arm':
        return 'linux/arm/v7'
    return f'linux/{arch}' if arch else ''


def parse_facts(text):
    """Return discover.sh's KEY=VALUE output as a dict."""
    return dict(line.split('=', 1) for line in text.splitlines() if '=' in line)


def render_env_sh(facts, source_image):
    """Return the environment script for a prepared image."""
    text = (RECIPES / 'env.sh.in').read_text()
    for key in ('ENV_SETUP', 'SYSROOT', 'ROS_DISTRO', 'PYTHON', 'PYTHON_SOABI'):
        text = text.replace(f'@{key}@', facts.get(key, ''))
    return text.replace('@SOURCE_IMAGE@', source_image)


def render_prepared_dockerfile(base, facts, kind, source_image, path_env):
    """Return the Dockerfile that turns a probe image into a prepared one."""
    lines = [
        f'FROM {base}',
        'COPY fix-links.sh env.sh /opt/buildx/',
        'RUN ["/opt/buildx/bin/busybox", "sh", "/opt/buildx/fix-links.sh"]',
    ]
    version = facts.get('AMENT_CMAKE_ROS_CORE')
    if version and version != 'unknown':
        lines += [
            'ADD https://github.com/ros2/ament_cmake_ros/archive/refs/tags/'
            f'{version}.tar.gz /opt/buildx/src/ament_cmake_ros.tar.gz',
            'COPY ament-cmake-ros-core.sh /opt/buildx/',
            'RUN ["/opt/buildx/bin/busybox", "sh", "/opt/buildx/ament-cmake-ros-core.sh"]',
        ]
    # The image's own commands first, busybox only for what is missing.
    lines.append(f'ENV PATH={path_env}:/opt/buildx/bin')
    lines += ['ENTRYPOINT []', 'CMD ["sh"]']
    target = target_platform_of(facts.get('TARGET_ARCH')) if kind == KIND_OE_SDK else ''
    labels = {
        LABEL_KIND: kind,
        LABEL_ENV_SETUP: '/opt/buildx/env.sh',
        LABEL_ROS_DISTRO: facts.get('ROS_DISTRO', ''),
        LABEL_SOURCE_IMAGE: source_image,
    }
    if target:
        labels[LABEL_TARGET_PLATFORM] = target
    lines.append('LABEL ' + ' \\\n      '.join(f'{k}="{v}"' for k, v in labels.items()))
    return '\n'.join(lines) + '\n'


def _image_exists(tag):
    return subprocess.run(
        ['docker', 'image', 'inspect', tag], capture_output=True).returncode == 0


def _docker_build(tag, context, build_args=None):
    cmd = ['docker', 'build', '-t', tag]
    for key, value in (build_args or {}).items():
        cmd += ['--build-arg', f'{key}={value}']
    if subprocess.run(cmd + [str(context)]).returncode != 0:
        raise ImageError(f'Building {tag} failed; the output above says why.')


def prepare(image, inspected, kind):
    """
    Return the tag of the prepared image for *image*, building it the first time.

    A probe copy with busybox added says what the image has (discover.sh);
    the prepared image then adds what it lacks.
    """
    ident = f'{short_id(inspected)}-{recipes_hash()}'
    tag = f'{LOCAL_REPO}:prepared-{ident}'
    if _image_exists(tag):
        return tag

    print(f"🔧 Preparing {image} for colcon buildx, once per image version ({tag})")
    probe = f'{LOCAL_REPO}:probe-{ident}'
    env_setup = labels_of(inspected).get(LABEL_ENV_SETUP, '')
    with tempfile.TemporaryDirectory(prefix='colcon-buildx-') as tmp:
        context = Path(tmp)
        (context / 'Dockerfile').write_text(
            f'FROM {image}\n'
            f'COPY --from={BUSYBOX_IMAGE} /bin/busybox /opt/buildx/bin/busybox\n'
            'RUN ["/opt/buildx/bin/busybox", "--install", "-s", "/opt/buildx/bin"]\n')
        _docker_build(probe, context)
        try:
            found = subprocess.run(
                ['docker', 'run', '--rm', '--entrypoint', '/opt/buildx/bin/busybox',
                 '-e', f'BUILDX_ENV_SETUP={env_setup}', '-e', 'PATH=/opt/buildx/bin:/usr/bin:/bin',
                 probe, 'sh', '-c', (RECIPES / 'discover.sh').read_text()],
                capture_output=True, text=True)
            facts = parse_facts(found.stdout)
            logger.debug(f"   discovered: {facts}")
            if kind == KIND_OE_SDK and not facts.get('ENV_SETUP'):
                raise ImageError(
                    f"No SDK environment script (environment-setup-*) found in {image}; "
                    f"name it with the {LABEL_ENV_SETUP} label.")
            if not facts.get('ROS_DISTRO'):
                raise ImageError(f"No ROS 2 installation (/opt/ros/<distro>) found in {image}.")
            if facts.get('AMENT_CMAKE_ROS_CORE') == 'unknown':
                logger.warning(
                    "⚠ rcutils needs ament_cmake_ros_core, which the image lacks, and the "
                    "version to add could not be read from ament_cmake_ros; builds will fail.")
            elif facts.get('AMENT_CMAKE_ROS_CORE'):
                print(f"   Adding ament_cmake_ros_core {facts['AMENT_CMAKE_ROS_CORE']}, which "
                      "the image's rcutils needs and the image lacks")

            for name in ('fix-links.sh', 'ament-cmake-ros-core.sh'):
                shutil.copy(RECIPES / name, context / name)
            (context / 'env.sh').write_text(render_env_sh(facts, image))
            path_env = env_of(inspected).get(
                'PATH', '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin')
            (context / 'Dockerfile').write_text(
                render_prepared_dockerfile(probe, facts, kind, image, path_env))
            _docker_build(tag, context)
        finally:
            subprocess.run(['docker', 'rmi', probe], capture_output=True)
    return tag


def derive_cross(image, inspected):
    """Return the tag of the cross image for a foreign-architecture *image*, building it once."""
    tag = f'{LOCAL_REPO}:cross-{short_id(inspected)}-{recipes_hash()}'
    if _image_exists(tag):
        return tag

    target = image_platform(inspected)
    os_release = parse_os_release(read_image_file(image, '/etc/os-release', target))
    build_args = cross_build_args(os_release, target)
    build_args['TARGET_IMAGE'] = image
    print(f"🔧 Building a cross image for {image} ({target}), once per image version ({tag})")
    print(f"   Host side: {build_args['HOST_IMAGE']} with {build_args['TRIPLET']}-gcc; "
          "nothing runs under emulation")
    with tempfile.TemporaryDirectory(prefix='colcon-buildx-') as tmp:
        for f in (RECIPES / 'cross').iterdir():
            shutil.copy(f, Path(tmp) / f.name)
        _docker_build(tag, tmp, build_args)
    return tag
