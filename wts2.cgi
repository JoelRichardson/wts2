#!/usr/bin/bash
if [ ! -e "./Configuration" ] ; then
    echo "No configuration file."
    exit 1
fi
. ./Configuration
. ./venv/bin/activate
umask u=rwx,g=rwx,o=rx
python ./wts2.py
