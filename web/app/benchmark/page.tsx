import fs from "node:fs";
import path from "node:path";
import { BenchmarkDashboard } from "@/components/BenchmarkDashboard.tsx";

export const dynamic = "force-dynamic";

export default function BenchmarkPage() {
  const dataPath = path.join(process.cwd(), "public", "benchmark-data.json");
  const questionsPath = path.join(process.cwd(), "public", "vmlu-full-questions.json");

  const data = JSON.parse(fs.readFileSync(dataPath, "utf-8"));
  const questions = JSON.parse(fs.readFileSync(questionsPath, "utf-8"));

  return <BenchmarkDashboard data={data} questions={questions} />;
}
