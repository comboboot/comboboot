#!/bin/bash

set -eux

sysimage_prepare() {
  mkdir -p /alisdir
  umount /alisdir || true
  mount -t tmpfs -o size=15G tmpfs /alisdir
}

sysimage_build() {
  pushd alis
    ./alis.sh
  popd

  install -m0755 combobootaur_rebuildfeed.sh /alisdir/usr/bin/combobootaur_rebuildfeed.sh
  install -m0755 comboboot_get.sh /alisdir/usr/bin/comboboot_get.sh
}

sysimage_publish() {
  UUID=$(cat /sys/class/dmi/id/product_uuid)

  FILES=""
  pushd /alisdir/
  for F in $(find boot -type f -exec echo "{}" \;); do
   FILES="$FILES -F $(basename $F)=@$(readlink -f $F)"
  done
  popd

  cat >/tmp/cfg <<EOF
kernel http://{WEBSESSION}/vmlinuz-linux ip=dhcp squashfs=http://{WEBSESSION}/rootfs.squashfs
initrd http://{WEBSESSION}/amd-ucode.img
initrd http://{WEBSESSION}/initramfs-linux.img
EOF

  tar -cv --one-file-system --zstd -f - -C /alisdir . | curl --progress-bar --verbose -XPOST -T - http://192.168.1.26:9999/${UUID}/upload

  FILES="$FILES -F cfg=@/tmp/cfg"
  curl --progress-bar --verbose $FILES http://192.168.1.26:9999/${UUID}/upload

}

echo "waitint for system to finish boot up"
systemctl is-system-running --wait || true
sysimage_prepare
sysimage_build
sysimage_publish
echo "Done."
