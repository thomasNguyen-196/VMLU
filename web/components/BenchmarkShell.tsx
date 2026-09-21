"use client";

import { useState } from "react";
import Link from "next/link";
import {
  BenchmarkDashboard,
  viewToDashboardData,
  type BenchmarkView,
} from "./BenchmarkDashboard.tsx";

/** Client shell: holds the active model + remounts the dashboard per model
 *  so tab/filter/modal state never leaks across models. Model switch is a
 *  full server round-trip (?model=) — the URL stays shareable. */
export function BenchmarkShell({ view }: { view: BenchmarkView }) {
  const [pending, setPending] = useState(false);
  const { data, questions } = viewToDashboardData(view);

  function onModelChange(id: string) {
    if (id === view.activeModel.id || pending) return;
    setPending(true);
    const url = id === "qwen3-5-9b-28k" ? "/benchmark" : `/benchmark?model=${encodeURIComponent(id)}`;
    window.location.assign(url);
  }

  return (
    <div>
      {pending && (
        <div className="sticky top-0 z-40 bg-indigo-600/90 text-white text-xs font-semibold text-center py-1.5">
          Đang tải số liệu model mới…
        </div>
      )}
      <div className="bg-white border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-2 flex items-center gap-2 text-xs text-slate-500">
          <Link href="/" className="font-semibold text-indigo-700 hover:underline">
            ← Review
          </Link>
          <span aria-hidden>·</span>
          <span>
            Model <span className="font-mono font-semibold text-slate-800">{view.activeModel.id}</span>
            {view.activeModel.quantization && (
              <span className="font-mono"> · {view.activeModel.quantization}</span>
            )}{" "}
            · {view.modelDatasets.length} datasets · số live từ Mongo
          </span>
        </div>
      </div>
      <BenchmarkDashboard
        key={view.activeModel.id}
        data={data}
        questions={questions}
        models={view.models}
        activeModelId={view.activeModel.id}
        onModelChange={onModelChange}
      />
    </div>
  );
}
