/** DB-backed results explorer (change results-db-frontend, spec: results-dashboard).
 *
 * Client component: model selector (from `models`) → dataset selector
 * (filtered to datasets that model ran) → run summary panel (from
 * precomputed `summaries`, never recomputed) → per-item lookup.
 * Compare mode renders ≥2 runs side by side on the same `dataset_id`.
 * No blob import: every number comes from /api/results/*.
 */

"use client";

import { useEffect, useMemo, useState } from "react";

interface ModelOpt {
  _id: string;
  display_name: string;
}

interface DatasetOpt {
  _id: string;
  benchmark: string;
  split: string;
  n: number;
}

interface RunOpt {
  _id: string;
  model_id: string;
  dataset_id: string;
  card_id: string;
  n: number;
  measurement_card_hash: string;
}

type Summary = Record<string, unknown>;

/** Cutover status (change results-db-frontend 4.1): the old /benchmark blob
 *  path stays the default render until its two snapshots are re-graded
 *  (KNOWN-1 MC-9 categories, KNOWN-2 MC-8 vbench — see
 *  code_benchmark/verify_results_db.py). This view is the DB-backed
 *  counterpart; both routes stay 200 with no shared read path. */
export const RESULTS_CUTOVER_NOTE =
  "Số DB recompute-clean từ CSV gốc; đường blob cũ (/benchmark) giữ nguyên đến khi 2 drift KNOWN được vá.";

