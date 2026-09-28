/** /harness — the frozen harness-arm study (see web/lib/harness-block.ts).
 *
 * Server component: reads `web/public/benchmark-data.json`, validates the
 * `.harness` block and renders the ladder / cost / audit. No Mongo, no build
 * step — the block is written by `code_benchmark/build_dashboard_harness.py`
 * and the same numbers also render offline in `harness_report.html`.
 */
import { promises as fs } from "fs";
import path from "path";
import { HARNESS_BLOB_HINT, readHarnessBlock, rowsForDataset, type HarnessBlock } from "@/lib/harness-block.ts";
import ThemeToggle from "@/components/ThemeToggle.tsx";

export const dynamic = "force-dynamic";


/** Thuật ngữ chuyên ngành giữ nguyên tiếng Anh trong phần diễn giải, vì dịch
 *  sang tiếng Việt sẽ mất nghĩa kỹ thuật hoặc tạo một thuật ngữ không có nguồn.
 *  Ở đây mỗi thuật ngữ được định nghĩa đúng một lần. */
const GLOSSARY: { term: string; vi: string; def: string }[] = [
  {
    term: "harness / agent scaffold",
    vi: "khung chạy agent",
    def: "Toàn bộ những thứ được chèn vào giữa lời gọi HTTP thuần và câu trả lời của model: system prompt, định nghĩa công cụ, vòng lặp suy luận, quy ước định dạng đầu ra. Nghiên cứu này so sánh `omp` (một coding agent) với đường gọi trực tiếp, giữ nguyên model và prompt.",
  },
  {
    term: "elicitation path",
    vi: "đường truy xuất câu trả lời",
    def: "Cách duy nhất mà câu trả lời được lấy ra model. Ở đây chỉ có hai đường: gọi HTTP trực tiếp, hoặc gọi trong tiến trình agent. Mọi khác biệt quan sát được đều quy về biến này.",
  },
  {
    term: "scaffold leak",
    vi: "rò cấu hình",
    def: "Khi cấu hình cá nhân của máy đang chạy lọt vào điều kiện thí nghiệm. Ở đây `PI_CODING_AGENT_DIR` không chặn được `~/.omp/agent/APPEND_SYSTEM.md` của agent dir mặc định, nên mọi arm đều thừa hưởng quy tắc trả lời của máy.",
  },
  {
    term: "paired bootstrap / McNemar",
    vi: "khoảng tin cậy bootstrap ghép cặp / kiểm định McNemar",
    def: "Hai phép kiểm định dùng chung một câu hỏi: với mỗi câu hỏi, arm A và arm B có cho ra kết quả khác nhau không. Bootstrap ghép cặp cho khoảng tin cậy của mức chênh lệch; McNemar kiểm tra tính có hệ thống của sự khác biệt đó.",
  },
  {
    term: "noise floor",
    vi: "ngưỡng nhiễu",
    def: "Mức dao động của chính một điều kiện khi chạy lại nhiều lần với cùng tham số. Hiệu ứng nhỏ hơn ngưỡng này thì không phải là kết quả, dù trung bình có thể khác 0.",
  },
  {
    term: "schema validity",
    vi: "tính hợp lệ về cấu trúc",
    def: "Với bài function-calling: lời gọi hàm có khớp với định nghĩa hàm của chính câu hỏi đó hay không (đủ tham số bắt buộc, đúng giá trị trong `enum`, không có tham số bịa). Nói rõ khác với accuracy: hợp lệ về cấu trúc không bảo đảm gọi đúng hàm.",
  },
  {
    term: "temperature = 0",
    vi: "nhiệt độ lấy mẫu bằng 0",
    def: "Tham số lấy mẫu đầu ra ở chế độ tất định. Ngay cả vậy, kết quả vẫn dao động giữa các lần chạy — vì thứ tự thực thi, việc chọn công cụ và cách lập luận của agent đều có tính ngẫu nhiên riêng.",
  },
  {
    term: "prompt token / completion token",
    vi: "token đầu vào / token đầu ra",
    def: "Đơn vị đo độ dài theo tokenizer của model. `prompt token` tính cả những gì agent tự chèn vào (system prompt, định nghĩa công cụ); `completion token` là phần model sinh ra.",
  },
  {
    term: "overhead",
    vi: "chi phí phát sinh thêm",
    def: "Chênh lệch thời gian xử lý giữa hai đường trên cùng một câu hỏi và cùng `workers`. Nó gồm thời gian khởi tạo tiến trình, thời gian chờ công cụ, và mọi bước trung gian của agent.",
  },
  {
    term: "persona",
    vi: "vai trò / lề (persona)",
    def: "Lớp hướng dẫn phong cách trả lời mà agent nhận thêm, độc lập với nhiệm vụ. Trong nghiên cứu này có hai mức: system prompt trung tính và system prompt sẵn có của omp.",
  },
  {
    term: "guard",
    vi: "chốt chặn",
    def: "Kiểm tra bắt buộc chạy trước khi tốn tài nguyên, dừng ngay với thông báo nêu rõ nguyên nhân thay vì để lỗi lan xuống dữ liệu. Ví dụ: kiểm tra 1-token trước mỗi lần chạy để không ghi nhầm sự cố hạ tầng thành kết quả của model.",
  },
];

