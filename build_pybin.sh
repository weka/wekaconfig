# this file uses pyinstaller to create the binary tarball that is used to deploy the tool binary
# this allows the tool binary to be deployed without installing python and other required python packages
#
TOOL=`basename $PWD`
MAIN=$TOOL.py
TARGET=tarball/$TOOL

pyinstaller --hidden-import npyscreen \
            --hidden-import ssh2.agent \
            --hidden-import ssh2.pkey \
            --hidden-import ssh2.exceptions \
            --hidden-import ssh2.sftp \
            --hidden-import ssh2.sftp_handle \
            --hidden-import ssh2.channel \
            --hidden-import ssh2.listener \
            --hidden-import ssh2.statinfo \
            --hidden-import ssh2.knownhost \
            --hidden-import ssh2.error_codes \
            --hidden-import ssh2.fileinfo \
            --hidden-import ssh2.utils \
            --hidden-import ssh2.publickey \
            --hidden-import ssh.channel \
            --hidden-import ssh.utils \
            --hidden-import ssh.connector \
            --hidden-import ssh.keytypes \
            --hidden-import ssh.sftp \
            --hidden-import ssh.sftp_attributes \
            --hidden-import ssh.sftp_handles \
            --hidden-import ssh.sftp_statvfs \
            --hidden-import ssh.scp \
            --add-data xterm-256color:xterm-256color \
            --onefile $MAIN

mkdir -p $TARGET
cp dist/$TOOL $TARGET

cd tarball
tar cvzf ../${TOOL}.tar $TOOL
