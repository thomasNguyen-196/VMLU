import type { ChangelogDoc, ChangelogItem, InlineSegment } from "@/lib/changelog.ts";
import { parseInline } from "@/lib/changelog.ts";
import SiteNav from "@/components/SiteNav.tsx";

function Inline({ text }: { text: string }) {
  return (
    <>
      {parseInline(text).map((segment: InlineSegment, index: number) =>
        segment.kind === "bold" ? (
          <strong key={index} className="font-semibold text-ink">{segment.value}</strong>
        ) : segment.kind === "code" ? (
          <code key={index} className="rounded bg-paper px-1 py-0.5 font-mono text-[0.92em] text-ink-2">{segment.value}</code>
        ) : (
          <span key={index}>{segment.value}</span>
        ),
      )}
    </>
  );
}

function Item({ item }: { item: ChangelogItem }) {
  return (
    <li className="flex gap-2.5 text-[12.5px] leading-relaxed text-ink-2">
      {item.category === "other" ? null : (
        <span className="mt-0.5 shrink-0 rounded border border-hair bg-paper px-1.5 py-0.5 font-mono text-[9.5px] uppercase tracking-wide text-ink-3">
          {item.category}
        </span>
      )}
      <span><Inline text={item.text} /></span>
    </li>
  );
}

export default function ChangelogPage({ doc }: { doc: ChangelogDoc }) {
  return (
    <>
      <SiteNav />
      <main className="mx-auto max-w-[1100px] px-4 py-8 sm:px-7">
        <header className="mb-8">
          <p className="font-mono text-[10.5px] text-ink-3">VMLU · MODEL BEHAVIOR</p>
          <h1 className="mt-1 font-disp text-[27px] font-semibold">{doc.title}</h1>
          <div className="mt-3 space-y-2 border-l-2 border-hair pl-4 text-[12px] leading-relaxed text-ink-2">
            {doc.intro.map((paragraph, index) => (
              <p key={index}><Inline text={paragraph} /></p>
            ))}
          </div>
        </header>
        <div className="space-y-8">
          {doc.entries.map((entry) => (
            <article key={entry.title} className="rounded-xl border border-hair bg-card p-5">
              <h2 className="font-disp text-[18px] font-semibold">{entry.title}</h2>
              {entry.meta.length ? (
                <div className="mt-2 space-y-1 text-[11.5px] leading-relaxed text-ink-3">
                  {entry.meta.map((line, index) => (
                    <p key={index}><Inline text={line} /></p>
                  ))}
                </div>
              ) : null}
              {entry.items.length ? (
                <ul className="mt-4 space-y-2.5">
                  {entry.items.map((item, index) => <Item key={index} item={item} />)}
                </ul>
              ) : null}
            </article>
          ))}
        </div>
        <p className="mt-8 text-[10.5px] leading-relaxed text-ink-3">
          Nguồn: <code>docs/model-behavior-changelog.md</code> — trang này đọc trực tiếp file mỗi request.
          Phân loại: model · provider · harness · data · ops.
        </p>
      </main>
    </>
  );
}