const DATASET_ORDER = ["reading400", "legal_mc", "legal_nli", "bidlqa_val", "vbench_agentic", "vbench_mc"];

async function load(): Promise<HarnessBlock> {
  const file = path.join(process.cwd(), "public", "benchmark-data.json");
  const raw = await fs.readFile(file, "utf-8");
  const block = readHarnessBlock(JSON.parse(raw));
  if (!block) throw new Error("benchmark-data.json chưa có khối .harness");
  return block;
}

export default async function HarnessPage() {
  let block: HarnessBlock;
  try {
    block = await load();
  } catch (e) {
    const hint = e instanceof Error ? e.message : String(e);
    return (
      <main className="mx-auto flex min-h-dvh max-w-[720px] flex-col justify-center px-6 py-16">
        <h1 className="text-[26px] font-semibold">Chưa có dữ liệu harness</h1>
        <p className="mt-3 text-[14px] leading-relaxed text-ink-2">
          Khối <code>.harness</code> của benchmark-data.json thiếu hoặc không hợp lệ: {hint}
        </p>
        <pre className="mt-4 overflow-x-auto rounded-lg border border-hair bg-card p-4 font-mono text-[12.5px] whitespace-pre-wrap text-ink-2">
          {HARNESS_BLOB_HINT}
        </pre>
      </main>
    );
  }

  const t = block.totals;
  return (
    <main className="mx-auto max-w-[1100px] px-6 py-12">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <h1 className="text-[24px] font-semibold">{block.benchmark_name}</h1>
        <ThemeToggle />
      </div>
      <p className="mt-2 text-[13px] text-ink-2">
        model <b>{block.model_id}</b> @ {block.endpoint} · harness <b>{block.harness}</b> · {block.condition} ·
        card {block.measurement_card} · hash{" "}
        <code className="font-mono text-[12px]">{block.measurement_card_hash.slice(0, 16)}…</code>
      </p>

      <div className="mt-6 rounded-lg border border-flag/40 bg-flag-soft/50 p-4 text-[13px] leading-relaxed">
        <b className="text-flag">⚠ Đọc MC-15…MC-21 cùng MC-22.</b> {block.leak.what}
        <br />
        <b>Bằng chứng:</b> {block.leak.evidence}
        <br />
        <b>Cách chặn:</b> {block.leak.fix} · <b>Guard:</b> {block.leak.guard}
      </div>

      <section className="mt-6 rounded-lg border border-hair bg-card p-5">
        <h2 className="text-[16px] font-semibold">So sánh trực tiếp: không dùng harness ⟷ dùng harness</h2>
        <p className="mt-1 text-[12.5px] text-ink-2">
          Cùng một model và cùng một prompt; chỉ khác ở chỗ có đưa câu hỏi qua tiến trình agent của{" "}
          <code className="font-mono">{block.harness}</code> hay không. Cột bên phải là cấu hình scaffold
          sạch (trung tính × không công cụ), theo thứ tự từ nặng đến nhẹ.
        </p>
        <table className="mt-2.5 w-full border-collapse text-[13px]">
          <thead>
            <tr className="border-b border-hair text-left text-ink-2">
              <th className="py-1.5 pr-2 font-medium">Tập dữ liệu</th>
              <th className="py-1.5 pr-2 font-medium">Tiêu chí</th>
              <th className="py-1.5 pr-2 font-medium">n</th>
              <th className="py-1.5 pr-2 font-medium">Không dùng harness</th>
              <th className="py-1.5 pr-2 font-medium">Dùng harness</th>
              <th className="py-1.5 font-medium">Chênh lệch</th>
            </tr>
          </thead>
          <tbody>
            {block.insight.comparison.map((c) => (
              <tr key={c.dataset} className="border-b border-hair/60">
                <td className="py-1.5 pr-2">{c.dataset_label}</td>
                <td className="py-1.5 pr-2 font-mono text-ink-2">{c.metric}</td>
                <td className="py-1.5 pr-2 font-mono">{c.n}</td>
                <td className="py-1.5 pr-2 font-mono">{c.no_harness.toFixed(2)}%</td>
                <td className="py-1.5 pr-2 font-mono font-semibold">{c.with_harness.toFixed(2)}%</td>
                <td className="py-1.5 font-mono">
                  <span className={c.delta < 0 ? "text-flag" : "text-ok"}>
                    {c.delta >= 0 ? "+" : ""}
                    {c.delta.toFixed(2)}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-2 text-[12.5px] text-ink-2">
          Ở mọi tập đã đo, đưa câu hỏi qua agent đều làm giảm điểm. Mức giảm nhỏ nhất (
          {block.insight.comparison[block.insight.comparison.length - 1]?.delta.toFixed(2)}) nằm trên
          tập lớn nhất, nên nó đáng tin hơn các con số trên tập nhỏ.
        </p>
      </section>

      <section className="mt-6 rounded-lg border border-hair bg-card p-5">
        <h2 className="text-[16px] font-semibold">Nhận xét — đọc kết quả này thành gì?</h2>
        <p className="mt-2 text-[14px] font-medium leading-relaxed">{block.insight.verdict}</p>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          {block.insight.claims.map((c) => (
            <div key={c.id} className="rounded-lg border border-hair p-4">
              <h3 className="text-[13.5px] font-semibold leading-snug">{c.title}</h3>
              <p className="mt-1.5 text-[12.5px] leading-relaxed text-ink-2">
                {c.body.split("**").map((chunk, i) =>
                  i % 2 === 1 ? (
                    <b key={i} className="text-ink">
                      {chunk}
                    </b>
                  ) : (
                    <span key={i}>{chunk}</span>
                  ),
                )}
              </p>
              <dl className="mt-2.5 flex flex-wrap gap-x-4 gap-y-1 border-t border-hair pt-2 text-[12px]">
                {c.evidence.map((e) => (
                  <div key={e.label} className="flex gap-1.5">
                    <dt className="text-ink-2">{e.label}</dt>
                    <dd className="font-mono font-semibold">{e.value}</dd>
                  </div>
                ))}
              </dl>
            </div>
          ))}
        </div>
        <p className="mt-3 text-[11.5px] text-ink-2">
          Mọi con số ở trên được builder nội suy từ artifact của chính các bảng dưới đây
          (<code>insight()</code> trong <code>build_dashboard_harness.py</code>) — không có số nào gõ tay,
          nên phần diễn giải không thể lệch với dữ liệu.
        </p>
      </section>

      {DATASET_ORDER.map((ds) => {
        const rows = rowsForDataset(block, ds);
        if (!rows.length) return null;
        const base = rows.find((r) => r.role === "baseline");
        return (
          <section key={ds} className="mt-8">
            <h2 className="text-[16px] font-semibold">
              {rows[0].dataset_label}
              {base ? <span className="ml-2 text-[13px] font-normal text-ink-2">arm A = {base.arm_b.toFixed(2)}%</span> : null}
            </h2>
            <table className="mt-2 w-full border-collapse text-[13px]">
              <thead>
                <tr className="border-b border-hair text-left text-ink-2">
                  <th className="py-1.5 pr-2 font-medium">Arm</th>
                  <th className="py-1.5 pr-2 font-medium">n</th>
                  <th className="py-1.5 pr-2 font-medium">char-F1</th>
                  <th className="py-1.5 pr-2 font-medium">Arm B</th>
                  <th className="py-1.5 pr-2 font-medium">Δ</th>
                  <th className="py-1.5 pr-2 font-medium">Server</th>
              <th className="py-1.5 pr-2 font-medium">CI 95%</th>
                  <th className="py-1.5 pr-2 font-medium">p</th>
                  <th className="py-1.5 font-medium">Card</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={`${r.arm}-${r.dataset}`} className="border-b border-hair/60">
                    <td className="py-1.5 pr-2">{r.label}</td>
                    <td className="py-1.5 pr-2 font-mono">{r.n}</td>
                    <td className="py-1.5 pr-2 font-mono">{r.char_f1 === null ? "—" : r.char_f1.toFixed(2)}</td>
                    <td className="py-1.5 pr-2 font-mono font-semibold">
                      {r.role === "baseline" ? "—" : `${r.arm_b.toFixed(2)}%`}
                    </td>
                    <td className="py-1.5 pr-2 font-mono">
                      {r.role === "baseline" ? (
                        "—"
                      ) : (
                        <span className={r.delta < 0 ? "text-flag" : "text-ok"}>
                          {r.delta >= 0 ? "+" : ""}
                          {r.delta.toFixed(2)}
                        </span>
                      )}
                    </td>
                    <td className="py-1.5 pr-2 font-mono">
                      {r.server_score === undefined ? (
                        <span className="text-ink-2">—</span>
                      ) : (
                        <span title={`${r.server_correct}/${r.server_total} (điểm server, khác validity)`}>
                          {r.server_score.toFixed(2)}%
                        </span>
                      )}
                    </td>
                    <td className="py-1.5 pr-2 font-mono text-ink-2">
                      {r.role === "baseline" ? "—" : `${r.ci95_low.toFixed(2)}..${r.ci95_high.toFixed(2)}`}
                    </td>
                    <td className="py-1.5 pr-2 font-mono text-ink-2">{r.mcnemar_p || "—"}</td>
                    <td className="py-1.5 font-mono text-ink-2">{r.card ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        );
      })}

      <section className="mt-10">
        <h2 className="text-[16px] font-semibold">Chi phí & kiểm định hiệu lực (gộp mọi tập)</h2>
        <table className="mt-2 w-full border-collapse text-[13px]">
          <thead>
            <tr className="border-b border-hair text-left text-ink-2">
              <th className="py-1.5 pr-2 font-medium">Arm</th>
              <th className="py-1.5 pr-2 font-medium">item</th>
              <th className="py-1.5 pr-2 font-medium">wall/item</th>
              <th className="py-1.5 pr-2 font-medium">completion tok</th>
              <th className="py-1.5 pr-2 font-medium">lỗi</th>
              <th className="py-1.5 pr-2 font-medium">dùng tool</th>
              <th className="py-1.5 pr-2 font-medium">gọi mạng</th>
              <th className="py-1.5 font-medium">trốn sandbox</th>
            </tr>
          </thead>
          <tbody>
            {block.cost.map((c) => (
              <tr key={c.arm} className="border-b border-hair/60">
                <td className="py-1.5 pr-2">{c.label}</td>
                <td className="py-1.5 pr-2 font-mono">{c.n}</td>
                <td className="py-1.5 pr-2 font-mono">{c.wall_s_per_item.toFixed(2)}s</td>
                <td className="py-1.5 pr-2 font-mono">{c.completion_tokens}</td>
                <td className="py-1.5 pr-2 font-mono">{c.failures}</td>
                <td className="py-1.5 pr-2 font-mono">{c.tool_use_items}</td>
                <td className="py-1.5 pr-2 font-mono">{c.net_attempt_items}</td>
                <td className="py-1.5 font-mono">{c.path_escape_items}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-2 text-[12.5px] text-ink-2">
          Tổng {t.items_harness} item harness · {t.failures} lỗi · {t.tool_use_items} item dùng tool ·{" "}
          {t.net_attempt_items} lần gọi mạng · {t.path_escape_items} lần trốn sandbox (không lần nào
          thành công).
        </p>
      </section>

      <section className="mt-10">
        <h2 className="text-[16px] font-semibold">
          Tốc độ &amp; token phát sinh — cặp trực tiếp <span className="font-normal text-ink-2">vs</span>{" "}
          cùng item trong omp
        </h2>
        <p className="mt-1 text-[12.5px] text-ink-2">
          Mỗi tập có hai dòng: <b>direct</b> là chính lời gọi HTTP của arm A, <b>omp</b> là cùng item đó
          đi qua agent. <code>overhead</code> là chênh lệch wall/item của cặp.
        </p>
        <table className="mt-2 w-full border-collapse text-[13px]">
          <thead>
            <tr className="border-b border-hair text-left text-ink-2">
              <th className="py-1.5 pr-2 font-medium">Arm</th>
              <th className="py-1.5 pr-2 font-medium">Bên</th>
              <th className="py-1.5 pr-2 font-medium">Tập</th>
              <th className="py-1.5 pr-2 font-medium">n</th>
              <th className="py-1.5 pr-2 font-medium">workers</th>
              <th className="py-1.5 pr-2 font-medium">wall p50</th>
              <th className="py-1.5 pr-2 font-medium">item/phút</th>
              <th className="py-1.5 pr-2 font-medium">prompt tok</th>
              <th className="py-1.5 pr-2 font-medium">completion tok</th>
              <th className="py-1.5 pr-2 font-medium">tổng tok</th>
              <th className="py-1.5 font-medium">overhead/item</th>
            </tr>
          </thead>
          <tbody>
            {block.speed.map((s, i) => (
              <tr
                key={`${s.arm}-${s.side}-${s.dataset}-${i}`}
                className={`border-b border-hair/60 ${s.side === "omp" ? "bg-flag-soft/25" : ""}`}
              >
                <td className="py-1.5 pr-2">
                  <span className="font-mono">{s.arm}</span>{" "}
                  <span className="text-ink-2">{s.label}</span>
                </td>
                <td className="py-1.5 pr-2 font-mono">
                  {s.side === "omp" ? "omp" : <span className="text-ink-2">direct</span>}
                </td>
                <td className="py-1.5 pr-2 font-mono text-ink-2">{s.dataset}</td>
                <td className="py-1.5 pr-2 font-mono">{s.n}</td>
                <td className="py-1.5 pr-2 font-mono text-ink-2">{s.workers}</td>
                <td className="py-1.5 pr-2 font-mono">{s.wall_p50_s}s</td>
                <td className="py-1.5 pr-2 font-mono">{s.items_per_min}</td>
                <td className="py-1.5 pr-2 font-mono">{s.prompt_tok_per_item}</td>
                <td className="py-1.5 pr-2 font-mono">{s.completion_tok_per_item}</td>
                <td className="py-1.5 pr-2 font-mono font-semibold">{s.total_tok_per_item}</td>
                <td className="py-1.5 font-mono">
                  {s.side === "direct" ? (
                    <span className="text-ink-2">— gốc</span>
                  ) : (
                    <span className="text-flag">+{s.overhead_s_per_item}s</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-2 text-[12.5px] text-ink-2">
          <b>Không dùng <code>input + cacheRead</code> làm kích thước request</b>: bộ đếm cache của
          gateway IEC là tích luỹ theo thời gian, làm MC-19 phình ~8×. Số ở đây lấy từ{" "}
          <code>capture_scaffold.py</code> (proxy localhost ghi đúng byte request) và từ token báo
          trong ledger. <code>prompt tok</code> của dòng omp <b>đã bao gồm</b> system prompt + tool
          schemas của scaffold — đó chính là phần phát sinh.
        </p>
      </section>

      {block.ladder.some((r) => r.server_score !== undefined) ? (
        <p className="mt-2 text-[12.5px] text-ink-2">
          Cột <b>Server</b> là <i>accuracy thật</i> từ vbench.ai — khác hẳn cột Arm B ở tập V-Bench,
          vốn chỉ là <i>schema validity</i> (call có khớp schema không). Ở function-calling hai thứ
          lệch nhau <b>gấp 3,4 lần</b> (validity −2,60đ nhưng accuracy −8,90đ): phần lớn lỗi là{" "}
          <b>gọi đúng hàm sai tham số</b>, không phải sinh JSON sai. Mẫu số là <b>1.000</b> (26 dòng
          invalid không nộp được tính sai).
        </p>
      ) : null}

      {block.secondary_metrics?.length ? (
        <section className="mt-10">
          <h2 className="text-[16px] font-semibold">
            Metric phụ — EM nguyên văn vs EM sau khi cắt vỏ
          </h2>
          <p className="mt-1 text-[12.5px] text-ink-2">
            <b>Không thay số chính.</b> Cùng một câu trả lời, chấm hai lần: nguyên văn (đúng cách
            arm A được chấm) và sau khi bóc vỏ (<code>**</code>, nhãn <code>Đáp án:</code>, block
            code, dòng hỏi lại). Chênh lệch = phần <i>đúng nội dung nhưng bị chấm 0</i>. Câu sai
            vẫn sai.
          </p>
          <table className="mt-2 w-full border-collapse text-[13px]">
            <thead>
              <tr className="border-b border-hair text-left text-ink-2">
                <th className="py-1.5 pr-2 font-medium">Arm</th>
                <th className="py-1.5 pr-2 font-medium">Tập</th>
                <th className="py-1.5 pr-2 font-medium">n</th>
                <th className="py-1.5 pr-2 font-medium">EM nguyên văn</th>
                <th className="py-1.5 pr-2 font-medium">EM sau cắt vỏ</th>
                <th className="py-1.5 font-medium">Giá của vỏ</th>
              </tr>
            </thead>
            <tbody>
              {block.secondary_metrics.map((m) => (
                <tr key={`${m.arm}-${m.dataset}`} className="border-b border-hair/60">
                  <td className="py-1.5 pr-2">{m.label}</td>
                  <td className="py-1.5 pr-2">{m.dataset_label}</td>
                  <td className="py-1.5 pr-2 font-mono">{m.n}</td>
                  <td className="py-1.5 pr-2 font-mono">{m.em_verbatim.toFixed(2)}%</td>
                  <td className="py-1.5 pr-2 font-mono font-semibold">
                    {m.em_stripped.toFixed(2)}%
                  </td>
                  <td
                    className={
                      m.wrapper_cost > 0.5
                        ? "py-1.5 font-mono text-flag"
                        : "py-1.5 font-mono text-ink-2"
                    }
                  >
                    {m.wrapper_cost >= 0 ? "+" : ""}
                    {m.wrapper_cost.toFixed(2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-[12.5px] text-ink-2">
            Arm sạch (H5) cắt vỏ được <b>+0,00</b> ở cả hai tập: câu trả lời của nó vốn đã trần, không
            vỏ. Toàn bộ chi phí vỏ nằm ở arm bị rò cấu hình — cơ chế MC-22, giờ có số.
          </p>
        </section>
      ) : null}

      {block.repeatability?.length ? (
        <section className="mt-10">
          <h2 className="text-[16px] font-semibold">Lặp lại — nhiễu chạy-đến-chạy là mức sàn của mọi kết luận</h2>
          <p className="mt-1 text-[12.5px] text-ink-2">
            Cùng một điều kiện, chạy lại nhiều lần. <code>spread</code> = độ biến thiên của chính ô đó
            ở <code>temperature 0</code> — <b>contrast nhỏ hơn số này thì không phải kết quả</b>.
            Không gộp khác <code>n</code> (100 item và 146 item là hai thí nghiệm khác nhau).
          </p>
          <table className="mt-2 w-full border-collapse text-[13px]">
            <thead>
              <tr className="border-b border-hair text-left text-ink-2">
                <th className="py-1.5 pr-2 font-medium">Ô</th>
                <th className="py-1.5 pr-2 font-medium">Tập</th>
                <th className="py-1.5 pr-2 font-medium">n</th>
                <th className="py-1.5 pr-2 font-medium">Lặp</th>
                <th className="py-1.5 pr-2 font-medium">Arm A</th>
                <th className="py-1.5 pr-2 font-medium">Arm B</th>
                <th className="py-1.5 pr-2 font-medium">Δ</th>
                <th className="py-1.5 pr-2 font-medium">CI 95%</th>
                <th className="py-1.5 pr-2 font-medium">TB ô</th>
                <th className="py-1.5 font-medium">Spread ô</th>
              </tr>
            </thead>
            <tbody>
              {block.repeatability.map((r) => (
                <tr
                  key={`${r.cell}-${r.dataset}-${r.n}-${r.repeat}`}
                  className="border-b border-hair/60"
                >
                  <td className="py-1.5 pr-2">
                    <span className="font-mono">{r.cell}</span>{" "}
                    <span className="text-ink-2">{r.label.replace(/ — lặp \d+$/, "")}</span>
                  </td>
                  <td className="py-1.5 pr-2 text-ink-2">{r.dataset}</td>
                  <td className="py-1.5 pr-2 font-mono">{r.n}</td>
                  <td className="py-1.5 pr-2 font-mono text-ink-2">r{r.repeat}</td>
                  <td className="py-1.5 pr-2 font-mono">{r.arm_a.toFixed(2)}</td>
                  <td className="py-1.5 pr-2 font-mono font-semibold">{r.arm_b.toFixed(2)}%</td>
                  <td className="py-1.5 pr-2 font-mono">
                    <span className={r.delta < 0 ? "text-flag" : "text-ok"}>
                      {r.delta >= 0 ? "+" : ""}
                      {r.delta.toFixed(2)}
                    </span>
                  </td>
                  <td className="py-1.5 pr-2 font-mono text-ink-2">
                    {r.ci95_low.toFixed(2)}..{r.ci95_high.toFixed(2)}
                  </td>
                  <td className="py-1.5 pr-2 font-mono">
                    {r.cell_mean === undefined ? (
                      <span className="text-ink-2">—</span>
                    ) : (
                      r.cell_mean.toFixed(2)
                    )}
                  </td>
                  <td
                    className={
                      r.cell_spread !== undefined && r.cell_spread > 2
                        ? "py-1.5 font-mono text-flag"
                        : "py-1.5 font-mono"
                    }
                  >
                    {r.cell_spread === undefined ? (
                      <span className="text-ink-2">1 lặp</span>
                    ) : (
                      `±${(r.cell_spread / 2).toFixed(2)}`
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}

      <section className="mt-10">
        <h2 className="text-[16px] font-semibold">Thuật ngữ</h2>
        <p className="mt-1 text-[12.5px] text-ink-2">
          Các thuật ngữ chuyên ngành được giữ nguyên tiếng Anh trong phần nhận xét và trong bảng biểu,
          vì cách dịch sang tiếng Việt sẽ hoặc mất nghĩa kỹ thuật, hoặc tạo ra một thuật ngữ không có
          nguồn. Mỗi thuật ngữ được định nghĩa đúng một lần tại đây.
        </p>
        <dl className="mt-3 space-y-3">
          {GLOSSARY.map((g) => (
            <div key={g.term} className="border-b border-hair/60 pb-2.5 last:border-b-0">
              <dt className="text-[13px]">
                <code className="font-mono font-semibold">{g.term}</code>
                <span className="ml-2 text-[12px] text-ink-2">— {g.vi}</span>
              </dt>
              <dd className="mt-0.5 text-[12.5px] leading-relaxed text-ink-2">{g.def}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="mt-10">
        <h2 className="text-[16px] font-semibold">Giới hạn phải nói khi trích</h2>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-[13px] leading-relaxed text-ink-2">
          {block.caveats.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
        <p className="mt-4 text-[12.5px] text-ink-2">
          Nguồn: {block.sources.report} · {block.sources.docs} · scorer {block.scorer}
        </p>
        <p className="mt-3 text-[12.5px] text-ink-2">
          <a className="underline" href="/benchmark">
            /benchmark
          </a>{" "}
          (bảng điểm chính) · bản offline: <code className="font-mono">harness_report.html</code>
        </p>
      </section>
    </main>
  );
}
