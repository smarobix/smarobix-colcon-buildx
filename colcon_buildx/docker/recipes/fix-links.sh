# SPDX-FileCopyrightText: 2026 SMAROBIX GmbH
# SPDX-License-Identifier: Apache-2.0
#
# Runs once while colcon-buildx prepares an image. An SDK image may carry no userland of its own:
# its /usr/bin/sh and /usr/bin/env can point into the SDK at files that do not exist. Point every
# such broken link at the static busybox, if busybox has that command, and drop the rest.

export PATH="/opt/buildx/bin:$PATH"
for dir in /bin /usr/bin; do
  [ -d "$dir" ] || continue
  for link in "$dir"/*; do
    [ -L "$link" ] && [ ! -e "$link" ] || continue
    name=${link##*/}
    rm -f "$link"
    if [ -e "/opt/buildx/bin/$name" ]; then
      ln -s /opt/buildx/bin/busybox "$link"
      echo "colcon-buildx: $link -> busybox"
    else
      echo "colcon-buildx: removed broken link $link"
    fi
  done
done
[ -e /bin/sh ] || ln -s /opt/buildx/bin/busybox /bin/sh
[ -e /usr/bin/env ] || ln -s /opt/buildx/bin/busybox /usr/bin/env

# OE's relocation wrappers (python3 and friends) start with #!/bin/bash, but are plain sh plus
# `exec -a`, which BusyBox's sh has too. Without a bash in the image, run them in that.
for bash in /bin/bash /usr/bin/bash; do
  [ -d "${bash%/*}" ] && [ ! -e "$bash" ] || continue
  printf '%s\n' '#!/opt/buildx/bin/busybox sh' \
    '# colcon-buildx: this image has no bash; this runs BusyBox sh in its place.' \
    'exec /opt/buildx/bin/busybox sh "$@"' > "$bash"
  chmod 755 "$bash"
  echo "colcon-buildx: $bash -> busybox sh"
done
