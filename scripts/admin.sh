#!/usr/bin/env bash
# FANS1 админка: start | stop | status
cd "$(dirname "$0")/.." || exit 1
PIDFILE=/tmp/fans1-admin.pid

case "${1:-start}" in
  start)
    if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
      echo "Админка уже запущена: http://127.0.0.1:8765"
      exit 0
    fi
    nohup python3 admin/server.py >/tmp/fans1-admin.log 2>&1 &
    echo $! > "$PIDFILE"
    sleep 1
    echo "Админка запущена: http://127.0.0.1:8765 (лог: /tmp/fans1-admin.log)"
    ;;
  stop)
    if [ -f "$PIDFILE" ]; then
      kill "$(cat "$PIDFILE")" 2>/dev/null && rm -f "$PIDFILE" && echo "Остановлена."
    else
      echo "Не запущена."
    fi
    ;;
  status)
    if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
      echo "Работает (pid $(cat "$PIDFILE")): http://127.0.0.1:8765"
    else
      echo "Не запущена. Запуск: $0 start"
    fi
    ;;
  *)
    echo "использование: $0 {start|stop|status}"
    ;;
esac
