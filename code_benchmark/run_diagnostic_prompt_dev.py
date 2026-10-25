"""Prompt development on SYNTHETIC prompts for the prospective campaign (task 5 of
openspec/changes/diagnostic-prospective-campaign). No benchmark text is used or sent.

From the repo root:
  .venv/bin/python -m code_benchmark.run_diagnostic_prompt_dev --seed 101 --dry-run
  .venv/bin/python -m code_benchmark.run_diagnostic_prompt_dev --seed 101 --run [--workers 6] [--tunnel-dns 172.16.30.1]

Items are generated from templates with known gold answers, wrapped in the frozen MC / reading
skeletons, expanded to arms B and S by the campaign's own builders, sent through the campaign
runner's own `request` (so the real request code is exercised) and scored by the arm wrapper.
The acceptance rule for the S wording is final-label compliance of at least 95% on at least 36
S prompts; accuracy on these synthetic items is a sanity check only and is never tuned on.
`--run` needs the IEC VPN and the endpoint settings in .env; outputs go to the ignored all_res tree.
"""
from __future__ import annotations

import argparse
import contextlib
import dataclasses
import datetime
import itertools
import json
import random
import statistics
from concurrent.futures import ThreadPoolExecutor
from fractions import Fraction
from unittest.mock import patch
from urllib.parse import urlsplit

from dotenv import dotenv_values
from openai import OpenAI

from code_benchmark import diagnostic_prospective as dp
from code_benchmark import run_diagnostic_prospective as runner
from code_benchmark import vi_multimodel as v1

OUT = dp.ROOT / "all_res" / "diagnostic_prospective" / "prompt_dev"
MC_DATASET, RD_DATASET = "vi-multimodel-v1-legal-mc-146", "vi-multimodel-v1-vi-squad-200"
CITIES = ["Hòa Phú", "Bình Lâm", "Đại Thành", "Quang Minh", "Nam Sơn", "Thái An"]
NAMES = ["An", "Bình", "Chi", "Dũng", "Hà", "Khoa", "Lan", "Minh", "Nga", "Phúc"]
FILLER = ("Công trình được xây dựng theo quy hoạch chung của khu vực và nhiều lần được tu bổ. "
          "Ban quản lý công bố báo cáo hoạt động mỗi năm một lần và tiếp nhận ý kiến đóng góp của người dân. "
          "Các số liệu trong bài đều lấy từ báo cáo gần nhất của đơn vị.")


def vn(number: int) -> str:
    return f"{number:,}".replace(",", ".")


def finish(rng, question: str, correct: str, wrong: list[str]):
    pool = [correct] + [w for w in dict.fromkeys(wrong) if w != correct][:3]
    extra = 1
    while len(pool) < 4:
        pool.append(f"{correct} ({extra})")
        extra += 1
    rng.shuffle(pool)
    return question, pool, pool.index(correct)


