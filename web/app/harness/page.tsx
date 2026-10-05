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
import SiteNav from "@/components/SiteNav.tsx";
import ThemeToggle from "@/components/ThemeToggle.tsx";
import TocNav, { type TocItem } from "@/components/TocNav.tsx";

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
  // Mục lục: chỉ những section thực sự có dữ liệu mới xuất hiện, theo đúng thứ
  // tự render bên dưới — thêm/xóa section mà quên cập nhật ở đây là một chỗ
  // lệch, nên mọi id đều được khai báo một lần ở đúng thẻ <section> của nó.
  const toc: TocItem[] = [
    { id: "nhan-xet", label: "Nhận xét" },
    { id: "so-sanh", label: "So sánh trực tiếp" },
  ];
  if (block.breakdown?.length) toc.push({ id: "cat-nhom", label: "Chênh lệch theo nhóm" });
  if (block.arg_credit?.length) toc.push({ id: "diem-tung-phan", label: "Điểm từng phần" });
  for (const ds of DATASET_ORDER) {
    const rows = rowsForDataset(block, ds);
    if (rows.length) toc.push({ id: `tap-${ds}`, label: rows[0].dataset_label.split(" (")[0] });
  }
  toc.push({ id: "chi-phi", label: "Chi phí & kiểm định" });
  toc.push({ id: "toc-do", label: "Tốc độ & token" });
  if (block.secondary_metrics?.length) toc.push({ id: "metric-phu", label: "Metric phụ" });
  if (block.repeatability?.length) toc.push({ id: "lap-lai", label: "Lặp lại" });
  toc.push({ id: "thuat-ngu", label: "Thuật ngữ" });
  toc.push({ id: "gioi-han", label: "Giới hạn khi trích" });
  return (
    <>
    <SiteNav />
    <div className="mx-auto flex max-w-[1360px] items-start gap-6 px-6 py-12">
      <aside className="hidden w-52 shrink-0 self-stretch lg:block">
        <TocNav items={toc} />
      </aside>
      <main className="min-w-0 max-w-[1060px] flex-1">
      <details className="mb-6 rounded-lg border border-hair bg-card p-3 lg:hidden">
        <summary className="cursor-pointer text-[13px] font-semibold">Mục lục</summary>
        <ul className="mt-2 grid gap-1 sm:grid-cols-2">
          {toc.map((it) => (
            <li key={it.id}>
              <a href={`#${it.id}`} className="text-[12.5px] text-ink-2 underline-offset-2 hover:text-ink hover:underline">
                {it.label}
              </a>
            </li>
          ))}
        </ul>
      </details>
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

      <section id="nhan-xet" className="mt-6 scroll-mt-6 rounded-lg border border-hair bg-card p-5">
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

      <section id="so-sanh" className="mt-6 scroll-mt-6 rounded-lg border border-hair bg-card p-5">
        <h2 className="text-[16px] font-semibold">So sánh trực tiếp: không dùng harness ⟷ dùng harness</h2>
        <p className="mt-1 text-[12.5px] text-ink-2">
          Cùng một model và cùng một prompt; chỉ khác ở chỗ có đưa câu hỏi qua tiến trình agent của{" "}
          <code className="font-mono">{block.harness}</code> hay không. Cột bên phải là cấu hình scaffold
          sạch (trung tính × không công cụ), xếp theo từng model, trong mỗi model từ nặng đến nhẹ.
        </p>
        {[...new Set(block.insight.comparison.map((c) => c.model))].map((m) => {
          const mrows = block.insight.comparison.filter((c) => c.model === m);
          return (
            <div key={m} className="mt-4">
              <h3 className="text-[13.5px] font-semibold">
                {m}{" "}
                <span className="font-normal text-ink-2">— cùng model ở cả hai cột</span>
              </h3>
              <table className="mt-1.5 w-full border-collapse text-[13px]">
                <thead>
                  <tr className="border-b border-hair text-left text-ink-2">
                    <th className="py-1.5 pr-2 font-medium">Tập dữ liệu</th>
                    <th className="py-1.5 pr-2 font-medium">Thước đo</th>
                    <th className="py-1.5 pr-2 text-right font-medium tabular-nums">n</th>
                    <th className="py-1.5 pr-2 text-right font-medium tabular-nums">Không dùng harness</th>
                    <th className="py-1.5 pr-2 text-right font-medium tabular-nums">Dùng harness</th>
                    <th className="py-1.5 text-right font-medium tabular-nums">Δ</th>
                  </tr>
                </thead>
                <tbody>
                  {mrows.map((c) => (
                    <tr key={`${c.model}/${c.dataset}`} className="border-b border-hair/60 last:border-0">
                      <td className="py-1.5 pr-2">{c.dataset_label}</td>
                      <td className="py-1.5 pr-2">
                        <span
                          className="inline-block rounded-full border border-hair px-1.5 py-px font-mono text-[11px] text-ink-2"
                          title={
                            c.metric === "agreement"
                              ? "Không phải điểm: tỉ lệ agent cho giống hệt lời gọi trực tiếp"
                              : `Thước đo của tập này: ${c.metric}`
                          }
                        >
                          {c.metric}
                        </span>
                      </td>
                      <td className="py-1.5 pr-2 text-right font-mono tabular-nums">{c.n}</td>
                      <td className="py-1.5 pr-2 text-right font-mono tabular-nums">
                        {c.no_harness.toFixed(2)}%
                        {(c.metric === "accuracy" || c.metric === "EM") &&
                        typeof c.a_blanks === "number" &&
                        c.a_blanks > 0 ? (
                          <span className="block text-[11px] font-normal text-ink-2">
                            trống {c.a_blanks}
                          </span>
                        ) : null}
                      </td>
                      <td className="py-1.5 pr-2 text-right font-mono font-semibold tabular-nums">
                        {c.with_harness.toFixed(2)}%
                        {(c.metric === "accuracy" || c.metric === "EM") &&
                        typeof c.b_blanks === "number" &&
                        c.b_blanks > 0 ? (
                          <span className="block text-[11px] font-normal text-ink-2">
                            trống {c.b_blanks}
                          </span>
                        ) : null}
                      </td>
                      <td className="py-1.5 text-right font-mono tabular-nums">
                        <span
                          className={
                            c.delta < 0
                              ? "inline-block min-w-[68px] rounded-full bg-flag-soft/70 px-2 py-px text-center text-flag"
                              : "inline-block min-w-[68px] rounded-full border border-hair px-2 py-px text-center"
                          }
                        >
                          {c.delta >= 0 ? "+" : ""}
                          {c.delta.toFixed(2)}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        })}
        <p className="mt-2 text-[12.5px] text-ink-2">
          Mỗi dòng là so trong <strong>một model</strong>: cùng model ở cả hai cột, chỉ khác
          việc câu hỏi có đi qua tiến trình agent hay không. Dấu của Δ không cố định giữa các
          model — đó là kết quả của phép so, không phải tiêu chí xếp hạng.{" "}
          {block.insight.comparison.some((c) => c.metric === "agreement") && (
            <>
              Dòng <span className="font-mono">agreement</span> KHÔNG phải điểm: đó là tỉ lệ câu
              trả lời mà agent cho <em>giống hệt</em> lời gọi trực tiếp trên cùng câu hỏi, nên nó
              đo mức agent làm đổi đáp án chứ không đo chất lượng — V-Bench chấm điểm ở máy chủ, ta
              không có vàng cục bộ.
            </>
          )}
        </p>
      </section>

      {block.breakdown?.length ? (
        <details id="cat-nhom" className="mt-6 scroll-mt-6 rounded-lg border border-hair bg-card px-5 py-3">
          <summary className="cursor-pointer text-[16px] font-semibold">
            Chênh lệch theo nhóm — cùng một phép so, cắt theo từng nhóm câu hỏi
          </summary>
          <p className="mt-1 text-[12.5px] text-ink-2">
            Mỗi dòng vẫn là so ghép cặp trong <strong>cùng model</strong>, chỉ thu hẹp xuống một
            nhóm (domain V-Bench, dạng câu reading). Nhóm nhỏ giữ nguyên CI rộng của nó — khoảng
            tin cậy nói thay cho việc giấu đi.
          </p>
          {block.breakdown.map((d) => (
            <div key={`${d.arm_slug}/${d.dataset}`} className="mt-4">
              <h3 className="text-[13.5px] font-semibold">
                {d.model} · {d.dataset_label}{" "}
                <span className="font-normal text-ink-2">— {d.label}</span>
              </h3>
              <table className="mt-1.5 w-full border-collapse text-[13px]">
                <thead>
                  <tr className="border-b border-hair text-left text-ink-2">
                    <th className="py-1.5 pr-2 font-medium">Nhóm</th>
                    <th className="py-1.5 pr-2 text-right font-medium tabular-nums">n</th>
                    <th className="py-1.5 pr-2 text-right font-medium tabular-nums">Không dùng</th>
                    <th className="py-1.5 pr-2 text-right font-medium tabular-nums">Dùng</th>
                    <th className="py-1.5 pr-2 text-right font-medium tabular-nums">Δ</th>
                    <th className="py-1.5 text-right font-medium tabular-nums">CI 95%</th>
                  </tr>
                </thead>
                <tbody>
                  {[...d.groups]
                    .sort((a, b) => a.delta - b.delta)
                    .map((g) => (
                      <tr key={g.group} className="border-b border-hair/60 last:border-0">
                        <td className="py-1.5 pr-2 font-mono text-[12.5px]">{g.group}</td>
                        <td className="py-1.5 pr-2 text-right font-mono tabular-nums">{g.n}</td>
                        <td className="py-1.5 pr-2 text-right font-mono tabular-nums">
                          {g.arm_a.toFixed(2)}%
                        </td>
                        <td className="py-1.5 pr-2 text-right font-mono font-semibold tabular-nums">
                          {g.arm_b.toFixed(2)}%
                        </td>
                        <td className="py-1.5 pr-2 text-right font-mono tabular-nums">
                          <span
                            className={
                              g.delta < 0
                                ? "inline-block min-w-[68px] rounded-full bg-flag-soft/70 px-2 py-px text-center text-flag"
                                : "inline-block min-w-[68px] rounded-full border border-hair px-2 py-px text-center"
                            }
                          >
                            {g.delta >= 0 ? "+" : ""}
                            {g.delta.toFixed(2)}
                          </span>
                        </td>
                        <td className="py-1.5 text-right font-mono text-[12px] text-ink-2 tabular-nums">
                          {g.ci95_low.toFixed(2)}..{g.ci95_high.toFixed(2)}
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          ))}
        </details>
      ) : null}

      {block.arg_credit?.length ? (
        <details id="diem-tung-phan" className="mt-6 scroll-mt-6 rounded-lg border border-hair bg-card px-5 py-3">
          <summary className="cursor-pointer text-[16px] font-semibold">
            Điểm từng phần — tham số đúng bao nhiêu, không chỉ gọi được hay không
          </summary>
          <p className="mt-1 text-[12.5px] text-ink-2">
            Validity 0/1 gộp hai lỗi khác nhau (không ra được call nào vs ra call nhưng sai tham
            số). Ở đây chấm từng tham số ở đúng tầng mà cổng pipeline kiểm tra:{" "}
            <code>required_fill</code> = tham số bắt buộc điền đúng / tham số bắt buộc (trên các
            câu đã ra được call), <code>precision</code> = tham số hợp lệ / tham số đã đưa ra.
            Câu không ra call không đóng góp vào tỉ lệ nào và được đếm riêng ở cột cuối.
          </p>
          <table className="mt-2 w-full border-collapse text-[13px]">
            <thead>
              <tr className="border-b border-hair text-left text-ink-2">
                <th className="py-1.5 pr-2 font-medium">Arm</th>
                <th className="py-1.5 pr-2 text-right font-medium tabular-nums">n</th>
                <th className="py-1.5 pr-2 text-right font-medium tabular-nums">Ra được call</th>
                <th className="py-1.5 pr-2 text-right font-medium tabular-nums">Bắt buộc điền đúng</th>
                <th className="py-1.5 pr-2 text-right font-medium tabular-nums">Precision tham số</th>
                <th className="py-1.5 text-right font-medium tabular-nums">Không ra call</th>
              </tr>
            </thead>
            <tbody>
              {block.arg_credit.map((a) => (
                <tr key={a.arm_slug} className="border-b border-hair/60 last:border-0">
                  <td className="py-1.5 pr-2">
                    <span className="font-mono text-[12.5px]">{a.arm}</span>{" "}
                    <span className="text-ink-2">{a.model}</span>
                  </td>
                  <td className="py-1.5 pr-2 text-right font-mono tabular-nums">{a.n_items}</td>
                  <td className="py-1.5 pr-2 text-right font-mono tabular-nums">{a.n_attempted}</td>
                  <td className="py-1.5 pr-2 text-right font-mono tabular-nums">
                    <span className="font-semibold">{a.required_fill_rate.toFixed(2)}%</span>{" "}
                    <span className="text-[11.5px] text-ink-2">
                      ({a.n_required_ok}/{a.n_required_slots})
                    </span>
                  </td>
                  <td className="py-1.5 pr-2 text-right font-mono tabular-nums">
                    <span className="font-semibold">{a.arg_precision.toFixed(2)}%</span>{" "}
                    <span className="text-[11.5px] text-ink-2">
                      ({a.n_supplied_ok}/{a.n_supplied})
                    </span>
                  </td>
                  <td className="py-1.5 text-right font-mono tabular-nums">{a.n_unparseable}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      ) : null}

      {DATASET_ORDER.map((ds) => {
        const rows = rowsForDataset(block, ds);
        if (!rows.length) return null;
        // Một tập có thể chứa hai model — mỗi model là một phép so riêng, nên mỗi
        // model có tiêu đề và mốc arm A của chính nó. Trộn chung một bảng sẽ làm
        // con số arm A của model này đội đầu bảng của model kia.
        const models = [...new Set(rows.map((r) => r.model ?? ""))];
        return (
          <section key={ds} id={`tap-${ds}`} className="mt-8 scroll-mt-6">
            <h2 className="text-[16px] font-semibold">{rows[0].dataset_label}</h2>
            {models.map((m) => {
              const mrows = rows.filter((r) => (r.model ?? "") === m);
              const base = mrows.find((r) => r.role === "baseline");
              return (
                <div key={m} className="mt-2.5">
                  <h3 className="text-[13.5px] font-semibold">
                    {m || "—"}
                    {base ? (
                      <span className="ml-2 text-[12.5px] font-normal text-ink-2">
                        arm A = {base.arm_b.toFixed(2)}%
                      </span>
                    ) : null}
                  </h3>
                  <table className="mt-1.5 w-full border-collapse text-[13px]">
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
                {mrows.map((r) => (
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
                </div>
              );
            })}
          </section>
        );
      })}

      <section id="chi-phi" className="mt-10 scroll-mt-6">
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

      <section id="toc-do" className="mt-10 scroll-mt-6">
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
        <section id="metric-phu" className="mt-10 scroll-mt-6">
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
        <section id="lap-lai" className="mt-10 scroll-mt-6">
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

      <section id="thuat-ngu" className="mt-10 scroll-mt-6">
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

      <section id="gioi-han" className="mt-10 scroll-mt-6">
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
          (bảng điểm chính) · mỗi dataset ở đây cũng có một dòng tương ứng trong tab cùng
          dataset của /benchmark · bản offline:{" "}
          <code className="font-mono">harness_report.html</code>
        </p>
      </section>
      </main>
    </div>
    </>
  );
}
