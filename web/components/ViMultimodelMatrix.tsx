import { fmtInt, fmtPct } from "@/lib/format.ts";
import type { MultiModelCell, MultiModelMatrix } from "@/lib/vi-multimodel.ts";

function CellScore({ cell, reading }: { cell: MultiModelCell; reading: boolean }) {
  if (cell.status === "not_run") {
    return <span className="text-ink-3" title="Chưa có run chính cho ô này">—</span>;
  }
  if (cell.status === "ambiguous") {
    return <span className="text-flag" title="Có nhiều run chính; cần chọn run tường minh">trùng run</span>;
  }
  if (cell.status === "summary_missing") {
    return <span className="text-ink-3" title="Run đã nhập nhưng chưa có summary">chờ tổng hợp</span>;
  }
  if (cell.status === "incomplete") {
    return (
      <span className="text-ink-2" title="Mẫu chưa đủ; chưa hiện điểm">
        {fmtInt(cell.n)}/{fmtInt(cell.expected_n)}
      </span>
    );
  }

  const interval = (pair: [number, number] | null | undefined) =>
    pair ? fmtPct(pair[0], 2) + "–" + fmtPct(pair[1], 2) : "chưa tính";
  const detail = reading
    ? "EM CI95: " + interval(cell.em_ci95) + " · token-F1 CI95: " + interval(cell.token_f1_ci95)
    : "Accuracy CI95: " + interval(cell.accuracy_ci95);

  return (
    <details className="group">
      <summary className="cursor-pointer list-none text-right font-mono tabular-nums marker:hidden">
        {reading
          ? <><span>{fmtPct(cell.em, 2)}</span><span className="px-1 text-ink-3">/</span><span>{fmtPct(cell.token_f1, 2)}</span></>
          : fmtPct(cell.accuracy, 2)}
        <span className="ml-1 text-[10px] text-ink-3" aria-hidden="true">⌄</span>
      </summary>
      <div className="absolute z-20 mt-1 min-w-56 rounded-lg border border-hair bg-card p-3 text-left text-[11.5px] leading-relaxed shadow-lg">
        <div>n = {fmtInt(cell.n)} / {fmtInt(cell.expected_n)}</div>
        {cell.correct !== undefined ? <div>Đúng: {fmtInt(cell.correct)}</div> : null}
        {cell.em_count !== undefined ? <div>EM chính xác: {fmtInt(cell.em_count)}</div> : null}
        {cell.coverage_pct !== undefined ? <div>Coverage: {fmtPct(cell.coverage_pct, 1)}</div> : null}
        {cell.request_error_n !== undefined ? <div>Request lỗi cuối: {fmtInt(cell.request_error_n)}</div> : null}
        {cell.unparsed_n !== undefined ? <div>Không trích được đáp án: {fmtInt(cell.unparsed_n)}</div> : null}
        {cell.empty_answer_n !== undefined ? <div>Đáp án rỗng: {fmtInt(cell.empty_answer_n)}</div> : null}
        {cell.truncated_n !== undefined ? <div>Bị cắt do giới hạn output: {fmtInt(cell.truncated_n)}</div> : null}
        {cell.latency_s_p50 != null ? <div>Độ trễ p50: {cell.latency_s_p50.toFixed(2)} giây</div> : null}
        {cell.latency_s_p90 != null ? <div>Độ trễ p90: {cell.latency_s_p90.toFixed(2)} giây</div> : null}
        {cell.prompt_tokens_mean != null ? <div>Token prompt trung bình: {fmtInt(Math.round(cell.prompt_tokens_mean))}</div> : null}
        {cell.completion_tokens_mean != null ? <div>Token hoàn tất trung bình: {fmtInt(Math.round(cell.completion_tokens_mean))}</div> : null}
        <div>{detail}</div>
        {reading && cell.legacy_em !== undefined ? (
          <div className="mt-1 border-t border-hair pt-1 text-ink-2">
            Legacy trên đáp án cuối: EM {fmtPct(cell.legacy_em, 2)} · char-F1 {fmtPct(cell.legacy_char_f1, 2)}
          </div>
        ) : null}
        <div className="mt-1 border-t border-hair pt-1 text-ink-3">
          {cell.card_id} · {cell.run_id ?? "main run"}
        </div>
      </div>
    </details>
  );
}

export function ViMultimodelMatrix({ matrix }: { matrix: MultiModelMatrix }) {
  const cells = new Map(
    matrix.cells.map((cell) => [cell.profile_id + "\u0000" + cell.dataset_id, cell]),
  );
  return (
    <div className="overflow-x-auto rounded-xl border border-hair bg-card">
      <table className="w-full min-w-[1100px] border-collapse text-[12.5px]">
        <caption className="sr-only">
          So sánh bốn model trên sáu nhóm bài tiếng Việt trong protocol {matrix.protocol_id}.
        </caption>
        <thead>
          <tr className="border-b border-hair bg-paper text-left text-ink-2">
            <th scope="col" className="sticky left-0 z-10 min-w-56 border-r border-hair bg-paper px-3 py-3 font-semibold">
              Model
            </th>
            {matrix.datasets.map((dataset) => (
              <th key={dataset.id} scope="col" className="min-w-32 px-3 py-3 text-right font-semibold">
                <span className="block text-ink">{dataset.label}</span>
                <span className="mt-0.5 block text-[10.5px] font-normal">{dataset.n} câu · {dataset.shortLabel}</span>
                <span className="mt-0.5 block text-[10.5px] font-normal">
                  {dataset.metric === "accuracy" ? "accuracy" : "EM / token-F1"} · %
                </span>
              </th>
            ))}
            <th scope="col" className="min-w-24 px-3 py-3 text-right font-semibold">
              <span className="block text-ink">Truncation</span>
              <span className="mt-0.5 block text-[10.5px] font-normal">tổng số câu</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {matrix.profiles.map((profile) => (
            <tr key={profile.id} className="border-b border-hair/70 last:border-0">
              <th scope="row" className="sticky left-0 z-10 border-r border-hair bg-card px-3 py-3 text-left font-medium">
                <span className="block text-ink">{profile.display_name}</span>
                {profile.tier ? <span className="block text-[10.5px] font-normal text-ink-3">{profile.tier}</span> : null}
                <span className="mt-0.5 block break-all font-mono text-[9.5px] font-normal text-ink-3">
                  {profile.id}
                </span>
              </th>
              {matrix.datasets.map((dataset) => {
                const cell = cells.get(profile.id + "\u0000" + dataset.id);
                return (
                  <td key={dataset.id} className="relative px-3 py-3 text-right align-top">
                    {cell ? <CellScore cell={cell} reading={dataset.metric === "reading"} /> : "—"}
                  </td>
                );
              })}
              <td className="px-3 py-3 text-right font-mono tabular-nums">
                {matrix.datasets.every((dataset) => {
                  const cell = cells.get(profile.id + "\u0000" + dataset.id);
                  return cell?.status === "scored" && cell.truncated_n !== undefined;
                })
                  ? fmtInt(matrix.datasets.reduce((total, dataset) => {
                      const cell = cells.get(profile.id + "\u0000" + dataset.id);
                      return total + (cell?.truncated_n ?? 0);
                    }, 0))
                  : <span className="text-ink-3">—</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
