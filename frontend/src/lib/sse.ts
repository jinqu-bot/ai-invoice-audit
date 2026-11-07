/**
 * 审核进度流（SSE）封装。
 *
 * 用法：
 *   const stop = subscribeBatch("B20261104-001", {
 *     onHello: (h) => setReplay(h.replay),
 *     onInvoiceDone: (d) => refresh(),
 *     onBatchDone: () => stop(),
 *   })
 *   组件卸载时调用 stop()，否则连接会一直挂着。
 *
 * D6 起新增三种事件：
 * - `hello`：订阅成功，带 `replay` 标志——**页面必须拿它区分"正在发生"和"回放"**，
 *   不然把历史批次的回放当成实时，是要被抓包的
 * - `batch_start`：这批一共几张，用来提前摆骨架
 * - `file_failed`：某个文件当场失败，附带原因
 */

import { API_BASE } from "./api";
import type {
  StreamBatchDone,
  StreamBatchStart,
  StreamFileFailed,
  StreamHello,
  StreamInvoiceDone,
  StreamStart,
  StreamTrace,
} from "./types";

export interface StreamHandlers {
  onHello?: (data: StreamHello) => void;
  onBatchStart?: (data: StreamBatchStart) => void;
  onStart?: (data: StreamStart) => void;
  onTrace?: (data: StreamTrace) => void;
  onFileFailed?: (data: StreamFileFailed) => void;
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

  bind<StreamHello>("hello", handlers.onHello);
  bind<StreamBatchStart>("batch_start", handlers.onBatchStart);
  bind<StreamStart>("invoice_start", handlers.onStart);
  bind<StreamTrace>("trace", handlers.onTrace);
  bind<StreamFileFailed>("file_failed", handlers.onFileFailed);
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