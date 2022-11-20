#!/bin/bash

set -euxo pipefail

#torbrowser
gpg --recv-keys EB774491D9FF06E2

calc_checksums() {
sudo mkdir -p /mnt/nfsroot/aurzig/aurzig/os/x86_64
#TODO: hardcoded path
sudo chown -R 1000:1000 /mnt/nfsroot/aurzig/aurzig/os/x86_64
mkdir -p /mnt/nfsroot/aurzig/aurzig/os/x86_64
find ${XDG_CACHE_HOME} -name "*.pkg.tar.zst" -exec sudo cp -fv {} /mnt/nfsroot/aurzig/aurzig/os/x86_64 \;
pushd /mnt/nfsroot/aurzig/aurzig/os/x86_64
  sudo repo-add -R aurzig.db.tar.xz *.pkg.tar.zst
popd
}

function exitcleanup {
  calc_checksums
  rm -rf ${XDG_CACHE_HOME}
}
trap exitcleanup EXIT

export XDG_CACHE_HOME=$(mktemp -d)
mkdir -p ${XDG_CACHE_HOME}
calc_checksums

paru -Sy

if [[ "$#" -ge 1 ]]; then
AURCOMBO_PACKAGES="$*"
else

AURCOMBO_PACKAGES=$((pacman -Sl aurzig || true) | cut -d" " -f2)

#
AURCOMBO_PACKAGES="auracle-git beets-extrafiles bitwarden-chromium brave-bin czkawka-cli czkawka-gui eclipse-cpp eclipse-pydev \
extra-cmake-modules-git mkinitcpio-overlayfs mkinitcpio-squashfs-git napi-bash nvidia-470xx-dkms nvidia-470xx-utils \
opencl-nvidia-470xx pacaur paru-bin platformio  python-ajsonrpc \
samsung-unified-driver samsung-unified-driver-common samsung-unified-driver-printer samsung-unified-driver-scanner \
sonixd-appimage stremio superproductivity-bin teams-insiders tor-browser xlayoutdisplay \
klog wsjtx"

#AURCOMBO_PACKAGES="$AURCOMBO_PACKAGES binfmt-qemu-static"

# platformio-udev-rules deps
paru -S --noconfirm  python-colorama python-semantic-version python-tabulate python-pyelftools python-marshmallow python-zeroconf python-aiofiles python-ajsonrpc python-starlette python-wsproto
AURCOMBO_PACKAGES="$AURCOMBO_PACKAGES platformio-udev-rules"


# qemu-user-static glib2-static

AURCOMBO_PACKAGES="$AURCOMBO_PACKAGES nvidia-470xx-dkms"
AURCOMBO_PACKAGES="$AURCOMBO_PACKAGES pacaur"
AURCOMBO_PACKAGES="$AURCOMBO_PACKAGES napi-bash"
AURCOMBO_PACKAGES="$AURCOMBO_PACKAGES tor-browser"
AURCOMBO_PACKAGES="$AURCOMBO_PACKAGES "


fi


touch /tmp/aurcombo_build.txt

for x in ${AURCOMBO_PACKAGES}; do
   if grep -q "^$x$" /tmp/aurcombo_build.txt; then
    echo "skipping"
   else
    pacaur -d -m --noconfirm --noedit --aur-buildonly ${x}
    calc_checksums
    paru -Sy
    bash -c "echo $x >>/tmp/aurcombo_build.txt"
   fi
done
