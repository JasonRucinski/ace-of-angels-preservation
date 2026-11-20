#!/bin/bash
# usage: shot.sh OUT.png SECONDS command...   (runs the command on a virtual screen and captures it)
out=$1; secs=$2; shift 2
Xvfb :97 -screen 0 1400x900x24 >/dev/null 2>&1 &
xpid=$!
sleep 1
DISPLAY=:97 "$@" >"$out.log" 2>&1 &
apid=$!
sleep "$secs"
DISPLAY=:97 import -window root "$out"
kill $apid 2>/dev/null; sleep 0.5; kill $xpid 2>/dev/null
wait 2>/dev/null
echo "captured $out; app log tail:"; tail -5 "$out.log"
