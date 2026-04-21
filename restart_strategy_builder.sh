#!/bin/bash
# P1 Strategy Builder - Restart Script

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 포트를 강제 종료하고 실제로 해제될 때까지 대기
kill_and_wait() {
  local port=$1
  local pids
  pids=$(lsof -ti:"$port" 2>/dev/null)
  if [ -n "$pids" ]; then
    echo "Port $port 사용 중인 프로세스 종료 중 (PID: $pids)..."
    echo "$pids" | xargs kill -9 2>/dev/null
    # 포트가 실제로 해제될 때까지 최대 10초 대기
    local waited=0
    while lsof -ti:"$port" >/dev/null 2>&1; do
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

echo "=== P1 Strategy Builder 재시작 ==="
kill_and_wait 3000
kill_and_wait 8000

echo "Starting P1 Strategy Builder..."
exec bash "$SCRIPT_DIR/strategy_builder/start.sh"
