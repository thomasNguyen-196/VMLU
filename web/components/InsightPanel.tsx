"use client";

import { buildInsight } from "@/lib/insights.ts";
import { ModelNotePanel } from "@/components/ModelNotePanel.tsx";

/** Khối "Nhận xét & hướng kiểm chứng" cho một lần chạy (mô hình × bộ dữ liệu).
 *  Diễn giải chuyên biệt + bằng chứng số rút từ summary; thuần trình bày,
 *  không fetch thêm (summary đã có sẵn ở panel cha). */
export function InsightPanel({
  modelId,
  datasetId,
  summary,
}: {
  modelId: string;
  datasetId: string;
  summary: Record<string, unknown>;
}) {
  const insight = buildInsight(modelId, datasetId, summary);

  return (
    <div className="mt-4 space-y-2.5 rounded-xl border border-hair bg-card p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold text-ink">💡 Nhận xét &amp; hướng kiểm chứng</span>
        <span
          className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${
            insight.curated
              ? "border-hair bg-paper text-ink-2"
              : "border-hair bg-card text-ink-3"
          }`}
        >
          {insight.curated ? "AI soạn · chưa có người đánh giá xác nhận" : "bằng chứng tự động"}
        </span>
        <span className="font-mono text-[10px] text-slate-400">
          {modelId} × {datasetId}
        </span>
      </div>

      <p className="text-xs leading-relaxed text-ink-2">{insight.verdict}</p>

      {insight.evidence.length > 0 && (
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-3">Bằng chứng số</p>
          <ul className="mt-1 space-y-0.5 font-mono text-[11px] leading-relaxed text-ink-2">
            {insight.evidence.map((e, i) => (
              <li key={i}>• {e}</li>
            ))}
          </ul>
        </div>
      )}

      {insight.causes.length > 0 && (
        <div className="space-y-1">
          <span className="text-[11px] font-semibold uppercase tracking-wide text-ink-3">
            Giả thuyết cần kiểm chứng
          </span>
          <div className="flex flex-wrap items-center gap-1.5">
            {insight.causes.map((c) => (
              <span
                key={c.tag}
                title={c.desc}
                className="rounded-full border border-flag/40 bg-flag-soft px-2 py-0.5 text-[10px] font-semibold text-flag"
              >
                {c.label}
              </span>
            ))}
          </div>
          <ul className="space-y-0.5 text-[11px] leading-relaxed text-ink-2">
            {insight.causes.map((c) => (
              <li key={c.tag}>
                <span className="font-semibold text-flag">{c.label}:</span> {c.desc}
              </li>
            ))}
          </ul>
        </div>
      )}

      {insight.actions.length > 0 && (
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-3">
            Phép kiểm chứng đề xuất
          </p>
          <ol className="mt-1 list-decimal space-y-0.5 pl-4 text-xs leading-relaxed text-ink-2">
            {insight.actions.map((a, i) => (
              <li key={i}>{a}</li>
            ))}
          </ol>
        </div>
      )}

      {insight.caveat && (
        <p className="rounded-lg border border-flag/40 bg-flag-soft px-2.5 py-1.5 text-[11px] leading-relaxed text-flag">
          ⚠️ Giới hạn diễn giải: {insight.caveat}
        </p>
      )}

      <ModelNotePanel modelId={modelId} datasetId={datasetId} />
    </div>
  );
}
