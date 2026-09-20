/** Contract tests for /api/results/* (change results-db-frontend).
 *
 * Offline: swaps the db module's adapter with an in-memory fake (no Mongo).
 * Run: `cd web && bun test lib/results-api.test.ts`
 */
import { describe, expect, test } from "bun:test";
import { __setDbForTest } from "./db.ts";
import { GET as modelsGET } from "../app/api/results/models/route.ts";
import { GET as datasetsGET } from "../app/api/results/datasets/route.ts";
import { GET as runsGET } from "../app/api/results/runs/route.ts";
import { GET as summaryGET } from "../app/api/results/summary/route.ts";
import { GET as itemsGET } from "../app/api/results/items/route.ts";

interface FakeStore {
  models: Array<{ _id: string }>;
  datasets: Array<{ _id: string }>;
  runs: Array<{ _id: string; model_id: string; dataset_id: string }>;
  summary: { _id: string; n: number };
  mc: Array<{ run_id: string; item_id: string }>;
}

function fakeDb(): FakeStore {
  return {
    models: [{ _id: "m1" }],
    datasets: [{ _id: "ds1" }],
    runs: [{ _id: "m1__ds1__MC-9", model_id: "m1", dataset_id: "ds1" }],
    summary: { _id: "m1__ds1__MC-9", n: 2 },
    mc: [{ run_id: "m1__ds1__MC-9", item_id: "28-0007" }],
  };
}

function fakeRequest(url: string): never {
  return new Request(url) as never;
}

function installFake(f: FakeStore) {
  const coll = (name: string) => {
    if (name === "models")
      return { find: () => ({ sort: () => ({ toArray: async () => f.models }) }) };
    if (name === "datasets")
      return { find: () => ({ sort: () => ({ toArray: async () => f.datasets }) }) };
    if (name === "runs")
      return {
        find: (q: Record<string, string>) => ({
          sort: () => ({
            toArray: async () =>
              f.runs.filter(
                (r) => (!q.model_id || r.model_id === q.model_id) && (!q.dataset_id || r.dataset_id === q.dataset_id),
              ),
          }),
        }),
      };
    if (name === "summaries") return { findOne: async () => f.summary };
    return {
      findOne: async (q: Record<string, string>) => {
        if (name !== "mc_items") return null;
        return f.mc.find((d) => d.run_id === q.run_id && d.item_id === q.item_id) ?? null;
      },
    };
  };
  __setDbForTest({ collection: coll } as never);
}

describe("results API", () => {
  test("models/datasets/runs return registry shapes", async () => {
    const f = fakeDb();
    installFake(f);
    try {
      const m = await modelsGET();
      expect(m.status).toBe(200);
      const mBody: unknown = await m.json();
      if (mBody && typeof mBody === "object" && "models" in mBody) {
        expect((mBody.models as unknown[]).length).toBe(1);
      } else {
        throw new Error("models route shape changed");
      }
      const d = await datasetsGET();
      const dBody: unknown = await d.json();
      if (dBody && typeof dBody === "object" && "datasets" in dBody) {
        expect((dBody.datasets as unknown[]).length).toBe(1);
      } else {
        throw new Error("datasets route shape changed");
      }
      const r = await runsGET(fakeRequest("http://x/api/results/runs?model=m1&dataset=ds1"));
      const rBody: unknown = await r.json();
      if (rBody && typeof rBody === "object" && "runs" in rBody) {
        expect((rBody.runs as unknown[]).length).toBe(1);
      } else {
        throw new Error("runs route shape changed");
      }
    } finally {
      __setDbForTest(null);
    }
  });

  test("summary/items validate params (400) and hit the fake store", async () => {
    const f = fakeDb();
    installFake(f);
    try {
      const bad1 = await summaryGET(fakeRequest("http://x/api/results/summary"));
      expect(bad1.status).toBe(400);
      const ok1 = await summaryGET(fakeRequest("http://x/api/results/summary?run=m1__ds1__MC-9"));
      expect(ok1.status).toBe(200);
      const bad2 = await itemsGET(fakeRequest("http://x/api/results/items?run=m1__ds1__MC-9"));
      expect(bad2.status).toBe(400);
      const ok2 = await itemsGET(
        fakeRequest("http://x/api/results/items?run=m1__ds1__MC-9&item=28-0007"),
      );
      expect(ok2.status).toBe(200);
      const okBody: unknown = await ok2.json();
      if (okBody && typeof okBody === "object" && "collection" in okBody) {
        expect(okBody.collection).toBe("mc_items");
      } else {
        throw new Error("items route shape changed");
      }
      const miss = await itemsGET(
        fakeRequest("http://x/api/results/items?run=m1__ds1__MC-9&item=nope"),
      );
      expect(miss.status).toBe(404);
    } finally {
      __setDbForTest(null);
    }
  });
});