def gen_discount(rng):
    while True:
        price = rng.choice([200_000, 250_000, 400_000, 500_000])
        d1, d2, back, qty = rng.choice([10, 20, 25]), rng.choice([5, 10]), rng.choice([4, 5, 10]), rng.randint(2, 5)
        value = Fraction(price) * (100 - d1) / 100 * (100 - d2) / 100 * qty * (100 - back) / 100
        if value.denominator == 1:
            break
    before_back = int(Fraction(price) * (100 - d1) / 100 * (100 - d2) / 100 * qty)
    q = (f"Một cửa hàng niêm yết giá một sản phẩm là {vn(price)} đồng. Trong đợt khuyến mãi, cửa hàng giảm {d1}% giá niêm yết, "
         f"sau đó giảm thêm {d2}% trên giá đã giảm. Một khách mua {qty} sản phẩm cùng loại và thanh toán bằng thẻ, được hoàn lại "
         f"{back}% trên tổng số tiền đã thanh toán. Hỏi số tiền khách thực sự phải chịu sau khi được hoàn tiền là bao nhiêu?")

    def fmt(n):
        return f"{vn(round(n))} đồng"

    return finish(rng, q, fmt(value), [fmt(before_back), fmt(price * (100 - d1 - d2) / 100 * qty * (100 - back) / 100),
                                       fmt(int(value) // qty)])


def gen_tank(rng):
    d, mins = rng.choice([10, 12, 15, 20, 25]), rng.choice([120, 150, 180, 200, 240])
    num, den = rng.choice([(1, 2), (2, 3), (3, 4)])
    remaining = d * mins
    volume = remaining * den // (den - num)
    outflow = rng.choice([20, 25, 30])
    inflow = outflow + d
    q = (f"Một bể nước có dung tích {f'{volume / 1000:g}'.replace('.', ',')} m³ (1 m³ = 1000 lít). Ban đầu bể chứa nước đến "
         f"{num}/{den} dung tích. Người ta mở đồng thời hai vòi: vòi thứ nhất bơm vào bể {inflow} lít mỗi phút, vòi thứ hai "
         f"xả ra khỏi bể {outflow} lít mỗi phút. Hỏi sau bao nhiêu phút kể từ lúc mở hai vòi thì bể đầy?")
    return finish(rng, q, f"{mins} phút", [f"{round(remaining / inflow)} phút", f"{mins + 30} phút", f"{max(10, mins - 40)} phút"])


def gen_race(rng):
    names = rng.sample(NAMES, 3)
    perms = list(itertools.permutations(names))

    def holds(order, clue):
        if clue[0] == "not_first":
            return order[0] != clue[1]
        if clue[0] == "not_last":
            return order[2] != clue[1]
        return order.index(clue[1]) > order.index(clue[2])

    while True:
        clues = []
        for _ in range(3):
            kind = rng.choice(["not_first", "not_last", "after"])
            clues.append((kind, *rng.sample(names, 2)) if kind == "after" else (kind, rng.choice(names)))
        solutions = [p for p in perms if all(holds(p, c) for c in clues)]
        if len(solutions) == 1:
            break
    text = {"not_first": "{0} không về nhất", "not_last": "{0} không về cuối cùng", "after": "{0} về đích sau {1}"}
    clause = "; ".join(text[c[0]].format(*c[1:]) for c in clues)
    q = (f"Ba người {', '.join(names[:2])} và {names[2]} cùng dự một cuộc thi chạy và về đích ở ba vị trí khác nhau, không có "
         f"người về đồng hạng. Biết rằng: {clause}. Thứ tự về đích của ba người, từ nhất đến cuối cùng, là gì?")
    answer = solutions[0]
    others = [p for p in perms if p != answer]
    rng.shuffle(others)
    return finish(rng, q, ", ".join(answer), [", ".join(p) for p in others[:3]])


def gen_travel(rng):
    while True:
        v, minutes = rng.choice([36, 40, 48, 54, 60, 72]), rng.choice([45, 75, 90, 105, 135, 150, 165])
        if v * minutes % 60 == 0:
            break
    start = rng.randint(6, 14) * 60 + rng.choice([0, 15, 30, 45])
    end = start + minutes
    distance = v * minutes // 60
    q = (f"Một xe khách rời bến A lúc {start // 60}:{start % 60:02d} và đến bến B lúc {end // 60}:{end % 60:02d}, chạy với vận tốc "
         f"không đổi {v} km/h và không dừng giữa đường. Quãng đường từ A đến B dài bao nhiêu ki-lô-mét?")
    return finish(rng, q, f"{distance} km", [f"{round(v * minutes / 100)} km", f"{distance + 12} km", f"{max(1, distance - 9)} km"])


def gen_recurrence(rng):
    a, b, n = rng.randint(1, 5), rng.randint(2, 6), rng.randint(7, 9)
    seq = [a, b]
    while len(seq) < n + 1:
        seq.append(seq[-1] + seq[-2])
    q = (f"Một dãy số được xác định bởi a1 = {a}, a2 = {b} và a(k+2) = a(k+1) + a(k) với mọi k ≥ 1. "
         f"Giá trị của a{n} là bao nhiêu?")
    return finish(rng, q, str(seq[n - 1]), [str(seq[n - 2]), str(seq[n]), str(seq[n - 1] + 2)])


def gen_deadline(rng):
    base = datetime.date(2026, rng.randint(1, 9), rng.randint(1, 27))
    days = rng.randint(15, 45)
    due = base + datetime.timedelta(days=days)

    def fmt(d):
        return d.strftime("%d/%m/%Y")

    q = (f"Theo quy chế, hồ sơ phải được nộp trong vòng {days} ngày kể từ ngày nhận thông báo, tính cả ngày nghỉ. "
         f"Thông báo được nhận ngày {fmt(base)}. Hạn chót nộp hồ sơ là ngày nào?")
    one = datetime.timedelta(days=1)
    return finish(rng, q, fmt(due), [fmt(due + one), fmt(due - one), fmt(due + datetime.timedelta(days=7))])


MC_GENERATORS = [gen_discount, gen_tank, gen_race, gen_travel, gen_recurrence, gen_deadline]


def gen_library(rng):
    city, year, k = rng.choice(CITIES), rng.randint(1965, 2008), rng.randint(3, 6)
    books, add = rng.choice([8, 12, 15, 20]) * 1000, rng.choice([800, 1200, 1500, 2000])
    desks, days = rng.choice([40, 60, 80]), rng.choice([5, 6, 7])
    passage = (f"Thư viện thành phố {city} được khánh thành năm {year} với {vn(books)} đầu sách. Mỗi năm sau đó, thư viện bổ sung "
               f"thêm {vn(add)} đầu sách mới. Thư viện có {desks} bàn đọc và mở cửa {days} ngày mỗi tuần. {FILLER}")
    return passage, [(f"Thư viện thành phố {city} được khánh thành vào năm nào?", str(year)),
                     (f"Sau {k} năm kể từ khi khánh thành, thư viện có tổng cộng bao nhiêu đầu sách?", vn(books + k * add)),
                     ("Thư viện mở cửa bao nhiêu ngày mỗi tuần?", str(days))]


def gen_coop(rng):
    name, tons = rng.choice(["Tân Lập", "Hòa Bình", "Đại Phú", "Thanh Sơn"]), rng.choice([800, 1000, 1200, 1600])
    s1, s2, drop, members = rng.choice([30, 35, 40]), rng.choice([25, 30, 35]), rng.choice([5, 10, 20]), rng.randint(40, 90)
    passage = (f"Hợp tác xã nông nghiệp {name} thu hoạch chè theo từng vụ. Năm đầu, sản lượng đạt {vn(tons)} tấn, trong đó vụ xuân "
               f"chiếm {s1}%, vụ hè chiếm {s2}% và vụ thu chiếm phần còn lại. Năm sau, do thời tiết bất lợi, tổng sản lượng giảm "
               f"{drop}% so với năm đầu. Hợp tác xã hiện có {members} hộ thành viên. {FILLER}")
    return passage, [("Vụ thu chiếm bao nhiêu phần trăm sản lượng năm đầu?", str(100 - s1 - s2)),
                     ("Sản lượng năm sau là bao nhiêu tấn?", str(tons * (100 - drop) // 100)),
                     ("Hợp tác xã có bao nhiêu hộ thành viên?", str(members))]


def gen_rules(rng):
    hours, grace, extra = rng.randint(2, 4), rng.choice([10, 15, 20]), rng.choice([5, 10])
    low, high = rng.randint(2, 4), rng.randint(6, 9)
    passage = (f"QUY CHẾ SỬ DỤNG PHÒNG HỌC NHÓM\nĐiều 1. Quy chế này áp dụng cho sinh viên và giảng viên của Trường.\n"
               f"Điều 2. Đăng ký phòng thực hiện trực tuyến chậm nhất 24 giờ trước giờ sử dụng. Mỗi lượt đăng ký phải có từ {low} đến "
               f"{high} người sử dụng; mỗi lượt không được vượt quá {hours} giờ.\n"
               f"Điều 3. Người đứng tên đăng ký phải nhận khóa phòng trong vòng {grace} phút kể từ giờ bắt đầu. Nếu nhóm có báo trước "
               f"qua cổng thông tin, thời hạn nhận phòng được kéo dài thêm {extra} phút, và việc kéo dài chỉ áp dụng một lần.\n"
               f"Điều 4. Nghiêm cấm mang đồ uống có cồn vào phòng. Vi phạm lần thứ nhất bị nhắc nhở bằng văn bản. {FILLER}")
    return passage, [("Mỗi lượt đăng ký phòng được sử dụng tối đa bao nhiêu giờ?", str(hours)),
                     ("Một nhóm đã báo trước qua cổng thông tin. Tổng thời hạn tối đa để nhận khóa phòng, tính từ giờ bắt đầu, "
                      "là bao nhiêu phút?", str(grace + extra)),
                     ("Mỗi lượt đăng ký phải có tối thiểu bao nhiêu người?", str(low))]


RD_GENERATORS = [gen_library, gen_coop, gen_rules]


def synthetic_items(seed: int) -> list[v1.EvalItem]:
    rng = random.Random(seed)  # nosec B311 - reproducible synthetic data, not cryptography
    items: list[v1.EvalItem] = []

    def add(task, question, prompt, gold):
        items.append(v1.EvalItem(
            dataset_id=MC_DATASET if task == "multiple_choice" else RD_DATASET, source_dataset="synthetic",
            item_id=f"SYN-{seed}-{len(items):02d}", replicate_id=dp.MAIN_REPLICATE, task=task, stratum="synthetic",
            question=question, passage_id="syn", prompt=prompt, gold_answer=gold))

    for generator in MC_GENERATORS:
        for _ in range(3):
            question, options, correct = generator(rng)
            body = question + "\n\n" + "\n".join(f"{'ABCD'[i]}. {o}" for i, o in enumerate(options))
            add("multiple_choice", question, dp.MC_HEAD + body + dp.MC_TAIL, "ABCD"[correct])
    for generator in RD_GENERATORS:
        for _ in range(2):
            passage, questions = generator(rng)
            for question, gold in questions:
                add("reading", question, dp.RD_HEAD + passage + dp.RD_QUESTION + question + dp.RD_TAIL, gold)
    return items


def arm_items_for(items, templates):
    return [dataclasses.replace(item, replicate_id=f"{arm}-r1", prompt=dp.build_arm_prompt(item, arm, templates))
            for item in items for arm in ("B", "S")]


def check_disjoint(items) -> int:
    frozen = {v1.sha256_bytes(i.prompt.encode()) for i in v1.rebuild_items("main").values()}
    clash = [i.item_id for i in items if v1.sha256_bytes(i.prompt.encode()) in frozen]
    if clash:
        raise SystemExit(f"Error: synthetic prompts equal frozen benchmark prompts: {clash}")
    return len(frozen)


def dry_run(items, templates) -> None:
    frozen = check_disjoint(items)
    arm_items = arm_items_for(items, templates)
    lengths = sorted(len(i.prompt) for i in arm_items)
    kinds = {k: sum(i.task == k for i in items) for k in ("multiple_choice", "reading")}
    print(f"synthetic items={len(items)} {kinds} | arm prompts={len(arm_items)} | chars min/median/max="
          f"{lengths[0]}/{int(statistics.median(lengths))}/{lengths[-1]} | disjoint from {frozen} frozen prompts: ok")
    sample_mc = next(i for i in arm_items if i.task == "multiple_choice" and i.replicate_id.startswith("S-"))
    sample_rd = next(i for i in arm_items if i.task == "reading" and i.replicate_id.startswith("S-"))
    print("\n--- S / multiple choice sample ---\n" + sample_mc.prompt)
    print("\n--- S / reading sample (tail) ---\n" + sample_rd.prompt[-420:])


def run(items, templates, protocol, workers: int, tunnel_dns: str, seed: int) -> None:
    check_disjoint(items)
    arm_items = arm_items_for(items, templates)
    manifest = {"protocol_id": dp.PROTOCOL_ID, "items": [v1.manifest_item(i) for i in arm_items]}
    manifest["manifest_sha256"] = v1.sha256_bytes(v1.canonical_json(manifest))
    rebuilt = {i.run_key: i for i in arm_items}
    env = dotenv_values(runner.ROOT / ".env")
    host = urlsplit(str(env["OPENAI_BASE_URL"])).hostname or ""
    address = runner.install_resolver_shim(host, tunnel_dns)
    print(f"resolver shim (this process only): {host} -> {address} via {tunnel_dns}")
    client = OpenAI(base_url=str(env["OPENAI_BASE_URL"]), api_key=str(env["OPENAI_API_KEY"]), timeout=300, max_retries=0,
                    default_headers=protocol["transport"]["gateway_header"])
    guard = runner.BudgetGuard(10 ** 9)
    with contextlib.ExitStack() as stack:
        for field in ("MODEL", "PROFILE", "PROTOCOL", "CARD_ID", "request"):
            stack.enter_context(patch.object(runner.base, field, getattr(runner.base, field)))
        runner.configure_engine(protocol, "dev", "MC-DEV", guard)
        request = runner.base.request
        with ThreadPoolExecutor(workers) as pool:
            rows = list(pool.map(lambda item: request(client, item, 0, 0), arm_items))
    predictions = {row["run_key"]: row for row in rows}
    scored, _ = dp.score_arm_rows(manifest, predictions, rebuilt)
    OUT.mkdir(parents=True, exist_ok=True)
    for name, data in (("rows", rows), ("scores", scored)):
        (OUT / f"{name}_seed{seed}.jsonl").write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in data) + "\n", encoding="utf-8")

    errors = [r for r in rows if r["status"] != "complete"]
    print(f"\nrequests={len(rows)} request_errors={len(errors)} {[r.get('error_type') for r in errors][:4]}")
    for arm in ("B", "S"):
        sub = [r for r in scored if r["arm"] == arm]
        mc = [r for r in sub if "correct" in r]
        rd = [r for r in sub if "em" in r]
        done = [r for r in rows if r["arm"] == arm and r["status"] == "complete"]
        tokens = [r["completion_tokens"] for r in done if isinstance(r.get("completion_tokens"), int)]
        latency = [r["latency_s"] for r in done]
        print(f"[{arm}] mc correct {sum(r['correct'] for r in mc)}/{len(mc)} (unparsed {sum(not r['prediction'] for r in mc)}) | "
              f"reading EM {sum(r['em'] for r in rd)}/{len(rd)} F1 {statistics.fmean(r['token_f1'] for r in rd):.2f} | "
              f"truncated {sum(r['finish_reason'] == 'length' for r in sub)} | completion tokens mean/max "
              f"{statistics.fmean(tokens):.0f}/{max(tokens)} | latency mean {statistics.fmean(latency):.1f}s")
    reasoning = [r for r in scored if r["arm"] == "S"]
    ok = sum(bool(r["format_ok"]) for r in reasoning)
    mc_ok = sum(bool(r["format_ok"]) for r in reasoning if "correct" in r)
    rd_ok = sum(bool(r["format_ok"]) for r in reasoning if "em" in r)
    markdown = sum(bool(r["markdown_final_line"]) for r in reasoning if "em" in r)
    pct = 100 * ok / len(reasoning)
    print(f"S final-label compliance {ok}/{len(reasoning)} = {pct:.1f}% (mc {mc_ok}/{sum('correct' in r for r in reasoning)}, "
          f"reading {rd_ok}/{sum('em' in r for r in reasoning)}); markdown on reading final line: {markdown} "
          f"-> {'PASS' if pct >= 95 else 'FAIL'} (threshold 95%)")
    for row in [r for r in reasoning if not r["format_ok"] or r["markdown_final_line"]][:6]:
        print(f"  non-compliant {row['item_id']}: ...{row['raw_response'][-170:]!r}")
    for row in [r for r in reasoning if r.get("correct") == 0 or r.get("em") == 0][:4]:
        print(f"  S miss {row['item_id']} gold={row['gold_answer']!r} pred={row['prediction']!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--run", action="store_true")
    parser.add_argument("--seed", type=int, default=101)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--tunnel-dns", default="172.16.30.1")
    args = parser.parse_args()
    templates, protocol = dp.load_templates(), dp.load_protocol()
    items = synthetic_items(args.seed)
    if args.dry_run:
        dry_run(items, templates)
    else:
        run(items, templates, protocol, args.workers, args.tunnel_dns, args.seed)


if __name__ == "__main__":
    main()
