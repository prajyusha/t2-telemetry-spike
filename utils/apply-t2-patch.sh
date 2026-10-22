#!/bin/sh
# PUBLIC_INTERFACE
# Apply the JSON HTTP initialization fix and install T2 in native-platform.
# Usage from the workspace: sh utils/apply-t2-patch.sh [normal|asan]
# Requires the running container, shared checkout, build tools and original backup.
set -eu
mode=${1:-normal}
case "$mode" in normal|asan) ;; *) echo "Usage: $0 [normal|asan]" >&2; exit 2 ;; esac
shared=/mnt/L2_CONTAINER_SHARED_VOLUME
if [ "${2:-}" != "--inside" ]; then
    exec docker exec native-platform sh "$shared/utils/apply-t2-patch.sh" "$mode" --inside
fi
test -f /opt/t2-orig/manifest.json
if pgrep -x telemetry2_0 >/dev/null; then
    echo "Stop T2 before installing; refusing to replace running libraries." >&2
    exit 1
fi
# Never write into the original backup or native credential directories.
python3 - <<'PY'
import pathlib
import shutil

source = pathlib.Path('/mnt/L2_CONTAINER_SHARED_VOLUME/telemetry')
target = pathlib.Path('/opt/t2-patched-src')
if not target.exists():
    shutil.copytree(source, target,
                    ignore=shutil.ignore_patterns('.git', '.DS_Store'))
if not (target / 'source/t2parser/t2parser.c').is_file():
    raise SystemExit('Missing parser in isolated source copy')
PY
cd /opt/t2-patched-src
if patch --dry-run --batch --forward -p1 < "$shared/utils/t2-prepareHttpUrl-fix.diff"; then
    patch --batch --forward -p1 < "$shared/utils/t2-prepareHttpUrl-fix.diff"
elif patch --dry-run --batch --reverse -p1 < "$shared/utils/t2-prepareHttpUrl-fix.diff"; then
    echo "Initialization patch already applied."
else
    echo "Patch does not match isolated source; refusing to continue." >&2
    exit 1
fi
export INSTALL_DIR=/usr/local
export top_srcdir=/opt/t2-patched-src
export top_builddir=/opt/t2-patched-src
debug="-Wall -Werror -Wextra"
sanitize=""
if [ "$mode" = asan ]; then
    debug="-g -O0 -fsanitize=address -fno-omit-frame-pointer"
    sanitize="-fsanitize=address"
fi
# Match build_inside_container.sh; pkg-config selects the image architecture.
export CFLAGS="$debug -I$INSTALL_DIR/include/rtmessage -I$INSTALL_DIR/include/msgpack -I$INSTALL_DIR/include/rbus -I$INSTALL_DIR/include $(pkg-config --cflags glib-2.0) -DFEATURE_SUPPORT_WEBCONFIG -DRDK_LOGGER -DPERSIST_LOG_MON_REF -DDCMAGENT -DENABLE_MTLS"
export CXXFLAGS="$CFLAGS"
export LDFLAGS="$sanitize -L/usr/local/lib $(pkg-config --libs glib-2.0)"
autoreconf --install
./configure --prefix=/usr/local --enable-rdkcertselector=yes --enable-dynamic-table-support=yes
# distclean visits disabled DIST_SUBDIRS without generated Makefiles.
# Reconfigure first, then clean every enabled target before changing modes.
make clean
make -j2 V=1
make install
ldconfig
for binary in /usr/local/bin/telemetry2_0 /usr/local/lib/libreportgen.so /usr/local/lib/libbulkdata.so; do
    echo "LINKAGE $binary"
    links=$(ldd "$binary")
    printf '%s\n' "$links"
    if [ "$mode" = asan ]; then
        printf '%s\n' "$links" | grep -q libasan
    elif printf '%s\n' "$links" | grep -q libasan; then
        echo "Unexpected ASan dependency in normal build" >&2
        exit 1
    fi
done
echo "STEP10_INSTALLED mode=$mode"
