#!/bin/bash
# Displays a complete MIB tree
smidump -c smirc -k -f tree `cat load-order` \
| egrep -v '^# WARNING:' \
| sed 's/^# \(.*\) registration tree.*/\n\n\1/'
