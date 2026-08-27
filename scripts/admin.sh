#!/usr/bin/env bash
# FANS1 админка: start | stop | status | restart
cd "$(dirname "$0")/.." || exit 1
PIDFILE=/tmp/fans1-admin.pid

is_running() {
  [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null
}

case "${1:-start}" in
  start)
    if is_running; then
      echo "Админка уже запущена: http://127.0.0.1:8765"
      exit 0
    fi
    rm -f "$PIDFILE"
    setsid nohup python3 admin/server.py >/tmp/fans1-admin.log 2>&1 &
    echo $! > "$PIDFILE"
    sleep 1
    if is_running; then
      echo "Админка запущена: http://127.0.0.1:8765 (лог: /tmp/fans1-admin.log)"
    else
      echo "Не удалось запустить — смотри /tmp/fans1-admin.log:"
      tail -n 15 /tmp/fans1-admin.log 2>/dev/null
      exit 1
    fi
    ;;
  stop)
    if is_running; then
      kill "$(cat "$PIDFILE")" 2>/dev/null && rm -f "$PIDFILE" && echo "Остановлена."
    else
      echo "Не запущена (но, возможно, висит чужая копия — см.: ps -ef | grep admin/server.py)"
    fi
    ;;
  restart)
    "$0" stop; sleep 1; "$0" start
    ;;
  status)
    if is_running; then
      echo "Работает (pid $(cat "$PIDFILE")): http://127.0.0.1:8765"
    else
      echo "Не запущена. Запуск: $0 start"
    fi
    ;;
  *)
    echo "использование: $0 {start|stop|status|restart}"
    ;;
esac
