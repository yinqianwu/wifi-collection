#!/bin/bash
egrep 'cisco.*MIBObjects' all_oids.txt \
| sed -e 's/^.*--//' -e 's/(.*$//' \
| while read node; do
	./walk2.sh $node 2>&1 >/dev/null
done \
| egrep -v '^(MIB search path|Cannot find module|Did not find|Unlinked OID|Undefined indentifier|Bad timestamp|Group not found|Bad month|Undefined OBJ|Cannot adopt|Undefined ident|Object not found in mod)'
