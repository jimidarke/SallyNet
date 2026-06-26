#!/usr/bin/env bash
# Shared helpers for SallyNet bash tooling — colored output + small utilities.
# Source this near the top of every script:  . "$(dirname "$0")/lib/sally-helpers.sh"
# Style mirrors the sibling gameBox project (header/ok/warn/fail + RED/GREEN/YELLOW/CYAN/NC).

# Colors (disabled automatically when stdout is not a TTY).
if [ -t 1 ]; then
  RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; YELLOW=$'\033[1;33m'; CYAN=$'\033[0;36m'; NC=$'\033[0m'
else
  RED=''; GREEN=''; YELLOW=''; CYAN=''; NC=''
fi

header() { printf '%s\n' "${CYAN}==> $*${NC}"; }
ok()     { printf '%s\n' "${GREEN}  ok  ${NC}$*"; }
warn()   { printf '%s\n' "${YELLOW} warn ${NC}$*" >&2; }
fail()   { printf '%s\n' "${RED} fail ${NC}$*" >&2; }
die()    { fail "$*"; exit 1; }

# require_cmd <cmd> [<cmd> ...] — exit if any command is missing from PATH.
require_cmd() {
  local missing=0 c
  for c in "$@"; do
    command -v "$c" >/dev/null 2>&1 || { fail "missing required command: $c"; missing=1; }
  done
  [ "$missing" -eq 0 ] || exit 1
}

# load_conf [<path>] — source a sally-media.conf if present. Defaults to
# $SALLY_MEDIA_CONF, then /etc/sally/sally-media.conf, then /opt/sally/media/sally-media.conf.
# Silent no-op when none exist (callers still apply their own :=defaults), so the
# encode scripts run standalone on a laptop worker that has no conf installed.
load_conf() {
  local p
  for p in "${1:-${SALLY_MEDIA_CONF:-}}" /etc/sally/sally-media.conf /opt/sally/media/sally-media.conf; do
    if [ -n "$p" ] && [ -f "$p" ]; then
      # shellcheck disable=SC1090
      set -a; . "$p"; set +a
      return 0
    fi
  done
  return 0
}
