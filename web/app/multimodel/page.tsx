import type { Metadata } from "next";
import SiteNav from "@/components/SiteNav.tsx";
import { ViMultimodelMatrix } from "@/components/ViMultimodelMatrix.tsx";
import { getViMultimodelMatrix } from "@/lib/vi-multimodel.ts";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "So sánh model tiếng Việt",
  description: "Ma trận accuracy, EM và token-F1 theo nhóm bài của benchmark tiếng Việt.",
};

export default async function MultimodelPage() {
  const matrix = await getViMultimodelMatrix();
  return (
    <>
      <SiteNav />
      <main className="mx-auto max-w-[1500px] px-5 py-8 sm:px-8">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="font-disp text-[24px] font-semibold">Benchmark tiếng Việt đa model</h1>
            <p className="mt-1 text-[13px] text-ink-2">
              Protocol {matrix.protocol_id} · mỗi item chạy một lượt omp, tools tắt và system prompt tối giản.
            </p>
          </div>
        </div>

        <ul className="mt-4 grid gap-x-6 gap-y-1 pl-5 text-[12.5px] leading-relaxed text-ink-2 md:grid-cols-2">
          <li>Accuracy đo trắc nghiệm; EM và token-F1 đo câu trả lời đọc hiểu.</li>
          <li>Gold đọc hiểu dùng bộ 400 câu đã được người dùng chấm.</li>
          <li>Reasoning được phép; budget theo nhóm bài được ghi trong measurement card.</li>
          <li>Ô chưa chạy, thiếu summary hoặc mẫu chưa đủ không hiện thành điểm 0.</li>
        </ul>

        <section aria-label="Ma trận điểm" className="mt-5">
          <ViMultimodelMatrix matrix={matrix} />
        </section>

        <p className="mt-3 text-[11.5px] leading-relaxed text-ink-3">
          Mỗi ô có số câu và CI95 khi mở chi tiết. Các cột giữ metric riêng, không gộp thành một điểm chung.
        </p>
      </main>
    </>
  );
}
