#!/bin/bash

# script for building ipxe.pxe with defined boot script
# boot server can be provided by COMBOSERVER variable
# or comboserver.lan will be used otherwise

set -euo pipefail

# ipxe will boot from this server
COMBOSERVER="${COMBOSERVER:-comboserver.lan:9999}"

echo "ipxe will boot from ${COMBOSERVER}"

SCRIPTDIR=$(dirname $(readlink -f $0))
IPXEDIR=$(mktemp -d)

rm -rf ${IPXEDIR}
rm -rf ipxe.pxe
git clone git://git.ipxe.org/ipxe.git ${IPXEDIR}

pushd  ${IPXEDIR} >/dev/null

# ignore compile warnings
sed -i "s/^CFLAGS.*:=/CFLAGS := -Wno-error=array-bounds -Wno-error=dangling-pointer=/" src/Makefile

cat >comboboot.ipxe <<EOF
#!ipxe

:start

echo "Running comboboot bootstrap"

echo "Dhcp start"
:dhcp_start
dhcp && goto dhcp_ok || sleep 1
sleep 1
goto dhcp_start
:dhcp_ok

echo "chain load"
chain http://${COMBOSERVER}/\${uuid}/cfg || echo "chain failed!"
echo "reboot in 60 seconds"
sleep 60
reboot
EOF

echo "Building ipxe..."
make -C ${IPXEDIR} EMBED=${IPXEDIR}/comboboot.ipxe -j$(nproc) -C src bin/ipxe.pxe bin/ipxe.lkrn >log.txt 2>&1 || \
    (cat log.txt && echo "build failed" && exit 1)
cp -f ${IPXEDIR}/src/bin/ipxe.pxe ${SCRIPTDIR}/comboboot.pxe
popd >/dev/null

rm -rf ${IPXEDIR}

echo "ipxe.pxe build successfully"
