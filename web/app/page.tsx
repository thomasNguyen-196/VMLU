import { loadBlob, BLOB_REGEN_HINT } from "@/lib/blob.ts";
import { ReviewApp } from "@/components/ReviewApp.tsx";

// The reviewer's data is per-machine file state; render at request time so a
// fresh export-blob is picked up on the next load.
export const dynamic = "force-dynamic";

export default async function Home() {
  let blob;
  try {
    blob = await loadBlob();
  } catch (e) {
    return <MissingBlob hint={e instanceof Error ? e.message : String(e)} />;
  }
  return <ReviewApp blob={blob} />;
}

function MissingBlob({ hint }: { hint: string }) {
  return (
    <main className="mx-auto flex min-h-dvh max-w-[640px] flex-col justify-center px-6 py-16">
      <h1 className="font-disp text-[26px] font-semibold">Chưa có dữ liệu để review</h1>
      <p className="mt-3 text-[14px] leading-relaxed text-ink-2">
        App đọc blob do Python dựng (nơi chạy toàn bộ kiểm tra join). Chưa tìm thấy nó hoặc nó không hợp lệ:
      </p>
      <pre className="mt-4 overflow-x-auto rounded-lg border border-hair bg-card p-4 font-mono text-[12.5px] whitespace-pre-wrap text-ink-2">
        {hint}
      </pre>
      <p className="mt-4 text-[13px] text-ink-2">Cách dựng lại từ thư mục gốc repo:</p>
      <pre className="mt-2 overflow-x-auto rounded-lg border border-flag/30 bg-flag-soft/50 p-4 font-mono text-[12.5px] whitespace-pre-wrap text-ink">
        {`.venv/bin/python code_benchmark/build_review_ui.py export-blob
${BLOB_REGEN_HINT}`}
      </pre>
    </main>
  );
}
