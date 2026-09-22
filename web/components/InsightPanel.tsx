"use client";

import { buildInsight } from "@/lib/insights.ts";
import { ModelNotePanel } from "@/components/ModelNotePanel.tsx";

/** Khối "Insight & định hướng" cho một run (model × dataset).
 *  Nhận định thủ công + bằng chứng số rút từ summary; thuần trình bày,
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
    <div className="mt-4 space-y-2.5 rounded-xl border border-indigo-100 bg-indigo-50/40 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold text-indigo-900">💡 Insight &amp; định hướng</span>
        <span
          className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${
            insight.curated
              ? "border-indigo-200 bg-white text-indigo-700"
              : "border-slate-200 bg-white text-slate-500"
          }`}
        >
          {insight.curated ? "nhận định thủ công" : "chỉ bằng chứng tự động"}
        </span>
        <span className="font-mono text-[10px] text-slate-400">
          {modelId} × {datasetId}
        </span>
      </div>

      <p className="text-xs leading-relaxed text-slate-700">{insight.verdict}</p>

      {insight.evidence.length > 0 && (
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Bằng chứng số</p>
          <ul className="mt-1 space-y-0.5 font-mono text-[11px] leading-relaxed text-slate-700">
            {insight.evidence.map((e, i) => (
              <li key={i}>• {e}</li>
            ))}
          </ul>
        </div>
      )}

      {insight.causes.length > 0 && (
        <div className="space-y-1">
          <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            Nguyên nhân khả nghi
          </span>
          <div className="flex flex-wrap items-center gap-1.5">
            {insight.causes.map((c) => (
              <span
                key={c.tag}
                title={c.desc}
                className="rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[10px] font-semibold text-amber-800"
              >
                {c.label}
              </span>
            ))}
          </div>
          <ul className="space-y-0.5 text-[11px] leading-relaxed text-slate-600">
            {insight.causes.map((c) => (
              <li key={c.tag}>
                <span className="font-semibold text-amber-800">{c.label}:</span> {c.desc}
              </li>
            ))}
          </ul>
        </div>
      )}

      {insight.actions.length > 0 && (
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            Hành động đề xuất
          </p>
          <ol className="mt-1 list-decimal space-y-0.5 pl-4 text-xs leading-relaxed text-slate-700">
            {insight.actions.map((a, i) => (
              <li key={i}>{a}</li>
            ))}
          </ol>
        </div>
      )}

      {insight.caveat && (
        <p className="rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-1.5 text-[11px] leading-relaxed text-amber-800">
          ⚠️ Không được suy diễn: {insight.caveat}
        </p>
      )}

      <ModelNotePanel modelId={modelId} datasetId={datasetId} />
    </div>
  );
}
