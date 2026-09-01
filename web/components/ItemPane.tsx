"use client";

import { memo } from "react";
import type { ReviewItem } from "@/lib/types.ts";
import type { Position } from "@/lib/review-logic.ts";

/** Left pane: the reading instrument. Position meta row, question, the
 *  original passage (collapsible — reviewers read it once per passage, then
 *  fold), and the model answer (the thing under review) in mono on an amber
 *  field so it can never be mistaken for gold. */
function ItemPaneInner({
  it,
  context,
  answer,
  model,
  position,
  total,
  idx,
}: {
  it: ReviewItem;
  context: string;
  answer: string | null;
  model: string;
  position: Position;
  total: number;
  idx: number;
}) {
  return (
    <section aria-labelledby="q-head" className="rounded-[10px] border border-card-edge bg-card p-5 shadow-[var(--shadow)] sm:p-6">
      <div className="mb-3.5 flex flex-wrap items-center gap-2">
        <span className="font-disp text-[13px] font-semibold tabular-nums">
          {idx + 1}
          <span className="font-normal text-ink-3"> / {total}</span>
        </span>
        <span
          className={
            "rounded-full border px-2.5 py-[3px] text-[10px] font-semibold uppercase tracking-[.06em] " +
            (it.dataset === "squad" ? "border-[#B9D3E6] bg-[#EAF3FA] text-[#1D5C8A] dark:border-[#2C4A63] dark:bg-[#16222E] dark:text-[#7FBBE8]" : "border-[#DAC5EA] bg-[#F4ECF9] text-[#7A4A9E] dark:border-[#4A3358] dark:bg-[#211829] dark:text-[#BC92DB]")
          }
        >
          {it.dataset}
        </span>
        <span className="rounded-full border border-hair px-2.5 py-[3px] text-[10px] font-semibold uppercase tracking-[.06em] text-ink-2">{it.stratum}</span>
        <span className="rounded-full border border-hair px-2.5 py-[3px] text-[10px] font-semibold tracking-[.06em] text-ink-2">#{it.item_id}</span>
        <span className="ml-auto text-[11.5px] tabular-nums text-ink-3">
          đoạn {it.passage_key} · câu {position.within}/{position.of} của đoạn này
        </span>
      </div>

      <div className="mb-1.5 flex items-baseline gap-2.5">
        <span className="font-mono text-[11px] text-ink-3">Q</span>
        <h2 id="q-head" lang="vi" className="text-[17px] font-semibold leading-[1.5]">
          {it.question}
        </h2>
      </div>

      <details open className="mt-4 border-t border-hair pt-3">
        <summary className="flex cursor-pointer list-none items-center gap-2.5 text-[13px] font-semibold text-ink-2 [&::-webkit-details-marker]:hidden hover:text-ink">
          <span aria-hidden className="text-ink-3 transition-transform duration-150">▸</span>
          Ngữ cảnh — đoạn văn gốc
          {context && <span className="text-[11px] font-normal tabular-nums text-ink-3">· {context.length.toLocaleString("vi-VN")} ký tự</span>}
        </summary>
        <p lang="vi" className="mt-3 whitespace-pre-wrap text-[15.5px] leading-[1.78] break-words text-ink">
          {context || "(thiếu ngữ cảnh — chạy lại export-blob)"}
        </p>
      </details>

      <div
        className={
          "mt-4 rounded-lg border border-l-[3px] p-3.5 text-[13.5px] leading-[1.65] break-words whitespace-pre-wrap font-mono " +
          (answer === null
            ? "border-hair border-l-ink-3 bg-hair/25 text-ink-3"
            : "border-flag/25 border-l-flag bg-flag-soft/60 text-ink")
        }
      >
        <span className={"mb-1.5 block text-[10.5px] font-semibold uppercase tracking-[.1em] " + (answer === null ? "text-ink-3" : "text-flag")}>
          Câu trả lời của model · {model}
        </span>
        {answer === null ? "(model này không có đáp án cho câu hỏi — n/a)" : answer}
      </div>
    </section>
  );
}

export const ItemPane = memo(ItemPaneInner);
