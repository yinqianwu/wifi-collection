#!/bin/bash
# Sorts out newest MIB .py file by last-updated field
# between CCO FTP v2 archive and WLC8.3 Zip archive
DIN="z83"
DOUT="c83"
DV2="v2"
for F in "${DIN}"/*.my; do
	MY="${F#$DIN/}"
	NEWEST=`egrep "LAST-UPDATED" "${DIN}/${MY}" "${DV2}/${MY}" 2>/dev/null \
	| sed -e 's/^\(.*\.my\):.*LAST-UPDATED[ '$'\t'']*"\([0-9][0-9]*\)Z".*$/\2 \1/' \
	| sort | tail -n1 | cut -d' ' -f2`
	echo "newest: ${NEWEST}"
	cp "${NEWEST}" "${DOUT}"
done

