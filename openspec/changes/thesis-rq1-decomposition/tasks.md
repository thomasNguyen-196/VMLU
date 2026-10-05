## 1. Generator

- [x] 1.1 `code_benchmark/build_rq1_decomposition.py`: declared `SOURCES` (scaffold
  @65K ×6 dataset, scaffold @28K ×3 lần chạy, scaffold @MiMo, persona × tools ×3
  ô, option order), `read_source` fail-fast, `noise_floor`, `calibration_rows`,
  `render`, `main`.
  - **Bằng chứng:** 14 dòng contrast · 4 cell noise · 2 dòng calibration; thiếu
    artifact ⇒ `SystemExit` "cannot be invented".
- [x] 1.2 Sinh `docs/rq1-decomposition.csv`, `-noise.csv`, `.md` (tiêu đề báo rõ
  "sinh tự động, đừng sửa tay").
  - **Bằng chứng:** 3 file tracked; mọi số trong `.md` đến từ artifact.
- [x] 1.3 Caveat sinh từ dữ liệu (số cell/số lần chạy/n), `p_fmt` không in
  `0.000`, metric ghi tên từng dòng.
  - **Bằng chứng:** `p_fmt("1.049e-05") == "1.0e-05"`; caveat ghi "4 cell × 2–3
    lần chạy, n=146" tự từ `noise_floor()`.

## 2. Tests

- [x] 2.1 `TestRq1Decomposition`: artifact thiếu ⇒ lỗi; mọi nguồn khai báo tồn tại;
  mỗi dòng scaffold có model riêng; metric không bị gộp; p nhỏ không thành 0;
  noise floor giữ từng cell, `n` cố định, ≥2 lần chạy; render từ artifact thật.
  - **Bằng chứng:** 7 test; suite **272 OK**, ruff sạch.

## 3. Đăng ký genome cho arm đã có (zero compute)

- [x] 3.1 Bundle đầu tiên: arm A3 ≡ `minimal_genome()` (`8e6d943df3ad94a0`) và arm
  T65 ≡ `baseline_genome()` (`d02b0c5126b940a7`).
  - **Bằng chứng:** `all_res/evidence/8e6d943df3ad94a0/` và `…/d02b0c5126b940a7/`
    (gitignored), sinh lại sau khi commit để `code_changed` trung thực.

## 4. Còn lại

- [ ] 4.1 MC-46: hình thức hoá `minimal_genome()` / `baseline_genome()` thành lệnh
  chạy được (bảng gene → CLI flag — `tasks.md` §4.2 của change `thesis-p0`).
- [ ] 4.2 Đo noise floor có hệ thống ở **65K** (hiện chỉ có một cặp gián tiếp từ
  MC-44); cần ≥2 lần chạy lại cùng một arm.
- [ ] 4.3 Nếu luận văn cần: chạy lại ô factorial persona × tools trên 65K (hiện
  chỉ có ở 28K, node đã offline).