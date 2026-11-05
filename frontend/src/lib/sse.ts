/**
 * 审核进度流（SSE）封装。
 *
 * 用法：
 *   const stop = subscribeBatch("B20261104-001", {
 *     onTrace: (t) => setSteps((s) => [...s, t]),
 *     onBatchDone: () => stop(),
 *   })
 *   组件卸载时调用 stop()，否则连接会一直挂着。
 */

import { API_BASE } from "./api";
import type {
  StreamBatchDone,
  StreamInvoiceDone,
  StreamStart,
  StreamTrace,
} from "./types";

export interface StreamHandlers {
  onStart?: (data: StreamStart) => void;
  onTrace?: (data: StreamTrace) => void;
  onInvoiceDone?: (data: StreamInvoiceDone) => void;
  onBatchDone?: (data: StreamBatchDone) => void;
  onError?: (err: unknown) => void;
}

export function subscribeBatch(batchId: string, handlers: StreamHandlers): () => void {
  const url = `${API_BASE}/api/batches/${encodeURIComponent(batchId)}/stream`;
  const es = new EventSource(url);

  const bind = <T,>(event: string, cb?: (data: T) => void) => {
    if (!cb) return;
    es.addEventListener(event, (e) => {
      try {
        cb(JSON.parse((e as MessageEvent).data) as T);
      } catch (err) {
        handlers.onError?.(err);
      }
    });
  };

  bind<StreamStart>("invoice_start", handlers.onStart);
  bind<StreamTrace>("trace", handlers.onTrace);
  bind<StreamInvoiceDone>("invoice_done", handlers.onInvoiceDone);
  bind<StreamBatchDone>("batch_done", (data) => {
    handlers.onBatchDone?.(data);
    es.close();
  });

  es.onerror = (err) => {
    handlers.onError?.(err);
    es.close();
  };

  return () => es.close();
}
