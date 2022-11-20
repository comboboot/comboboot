#!/bin/bash

set -eux

rm -rf /tmp/comboboot_sfx.sh
curl http://192.168.1.26:9999/static/comboboot_sfxgen.sh.cgi --output /tmp/comboboot_sfx.sh
chmod +x /tmp/comboboot_sfx.sh
/tmp/comboboot_sfx.sh
