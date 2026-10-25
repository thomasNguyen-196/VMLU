import type { ExpansionCell, ExpansionDataset, ExpansionProfile } from "@/lib/vi-multimodel-expansion.ts";

function fmtInt(value: number) {
  return value.toLocaleString("vi-VN");
}

function fmtPct(value: number | null | undefined, digits = 1) {
  return typeof value === "number" ? `${value.toFixed(digits)}%` : "—";
}

function CellValue({ cell }: { cell: ExpansionCell }) {
  if (cell.status === "scored") {
    return (
      <details className="group">
        <summary className="cursor-pointer list-none text-right font-mono tabular-nums marker:hidden">
          {fmtPct(cell.accuracy, 2)}
          <span className="ml-1 text-[10px] text-ink-3" aria-hidden="true">⌄</span>
        </summary>
        <div className="absolute z-20 mt-1 min-w-52 rounded-lg border border-hair bg-card p-3 text-left text-[11.5px] leading-relaxed shadow-lg">
          <div>Đúng: {cell.correct === undefined ? "—" : fmtInt(cell.correct)}</div>
          <div>n = {fmtInt(cell.completed_n)} / {fmtInt(cell.expected_n)}</div>
          <div>CI95 Wilson: {cell.accuracy_ci95 ? `${fmtPct(cell.accuracy_ci95[0], 2)}–${fmtPct(cell.accuracy_ci95[1], 2)}` : "—"}</div>
          <div>Không parse được: {fmtInt(cell.expected_n - (cell.parse_valid_n ?? cell.expected_n))}</div>
          <div>Bị cắt output: {fmtInt(cell.truncated_n ?? 0)}</div>
          <div className="mt-1 border-t border-hair pt-1 text-ink-3">{cell.card_id ?? "measurement card"}</div>
        </div>
      </details>
    );
  }

  if (cell.status === "awaiting_server_grade") {
    return (
      <details className="group">
        <summary className="cursor-pointer list-none text-right marker:hidden">
          <span className="block text-[11px] font-medium text-ink-2">chờ server chấm</span>
          <span className="mt-0.5 block font-mono text-[10.5px] text-ink-3">
            parse {cell.parse_valid_n === null || cell.parse_valid_n === undefined ? "—" : `${fmtInt(cell.parse_valid_n)}/${fmtInt(cell.expected_n)}`}
          </span>
        </summary>
        <div className="absolute z-20 mt-1 min-w-52 rounded-lg border border-hair bg-card p-3 text-left text-[11.5px] leading-relaxed shadow-lg">
          <div>Local gold: không có</div>
          <div>Output parse hợp lệ: {cell.parse_valid_n === null || cell.parse_valid_n === undefined ? "chưa tổng hợp" : `${fmtInt(cell.parse_valid_n)} / ${fmtInt(cell.expected_n)} (${fmtPct(cell.parse_valid_pct, 2)})`}</div>
          <div>Request hoàn tất: {fmtInt(cell.completed_n)} / {fmtInt(cell.expected_n)}</div>
          <div>Request lỗi cuối: {fmtInt(cell.request_error_n)}</div>
          <div>Truncation: {fmtInt(cell.truncated_n ?? 0)}</div>
          <div className="mt-1 border-t border-hair pt-1 text-ink-3">{cell.card_id ?? "measurement card"}</div>
        </div>
      </details>
    );
  }

  if (cell.status === "running") {
    return (
      <span className="font-mono tabular-nums text-ink-2" title="Đang chạy; lỗi transport không tính là đáp án sai">
        <span className="block">đang chạy {fmtInt(cell.completed_n)}/{fmtInt(cell.expected_n)}</span>
        {cell.request_error_n > 0 ? <span className="mt-0.5 block text-[10px] text-flag">lỗi kỹ thuật {fmtInt(cell.request_error_n)} · chờ resume</span> : null}
      </span>
    );
  }
  if (cell.status === "pending_score") {
    return (
      <span className="text-ink-2" title="Đủ request cho split này; đợi tổng hợp score sau khi phase xong">
        chờ tổng hợp
        <span className="mt-0.5 block font-mono text-[10.5px] text-ink-3">
          {fmtInt(cell.completed_n)}/{fmtInt(cell.expected_n)}
        </span>
      </span>
    );
  }
  if (cell.status === "paused") {
    return <span className="text-flag" title="Phase tạm dừng, cần kiểm tra ledger">cần xử lý</span>;
  }
  if (cell.status === "awaiting_user_review") {
    return <span className="text-ink-3" title="Qwen chờ người dùng duyệt kết quả Go">chờ duyệt</span>;
  }
  return <span className="text-ink-3" title="Chưa xếp hàng">xếp hàng</span>;
}

export function ViMultimodelExpansionMatrix({
  profiles,
  datasets,
  cells,
}: {
  profiles: ExpansionProfile[];
  datasets: ExpansionDataset[];
  cells: ExpansionCell[];
}) {
  const cellByKey = new Map<string, ExpansionCell>(
    cells.map((cell): [string, ExpansionCell] => [`${cell.profile_id}\u0000${cell.dataset_id}`, cell]),
  );
  return (
    <div className="overflow-x-auto rounded-xl border border-hair bg-card">
      <table className="w-full min-w-[980px] border-collapse text-[12px]">
        <caption className="sr-only">Ma trận điểm main protocol v2 theo model và tập benchmark tiếng Việt.</caption>
        <thead>
          <tr className="border-b border-hair bg-paper text-left text-ink-2">
            <th scope="col" className="sticky left-0 z-10 min-w-52 border-r border-hair bg-paper px-3 py-3 font-semibold">Model</th>
            {datasets.map((dataset) => (
              <th key={dataset.id} scope="col" className="min-w-40 px-3 py-3 text-right font-semibold">
                <span className="block text-ink">{dataset.label}</span>
                <span className="mt-0.5 block text-[10px] font-normal text-ink-3">{fmtInt(dataset.n)} câu · {dataset.short_label}</span>
                <span className="mt-0.5 block text-[10px] font-normal text-ink-3">
                  {dataset.metric === "accuracy" ? "accuracy · local gold" : "server score · gold giữ lại"}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {profiles.map((profile) => (
            <tr key={profile.id} className="border-b border-hair/70 last:border-0">
              <th scope="row" className="sticky left-0 z-10 border-r border-hair bg-card px-3 py-3 text-left font-medium">
                <span className="block text-ink">{profile.display_name}</span>
                <span className="block text-[10.5px] font-normal text-ink-3">{profile.provider} · {profile.status === "awaiting_user_review" ? "chờ duyệt" : profile.status}</span>
                <span className="mt-0.5 block break-all font-mono text-[9.5px] font-normal text-ink-3">{profile.id}</span>
              </th>
              {datasets.map((dataset) => {
                const cell = cellByKey.get(`${profile.id}\u0000${dataset.id}`);
                return (
                  <td key={dataset.id} className="relative px-3 py-3 text-right align-top">
                    {cell ? <CellValue cell={cell} /> : <span className="text-ink-3">—</span>}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
