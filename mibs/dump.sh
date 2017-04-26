#!/bin/bash
# Exports a complete MIB tree to a Python module
echo 'MIBS = ['
smidump -c smirc -k -f python `cat load-order` \
| egrep -v '^(#.*|FILENAME.*|)$' \
|  sed -e 's/^}/},/' -e 's/^MIB = //'
echo ']'
