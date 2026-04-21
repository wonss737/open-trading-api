#!/bin/bash
# P2 Backtester - Restart Script

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 포트를 강제 종료하고 실제로 해제될 때까지 대기
kill_and_wait() {
  local port=$1
  local pids
  # fuser로 IPv4/IPv6 모두 탐지 (lsof는 IPv6 바인딩을 놓칠 수 있음)
  pids=$(fuser "${port}/tcp" 2>/dev/null)
  if [ -n "$pids" ]; then
    echo "Port $port 사용 중인 프로세스 종료 중 (PID: $pids)..."
    fuser -k "${port}/tcp" 2>/dev/null
    # 포트가 실제로 해제될 때까지 최대 10초 대기
    local waited=0
    while fuser "${port}/tcp" >/dev/null 2>&1; do
      sleep 0.5
      waited=$((waited + 1))
      if [ $waited -ge 20 ]; then
        echo "경고: 포트 $port 해제 대기 시간 초과"
        break
      fi
    done
    echo "Port $port 해제 완료"
  else
    echo "Port $port 사용 중인 프로세스 없음"
  fi
}

echo "=== P2 Backtester 재시작 ==="
kill_and_wait 3001
kill_and_wait 8002

echo "Starting P2 Backtester..."
exec bash "$SCRIPT_DIR/backtester/start.sh"
