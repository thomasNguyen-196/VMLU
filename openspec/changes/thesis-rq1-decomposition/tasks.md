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

## 4. MC-46/47 — factorial + noise floor trên 65K (chạy rồi)

- [x] 4.1 4 ô của ma trận persona × tools trên 65K + 2 lặp sạch cho noise floor
  (MC-46 pre-register → MC-47 kết quả).
  - **Bằng chứng:** 5 arm × 146 item, **0 failure**; F5 −1,37 (CI chạm 0) vs
    tools −11,64, persona −8,22; noise floor 65K = **1,37 điểm** (2 lặp).
- [x] 4.2 Bảng RQ1 cập nhật: mục factorial 65K + contrast gene ghép đôi (dùng lại
  `_paired_bootstrap`/`_mcnemar_p` của harness) + ô noise floor 65K.
  - **Bằng chứng:** 23 dòng contrast · 5 cell noise; `docs/rq1-decomposition.md`.
- [x] 4.3 Ghi sự cố hạ tầng (proxy thiếu DNS shim ⇒ 25 item `exit 1`, 60× chậm,
  **không** bị preflight bắt) vào MC-47.
  - **Bằng chứng:** MC-47 mục "Sự cố hạ tầng".

## 5. Còn lại

- [ ] 5.1 Bảng gene → CLI flag (`tasks.md` §4.2 của change `thesis-p0`) để genome
  chạy được, không chỉ validate được.
- [ ] 5.2 Xác định **shape thật** của T65 gốc (`system=690` ≠ `system=745`): MC-31
  mô tả "system prompt trung tính" nhưng proxy log ghi 690 ký tự. Cần một lần chạy
  đúng cấu hình MC-31 để **hoặc xác nhận hoặc đính chính** MC-31/32.
- [ ] 5.3 Nếu luận văn cần: lặp thêm từng ô (thu hẹp CI tương tác) và mở rộng
  factorial ra `reading400` — hiện mọi kết luận mới chỉ dựa trên `legal_mc`.