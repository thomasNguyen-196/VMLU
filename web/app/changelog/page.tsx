import type { Metadata } from "next";
import ChangelogPage from "@/components/ChangelogPage.tsx";
import { loadChangelog } from "@/lib/changelog.ts";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Changelog hành vi model · VMLU",
  description: "Nhật ký quan sát hành vi/dị thường của model theo từng ngày, kèm bằng chứng artifact và phân loại model/provider/harness/data/ops.",
};

export default async function Page() {
  return <ChangelogPage doc={await loadChangelog()} />;
}
