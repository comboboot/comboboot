#!/bin/bash

# pipes on stdout self extracting archive

SCRIPTDIR=$(dirname  $0)

cd $SCRIPTDIR

cat <<END
#!/bin/bash

TEMP=\$(mktemp -d)

cat \$0 | (cd \$TEMP && sed '0,/^#EOF#$/d' | tar zx;./comboboot_install.sh)

exit 0
#EOF#
END

tar zcf - --exclude-vcs --dereference $(ls -1 | grep -E -v "^combogen\.sh$|^iso$|^cfg$")