function OverallLine({ summary }: { summary: Summary }) {
  const n = summary.n;
  const acc = summary.accuracy_rows as
    | Array<{ level: string; name: string; n: string; correct: string; accuracy: string }>
    | undefined;
  const reading = summary.reading_rows as
    | Array<{ dataset: string; n: string; em_count: string; em: string; char_f1: string }>
    | undefined;
  const server = summary.server_rows as
    | Array<{ domain: string; track: string; score: string; correct: string; total: string }>
    | undefined;
  if (acc) {
    const o = acc.find((r) => r.level === "overall");
    if (!o) return <p className="text-sm text-slate-500">Không có overall trong accuracy_rows.</p>;
    return (
      <div>
        <p className="text-2xl font-bold font-mono">
          {o.correct}/{o.n} = {o.accuracy}%
        </p>
        <p className="text-xs text-slate-500">overall · n={String(n)}</p>
        <details className="mt-2">
          <summary className="cursor-pointer text-sm font-semibold text-indigo-700">
            Per-category / per-subject ({acc.length - 1} dòng)
          </summary>
          <table className="mt-2 w-full text-xs font-mono">
            <thead>
              <tr className="text-left text-slate-500">
                <th className="pr-2">level</th>
                <th className="pr-2">name</th>
                <th className="pr-2">n</th>
                <th className="pr-2">correct</th>
                <th>acc</th>
              </tr>
            </thead>
            <tbody>
              {acc.map((r, i) => (
                <tr key={i} className="border-t border-slate-100">
                  <td className="pr-2">{r.level}</td>
                  <td className="pr-2">{r.name}</td>
                  <td className="pr-2">{r.n}</td>
                  <td className="pr-2">{r.correct}</td>
                  <td>{r.accuracy}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      </div>
    );
  }
  if (reading) {
    const all = reading.find((r) => r.dataset === "ALL") ?? reading[0];
    return (
      <div>
        <p className="text-2xl font-bold font-mono">
          EM {all.em}% · F1 {all.char_f1}
        </p>
        <p className="text-xs text-slate-500">
          {all.em_count}/{all.n} exact · n={String(n)}
        </p>
        <table className="mt-2 w-full text-xs font-mono">
          <thead>
            <tr className="text-left text-slate-500">
              <th className="pr-2">dataset</th>
              <th className="pr-2">n</th>
              <th className="pr-2">em</th>
              <th>char_f1</th>
            </tr>
          </thead>
          <tbody>
            {reading.map((r, i) => (
              <tr key={i} className="border-t border-slate-100">
                <td className="pr-2">{r.dataset}</td>
                <td className="pr-2">{r.n}</td>
                <td className="pr-2">{r.em}</td>
                <td>{r.char_f1}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }
  if (server) {
    return (
      <div>
        <p className="text-sm text-slate-500">server-side scores (vbench.ai) · n={String(n)}</p>
        <table className="mt-2 w-full text-xs font-mono">
          <thead>
            <tr className="text-left text-slate-500">
              <th className="pr-2">domain</th>
              <th className="pr-2">track</th>
              <th className="pr-2">score</th>
              <th>correct/total</th>
            </tr>
          </thead>
          <tbody>
            {server.map((r, i) => (
              <tr key={i} className="border-t border-slate-100">
                <td className="pr-2">{r.domain}</td>
                <td className="pr-2">{r.track}</td>
                <td className="pr-2">{r.score}</td>
                <td>
                  {r.correct}/{r.total}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }
  return <p className="text-sm text-slate-500">Run không gold local (test/withheld) · n={String(n)} — chấm server-side.</p>;
}

function RunPanel({
  run,
  summary,
  summaryError,
  itemId,
  setItemId,
  item,
  itemError,
  onLookup,
}: {
  run: RunOpt | null;
  summary: Summary | null;
  summaryError: string | null;
  itemId: string;
  setItemId: (v: string) => void;
  item: { collection: string; doc: Record<string, unknown> } | null;
  itemError: string | null;
  onLookup: () => void;
}) {
  if (!run) return <p className="text-sm text-slate-500">Chưa có run cho lựa chọn này.</p>;
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-2xs">
      <p className="font-mono text-xs text-slate-500">{run._id}</p>
      <p className="text-sm text-slate-600">
        card <span className="font-mono font-semibold">{run.card_id}</span> · n={run.n} · hash{" "}
        <span className="font-mono">{run.measurement_card_hash.slice(0, 12)}</span>
      </p>
      <div className="mt-3">
        {summaryError ? (
          <p className="text-sm text-red-600">summary: {summaryError}</p>
        ) : summary ? (
          <OverallLine summary={summary} />
        ) : (
          <p className="text-sm text-slate-500">Đang tải summary…</p>
        )}
      </div>
      <div className="mt-4 border-t border-slate-100 pt-3">
        <p className="text-sm font-semibold">Per-item lookup</p>
        <div className="mt-1 flex gap-2">
          <input
            value={itemId}
            onChange={(e) => setItemId(e.target.value)}
            placeholder="item_id (vd 54-0002, LG-0001, squad:12)"
            className="w-full rounded-lg border border-slate-200 px-2 py-1 font-mono text-xs"
          />
          <button
            onClick={onLookup}
            className="rounded-lg bg-indigo-600 px-3 py-1 text-xs font-semibold text-white hover:bg-indigo-500"
          >
            Tra
          </button>
        </div>
        {itemError && <p className="mt-1 text-xs text-red-600">{itemError}</p>}
        {item && (
          <dl className="mt-2 space-y-1 font-mono text-xs">
            <div className="flex gap-2">
              <dt className="text-slate-500">collection</dt>
              <dd>{item.collection}</dd>
            </div>
            {["item_id", "answer", "gold", "correct", "em", "f1", "prediction", "domain", "track"].map(
              (k) =>
                item.doc[k] !== undefined && (
                  <div className="flex gap-2" key={k}>
                    <dt className="text-slate-500">{k}</dt>
                    <dd className="break-all">{String(item.doc[k])}</dd>
                  </div>
                ),
            )}
            {typeof item.doc.raw_response === "string" && item.doc.raw_response && (
              <div>
                <dt className="text-slate-500">raw_response</dt>
                <dd className="break-all whitespace-pre-wrap rounded bg-slate-50 p-1">
                  {item.doc.raw_response.slice(0, 1200)}
                </dd>
              </div>
            )}
          </dl>
        )}
      </div>
    </div>
  );
}

export function ResultsExplorer() {
  const [models, setModels] = useState<ModelOpt[]>([]);
  const [datasets, setDatasets] = useState<DatasetOpt[]>([]);
  const [runs, setRuns] = useState<RunOpt[]>([]);
  const [model, setModel] = useState("");
  const [dataset, setDataset] = useState("");
  const [compareModel, setCompareModel] = useState("");
  const [summary, setSummary] = useState<Summary | null>(null);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [compareSummary, setCompareSummary] = useState<Summary | null>(null);
  const [itemId, setItemId] = useState("");
  const [item, setItem] = useState<{ collection: string; doc: Record<string, unknown> } | null>(null);
  const [itemError, setItemError] = useState<string | null>(null);
  const [bootError, setBootError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        const reqs = ["/api/results/models", "/api/results/datasets", "/api/results/runs"].map(
          async (url) => {
            const res = await fetch(url, { cache: "no-store" });
            if (!res.ok) throw new Error(`${url} -> ${res.status}: ${(await res.text()).slice(0, 200)}`);
            return res.json() as Promise<unknown>;
          },
        );
        const [m, d, r] = await Promise.all(reqs);
        if (!alive) return;
        const ms = (m as { models: ModelOpt[] }).models;
        const ds = (d as { datasets: DatasetOpt[] }).datasets;
        setModels(ms);
        setDatasets(ds);
        setRuns((r as { runs: RunOpt[] }).runs);
        const primary = ms.find((x) => x._id === "qwen3-5-9b-28k") ?? ms[0];
        if (primary) {
          setModel(primary._id);
          setCompareModel(ms.find((x) => x._id !== primary._id)?._id ?? "");
        }
      } catch (e) {
        if (alive) setBootError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  const modelDatasets = useMemo(() => {
    const ran: Record<string, true> = {};
    for (const r of runs) if (r.model_id === model) ran[r.dataset_id] = true;
    return datasets.filter((d) => ran[d._id]);
  }, [runs, datasets, model]);

  useEffect(() => {
    if (!modelDatasets.length) {
      setDataset("");
      return;
    }
    if (!modelDatasets.some((d) => d._id === dataset)) {
      const prefer = modelDatasets.find((d) => d._id === "vmlu-mqa-all-gold") ?? modelDatasets[0];
      setDataset(prefer._id);
    }
  }, [modelDatasets, dataset]);

  const run = useMemo(
    () => runs.find((r) => r.model_id === model && r.dataset_id === dataset) ?? null,
    [runs, model, dataset],
  );
  const compareRun = useMemo(
    () => runs.find((r) => r.model_id === compareModel && r.dataset_id === dataset) ?? null,
    [runs, compareModel, dataset],
  );

  async function lookup() {
    if (!run || !itemId.trim()) return;
    setItem(null);
    setItemError(null);
    try {
      const res = await fetch(
        `/api/results/items?run=${encodeURIComponent(run._id)}&item=${encodeURIComponent(itemId.trim())}`,
        { cache: "no-store" },
      );
      const body: unknown = await res.json();
      if (!res.ok) {
        const msg = body && typeof body === "object" && "error" in body ? String(body.error) : res.statusText;
        throw new Error(msg);
      }
      if (body && typeof body === "object" && "collection" in body && "item" in body) {
        const coll = body.collection;
        const doc = body.item;
        if (typeof coll === "string" && doc && typeof doc === "object")
          setItem({ collection: coll, doc: doc as Record<string, unknown> });
        else throw new Error("unexpected /api/results/items shape");
      } else throw new Error("unexpected /api/results/items shape");
    } catch (e) {
      setItemError(e instanceof Error ? e.message : String(e));
    }
  }

  useEffect(() => {
    setSummary(null);
    setSummaryError(null);
    setItemError(null);
    if (!run) return;
    let alive = true;
    void (async () => {
      try {
        const url = `/api/results/summary?run=${encodeURIComponent(run._id)}`;
        const res = await fetch(url, { cache: "no-store" });
        if (!res.ok) throw new Error(`${url} -> ${res.status}: ${(await res.text()).slice(0, 200)}`);
        const body = (await res.json()) as { summary: Summary };
        if (alive) setSummary(body.summary);
      } catch (e) {
        if (alive) setSummaryError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      alive = false;
    };
  }, [run]);

  useEffect(() => {
    setCompareSummary(null);
    if (!compareRun) return;
    let alive = true;
    void (async () => {
      try {
        const url = `/api/results/summary?run=${encodeURIComponent(compareRun._id)}`;
        const res = await fetch(url, { cache: "no-store" });
        if (!res.ok) throw new Error(`${url} -> ${res.status}`);
        const body = (await res.json()) as { summary: Summary };
        if (alive) setCompareSummary(body.summary);
      } catch {
        if (alive) setCompareSummary(null);
      }
    })();
    return () => {
      alive = false;
    };
  }, [compareRun]);


  if (bootError)
    return (
      <main className="mx-auto max-w-5xl px-6 py-16">
        <h1 className="text-xl font-bold">Không đọc được Mongo qua /api/results</h1>
        <pre className="mt-3 rounded-lg border bg-white p-4 font-mono text-xs whitespace-pre-wrap">{bootError}</pre>
        <p className="mt-2 text-sm text-slate-500">Mongo local `vmlu-mongo:27017` + db `vmlu` phải chạy (xem docs/results-backend.md).</p>
      </main>
    );

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-3 px-4 py-3 sm:px-6">
          <h1 className="font-bold">Results (DB-backed)</h1>
          <label className="flex items-center gap-1 text-xs">
            Model
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className="rounded-lg border border-slate-200 bg-white px-2 py-1 font-mono"
            >
              {models.map((m) => (
                <option key={m._id} value={m._id}>
                  {m.display_name ?? m._id} ({m._id})
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-1 text-xs">
            Dataset
            <select
              value={dataset}
              onChange={(e) => setDataset(e.target.value)}
              className="rounded-lg border border-slate-200 bg-white px-2 py-1 font-mono"
            >
              {modelDatasets.map((d) => (
                <option key={d._id} value={d._id}>
                  {d._id} (n={d.n})
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-1 text-xs">
            So sánh với
            <select
              value={compareModel}
              onChange={(e) => setCompareModel(e.target.value)}
              className="rounded-lg border border-slate-200 bg-white px-2 py-1 font-mono"
            >
              <option value="">— không —</option>
              {models
                .filter((m) => m._id !== model)
                .map((m) => (
                  <option key={m._id} value={m._id}>
                    {m._id}
                  </option>
                ))}
            </select>
          </label>
        </div>
        <p className="mx-auto max-w-6xl px-4 pb-2 text-xs text-slate-500 sm:px-6">{RESULTS_CUTOVER_NOTE}</p>
      </header>
      <main className="mx-auto grid max-w-6xl gap-4 px-4 py-4 sm:px-6 md:grid-cols-2">
        <section>
          <h2 className="mb-2 text-sm font-semibold text-slate-600">Chính — {model || "…"}</h2>
          <RunPanel
            run={run}
            summary={summary}
            summaryError={summaryError}
            itemId={itemId}
            setItemId={setItemId}
            item={item}
            itemError={itemError}
            onLookup={() => void lookup()}
          />
        </section>
        <section>
          <h2 className="mb-2 text-sm font-semibold text-slate-600">
            Đối chiếu — {compareModel || "chưa chọn"}
            {dataset && <span className="font-mono"> · {dataset}</span>}
          </h2>
          {compareModel ? (
            compareRun ? (
              <RunPanel
                run={compareRun}
                summary={compareSummary}
                summaryError={null}
                itemId={itemId}
                setItemId={setItemId}
                item={null}
                itemError={null}
                onLookup={() => void lookup()}
              />
            ) : (
              <p className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm">
                Model <span className="font-mono">{compareModel}</span> chưa chạy dataset{" "}
                <span className="font-mono">{dataset}</span> — không có gì để so.
              </p>
            )
          ) : (
            <p className="text-sm text-slate-500">Chọn model đối chiếu để render side-by-side cùng dataset_id.</p>
          )}
        </section>
      </main>
    </div>
  );
}
