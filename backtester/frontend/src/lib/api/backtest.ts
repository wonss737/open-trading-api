/**
 * 백테스트 API — 비동기 잡 패턴
 *
 * POST /run  → job_id 즉시 반환 (202)
 * GET  /jobs/{job_id} → 상태 폴링 (pending / running / completed / failed)
 */

import { apiGet, apiPost } from "./client";
import type {
  BacktestRequest,
  BacktestJobResponse,
  BacktestResponse,
  CustomBacktestRequest,
  JobSubmitResponse,
} from "@/types";

const POLL_INTERVAL_MS = 2000;
const POLL_TIMEOUT_MS = 15 * 60 * 1000; // 15분

async function pollJob(jobId: string): Promise<BacktestResponse> {
  const deadline = Date.now() + POLL_TIMEOUT_MS;
  while (Date.now() < deadline) {
    const job = await apiGet<BacktestJobResponse>(`/api/backtest/jobs/${jobId}`);
    if (job.status === "completed") {
      return { success: true, data: job.result!, message: "백테스트 완료" };
    }
    if (job.status === "failed") {
      throw new Error(job.error || "백테스트 실패");
    }
    // pending / running → 대기 후 재시도
    await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
  }
  throw new Error("백테스트 폴링 시간 초과 (15분)");
}

/**
 * 백테스트 실행 (Preset 전략)
 */
export async function runBacktest(request: BacktestRequest): Promise<BacktestResponse> {
  const { job_id } = await apiPost<JobSubmitResponse>("/api/backtest/run", request);
  return pollJob(job_id);
}

/**
 * 커스텀 전략 백테스트 실행 (YAML)
 */
export async function runCustomBacktest(
  yamlContent: string,
  symbols: string[],
  startDate: string,
  endDate: string,
  initialCapital: number,
  commissionRate?: number,
  taxRate?: number,
  slippage?: number
): Promise<BacktestResponse> {
  const request: CustomBacktestRequest = {
    yaml_content: yamlContent,
    symbols,
    start_date: startDate,
    end_date: endDate,
    initial_capital: initialCapital,
    commission_rate: commissionRate,
    tax_rate: taxRate,
    slippage,
  };
  const { job_id } = await apiPost<JobSubmitResponse>("/api/backtest/run-custom", request);
  return pollJob(job_id);
}
