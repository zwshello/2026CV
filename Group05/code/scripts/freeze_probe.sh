#!/usr/bin/env bash
# Freeze probe helper for collecting logs before a hard lock.
set -euo pipefail

MODE="${1:-}"
LOG_DIR="${FREEZE_PROBE_DIR:-/tmp/freeze_probe}"
PID_DIR="/tmp/freeze_probe_pids"

usage() {
    cat <<'EOF'
Usage:
  sudo bash scripts/freeze_probe.sh start [LOG_DIR]
  sudo bash scripts/freeze_probe.sh stop
  sudo bash scripts/freeze_probe.sh status
  sudo bash scripts/freeze_probe.sh prevboot [LOG_DIR]

Commands:
  start     Start realtime probes: kernel log, system log, io/cpu sampler.
  stop      Stop all probe processes.
  status    Show probe process state and current log files.
  prevboot  Export previous boot logs (-b -1) for post-freeze analysis.

Notes:
  - Default LOG_DIR is /tmp/freeze_probe
  - You can override default path with env var FREEZE_PROBE_DIR
EOF
}

require_root() {
    if [[ ${EUID} -ne 0 ]]; then
        echo "ERROR: root is required. Run with sudo."
        exit 1
    fi
}

set_log_dir_from_arg() {
    if [[ $# -ge 1 && -n "${1:-}" ]]; then
        LOG_DIR="$1"
    fi
}

pid_file() {
    local name="$1"
    echo "$PID_DIR/${name}.pid"
}

is_pid_running() {
    local pid="$1"
    [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

start_probe() {
    local name="$1"
    shift

    local pf
    pf="$(pid_file "$name")"
    if [[ -f "$pf" ]]; then
        local existing
        existing="$(cat "$pf" 2>/dev/null || true)"
        if is_pid_running "$existing"; then
            echo "[start] ${name} already running (pid=${existing})"
            return 0
        fi
        rm -f "$pf"
    fi

    "$@" &
    local new_pid=$!
    echo "$new_pid" > "$pf"
    echo "[start] ${name} pid=${new_pid}"
}

start_mode() {
    require_root
    set_log_dir_from_arg "${2:-}"

    mkdir -p "$LOG_DIR" "$PID_DIR"

    start_probe kernlog bash -c "exec journalctl -kf > \"$LOG_DIR/kern.log\" 2>&1"
    start_probe syslog bash -c "exec journalctl -f > \"$LOG_DIR/sys.log\" 2>&1"
    start_probe sampler bash -c '
        while true; do
            echo "===== $(date --iso-8601=seconds) ====="
            echo "[loadavg] $(cat /proc/loadavg)"
            free -h | sed -n "1,3p"
            echo "[io]"
            if command -v iostat >/dev/null 2>&1; then
                iostat -xz 1 1 2>/dev/null || true
            else
                cat /proc/diskstats | sed -n "1,10p"
            fi
            echo "[top-cpu]"
            ps -eo pid,comm,state,%cpu,%mem,etime --sort=-%cpu | sed -n "1,15p"
            echo
            sleep 1
        done
    ' > "$LOG_DIR/io.log" 2>&1

    echo
    echo "Probe started. Logs are written to: $LOG_DIR"
    echo "Reproduce the freeze, then run: sudo bash scripts/freeze_probe.sh stop"
}

stop_mode() {
    mkdir -p "$PID_DIR"

    local any=0
    for name in kernlog syslog sampler; do
        local pf pid
        pf="$(pid_file "$name")"
        if [[ ! -f "$pf" ]]; then
            continue
        fi
        pid="$(cat "$pf" 2>/dev/null || true)"
        if is_pid_running "$pid"; then
            any=1
            echo "[stop] stopping ${name} pid=${pid}"
            kill "$pid" 2>/dev/null || true
            sleep 1
            if is_pid_running "$pid"; then
                kill -9 "$pid" 2>/dev/null || true
            fi
        fi
        rm -f "$pf"
    done

    if [[ $any -eq 0 ]]; then
        echo "[stop] no running probe process found."
    else
        echo "[stop] probe processes stopped."
    fi
}

status_mode() {
    set_log_dir_from_arg "${2:-}"

    echo "=== freeze_probe status ==="
    echo "LOG_DIR: $LOG_DIR"

    for name in kernlog syslog sampler; do
        local pf pid state
        pf="$(pid_file "$name")"
        pid="-"
        state="stopped"
        if [[ -f "$pf" ]]; then
            pid="$(cat "$pf" 2>/dev/null || true)"
            if is_pid_running "$pid"; then
                state="running"
            fi
        fi
        echo "  - $name: $state (pid=$pid)"
    done

    if [[ -d "$LOG_DIR" ]]; then
        echo
        echo "Log files:"
        ls -lh "$LOG_DIR" 2>/dev/null || true
    else
        echo
        echo "Log dir does not exist yet."
    fi
}

prevboot_mode() {
    require_root
    set_log_dir_from_arg "${2:-}"

    mkdir -p "$LOG_DIR"

    echo "[prevboot] exporting previous boot kernel log..."
    journalctl -b -1 -k --no-pager > "$LOG_DIR/prevboot-kernel.log" || true

    echo "[prevboot] exporting previous boot full system log..."
    journalctl -b -1 --no-pager > "$LOG_DIR/prevboot-system.log" || true

    echo "[prevboot] done. Files:"
    ls -lh "$LOG_DIR" | sed -n '1,20p'
}

case "$MODE" in
    start)
        start_mode "$@"
        ;;
    stop)
        stop_mode
        ;;
    status)
        status_mode "$@"
        ;;
    prevboot)
        prevboot_mode "$@"
        ;;
    *)
        usage
        exit 1
        ;;
esac
