"use client";

/** The one line that stops /benchmark and /harness reading as separate
 *  products. Sits inside each dataset tab's `DatasetStrip`, directly under the
 *  headline number, and answers "what does the agent in the path cost on THIS
 *  dataset?" without a page transition.
 *
 *  Why it lives here and not on a separate page: the harness arms are the same
 *  measurement of the same cells, cut along a second axis. Putting the delta
 *  beside the direct number is what makes that visible; a link to a study page
 *  only asserts it.
 *
 *  Two honesty rules, both from `lib/harness-contrast.ts`:
 *  · arm A is labelled the STUDY'S OWN direct arm. It is not claimed to be the
 *    Mongo run above, because no run id proves that yet.
 *  · no arms → say so. An absent arm is not an arm scoring zero.
 */
import Link from "next/link";
import type { HarnessContrastVM } from "@/lib/harness-contrast.ts";

function fmt(n: number): string {
  return Number.isInteger(n) ? String(n) : n.toFixed(2);
}

export function HarnessContrast({
  contrast,
  datasetName,
}: {
  contrast: HarnessContrastVM | null;
  datasetName: string;
}) {
  // No harness arm for this cell. Say it — an empty strip would read as "no
  // effect measured", which is the opposite of "not measured".
  if (!contrast || contrast.arms.length === 0) {
    return (
      <p className="text-[11px] leading-relaxed text-slate-500 border-t border-slate-100 pt-2 mt-2">
        Chưa có arm <span className="font-mono">omp</span> cho {datasetName} — nghiên cứu
        harness chưa đo cell này.{" "}
        <Link href="/harness" className="underline underline-offset-2 hover:text-slate-800">
          Xem các cell đã đo
        </Link>
        .
      </p>
    );
  }

  // vbench_mc and vbench_agentic share a benchmark dataset but are different
  // metrics on different subsets. Blend them and the strip states a falsehood.
  const metrics = [...new Set(contrast.arms.map((a) => a.metric))];
  const mixed = metrics.length > 1;

  return (
    <div className="border-t border-slate-100 pt-2 mt-2 space-y-1.5">
      <p className="text-[11px] leading-relaxed text-slate-600">
        <span className="font-bold text-slate-800">Đo qua agent (omp): </span>
        cùng model, cùng câu, chỉ khác đường truy xuất câu trả lời
        {mixed ? " — lưu ý cell này gộp 2 metric khác nhau, xem từng dòng" : ""}.
      </p>
      <ul className="space-y-1">
        {contrast.arms.map((a) => (
          <li key={a.arm} className="text-[11px] leading-relaxed flex flex-wrap items-baseline gap-x-2">
            <span className="font-mono font-semibold text-slate-900">{a.arm}</span>
            <span className="font-mono text-slate-700">
              {a.metric} {fmt(a.armB)}
            </span>
            <span
              className={`font-mono font-semibold ${
                a.delta < 0 ? "text-rose-700" : a.delta > 0 ? "text-emerald-700" : "text-slate-600"
              }`}
            >
              ({a.delta > 0 ? "+" : ""}
              {fmt(a.delta)} so với arm A {fmt(a.armA)} của chính nghiên cứu này)
            </span>
            <span className="font-mono text-slate-400">
              CI95 [{fmt(a.ci95Low)}, {fmt(a.ci95High)}] · McNemar p={a.mcnemarP} · n={a.n}
            </span>
            {a.card && <span className="font-mono text-slate-500">card {a.card}</span>}
          </li>
        ))}
      </ul>
      <p className="text-[10.5px] leading-relaxed text-slate-400">
        arm A là đường gọi trực tiếp của chính nghiên cứu harness, không phải run Mongo ở trên
        — chưa có run id chứng minh hai bên là cùng một lần chạy.{" "}
        <Link href={contrast.arms[0].href} className="underline underline-offset-2 hover:text-slate-700">
          Mở {contrast.datasetLabel.split(" (")[0]} trong /harness
        </Link>
      </p>
    </div>
  );
}