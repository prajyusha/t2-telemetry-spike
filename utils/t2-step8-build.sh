#!/bin/sh
set -eu
# Run inside native-platform; no source or credential changes.
python3 - <<'PY'
import pathlib, shutil, json, hashlib
root = pathlib.Path('/opt/t2-orig')
if root.exists():
    raise SystemExit('/opt/t2-orig already exists; refusing to overwrite backup')
root.mkdir()
names = ['libt2utils', 'libdcautil', 'librbusmethod', 'libbulkdata',
         'libccspinterface', 'libreportgen', 'libscheduler', 'libhttp',
         'libt2parser', 'libxconfclient', 'libtelemetry_msgsender']
files = [pathlib.Path('/usr/local/bin/telemetry2_0')]
for name in names:
    files.extend(pathlib.Path('/usr/local/lib').glob(name + '.*'))
manifest = []
for src in files:
    dst = root / src.relative_to('/')
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst, follow_symlinks=False)
    manifest.append({'path': str(src), 'link': str(src.readlink()) if src.is_symlink() else None,
                     'sha256': hashlib.sha256(src.read_bytes()).hexdigest()})
(root / 'manifest.json').write_text(json.dumps(manifest, indent=2))
print('BACKUP', len(manifest), 'artifacts')
shutil.copytree('/mnt/L2_CONTAINER_SHARED_VOLUME/telemetry', '/opt/t2-debug-src',
                ignore=shutil.ignore_patterns('.git', '.DS_Store'))
PY
cd /opt/t2-debug-src
export INSTALL_DIR=/usr/local
export CFLAGS="-g -O0 -fsanitize=address -fno-omit-frame-pointer -I/usr/local/include/rtmessage -I/usr/local/include/msgpack -I/usr/local/include/rbus -I/usr/local/include $(pkg-config --cflags glib-2.0) -DFEATURE_SUPPORT_WEBCONFIG -DRDK_LOGGER -DPERSIST_LOG_MON_REF -DDCMAGENT -DENABLE_MTLS"
export CXXFLAGS="$CFLAGS"
export LDFLAGS="-fsanitize=address -L/usr/local/lib $(pkg-config --libs glib-2.0)"
autoreconf --install
./configure --prefix=/usr/local --enable-rdkcertselector=yes --enable-dynamic-table-support=yes
make -j2 V=1
make install
ldconfig
echo STEP8_BUILD_INSTALLED
