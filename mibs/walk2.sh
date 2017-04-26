#!/bin/bash
snmpwalk -v2c -c public -OX -Pd -Pe -M wlc83 -m ALL sln-wlab-gw:2161 "$@"
