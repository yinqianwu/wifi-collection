#!/bin/bash
# Generates MIB .my file load order based on dependencies
for my in "$@"; do
	mod=`egrep 'DEFINITIONS' "$my" | sed -r 's/^[[:blank:]]*([-a-zA-z0-9]+)[[:blank:]]+DEFINITIONS.*$/\1/'`
	for dep in `egrep 'FROM' "$my" | sed -r 's/^.*[[:blank:]]+FROM[[:blank:]]+([-a-zA-Z0-9]+).*$/\1/'`; do
		echo "$mod $dep"
	done
done | tsort | tac
