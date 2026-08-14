#!/bin/sh
set -eu

export DISPLAY="${DISPLAY:-:99}"
export JAVSP_GOOGLE_BROWSER_VNC=1

Xvfb "$DISPLAY" -screen 0 1440x900x24 -ac +extension GLX +render -noreset &
x11vnc -display "$DISPLAY" -localhost -forever -shared -nopw -rfbport "${JAVSP_GOOGLE_VNC_PORT:-5900}" &

exec python -m javsp_web.server
