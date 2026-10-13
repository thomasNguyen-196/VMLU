#!/usr/bin/env python3
"""
Test Probe: Kiểm tra chi tiết Token Usage và Completion Time qua CommandCode (hoặc OpenAI-compatible proxy).

Mục tiêu:
1. Đo chính xác thời gian hoàn thành (wall-clock latency).
2. Kiểm tra xem Proxy có forward đủ 4 trường:
   - prompt_tokens (input)
   - completion_tokens (output)
   - reasoning_tokens (thinking tokens)
   - cached_tokens (cache hit tokens)
"""

import os
import sys
import time
import json
from pathlib import Path
from dotenv import load_dotenv

# Tải cấu hình từ file .env cùng thư mục
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

BASE_URL = os.getenv("COMMANDCODE_BASE_URL", "").strip()
API_KEY = os.getenv("COMMANDCODE_API_KEY", "").strip()
MODEL = os.getenv("COMMANDCODE_MODEL", "gemini-3.8-flash").strip()

if not API_KEY or API_KEY == "your_api_key_here":
    print("❌ LỖI: Bạn chưa điền COMMANDCODE_API_KEY vào file:")
    print(f"   {env_path}")
    sys.exit(1)

if not BASE_URL:
    print("❌ LỖI: Chưa cấu hình COMMANDCODE_BASE_URL trong file .env")
    sys.exit(1)

from openai import OpenAI

client = OpenAI(
    base_url=BASE_URL,
    api_key=API_KEY,
)

print("=" * 65)
print(f"🚀 BẮT ĐẦU TEST PROBE TOKEN USAGE & LATENCY")
print(f"• Base URL : {BASE_URL}")
print(f"• Model    : {MODEL}")
print("=" * 65)

# Câu hỏi kiểm thử đòi hỏi suy luận để kích hoạt thinking nếu model có hỗ trợ
test_prompt = (
    "Giải bài toán sau từng bước: Trong một lớp học có 45 học sinh. "
    "Có 28 bạn thích Toán, 22 bạn thích Văn, và 5 bạn không thích cả hai môn. "
    "Hỏi có bao nhiêu bạn thích cả hai môn Toán và Văn? Đưa ra đáp án cuối cùng."
)

messages = [
    {
        "role": "system",
        "content": (
            "Bạn là một trợ lý AI thông minh, giải toán chính xác và chặt chẽ. "
            "Trình bày ngắn gọn, đưa ra con số chính xác."
        ),
    },
    {"role": "user", "content": test_prompt},
]

print("\n📡 Đang gửi request lần 1...")
t0 = time.perf_counter()

try:
    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
    )
    latency_1 = time.perf_counter() - t0
except Exception as e:
    print(f"\n❌ Lỗi khi gọi API: {e}")
    sys.exit(1)

print(f"✅ Request hoàn tất trong: {latency_1:.3f} giây")

# Kiểm tra Usage Object
usage = response.usage
print("\n" + "─" * 65)
print("📊 DỮ LIỆU USAGE NGUYÊN BẢN (RAW RESPONSE USAGE):")
if usage:
    if hasattr(usage, "model_dump"):
        print(json.dumps(usage.model_dump(), indent=2, ensure_ascii=False))
    else:
        print(usage)
else:
    print("⚠️ API không trả về trường `usage`!")

print("─" * 65)
print("🔍 PHÂN TÍCH TỪNG TRƯỜNG DỮ LIỆU:")

prompt_tokens = getattr(usage, "prompt_tokens", None) if usage else None
completion_tokens = getattr(usage, "completion_tokens", None) if usage else None
total_tokens = getattr(usage, "total_tokens", None) if usage else None

# Chi tiết thinking tokens (reasoning_tokens)
completion_details = getattr(usage, "completion_tokens_details", None) if usage else None
reasoning_tokens = getattr(completion_details, "reasoning_tokens", None) if completion_details else None

# Chi tiết cache hit tokens (cached_tokens)
prompt_details = getattr(usage, "prompt_tokens_details", None) if usage else None
cached_tokens = getattr(prompt_details, "cached_tokens", None) if prompt_details else None

print(f"1. Input Tokens (Prompt)       : {prompt_tokens}")
print(f"2. Output Tokens (Completion)  : {completion_tokens}")
print(f"3. Thinking Tokens (Reasoning) : {reasoning_tokens if reasoning_tokens is not None else '❌ Không có (Proxy không forward hoặc model không sinh)'}")
print(f"4. Cache Hit Tokens            : {cached_tokens if cached_tokens is not None else '❌ Không có (Chưa hit cache hoặc Proxy không forward)'}")
print(f"5. Total Tokens                : {total_tokens}")

# Thử request lần 2 với cùng prompt để kiểm tra Cache Hit
print("\n" + "─" * 65)
print("📡 Đang gửi tiếp request lần 2 (cùng prompt) để kiểm tra Cache Hit...")
t1 = time.perf_counter()
try:
    response_2 = client.chat.completions.create(
        model=MODEL,
        messages=messages,
    )
    latency_2 = time.perf_counter() - t1
    usage_2 = response_2.usage
    prompt_details_2 = getattr(usage_2, "prompt_tokens_details", None) if usage_2 else None
    cached_tokens_2 = getattr(prompt_details_2, "cached_tokens", None) if prompt_details_2 else None
    
    print(f"✅ Request 2 hoàn tất trong: {latency_2:.3f} giây")
    print(f"• Cache Hit ở Request 2: {cached_tokens_2 if cached_tokens_2 is not None else '❌ Vẫn không có'}")
except Exception as e:
    print(f"⚠️ Request 2 gặp lỗi: {e}")

print("=" * 65)
print("🏁 KẾT LUẬN:")
if reasoning_tokens is not None and cached_tokens is not None:
    print("🎉 TUYỆT VỜI! Proxy này forward ĐẦY ĐỦ 100% cả Thinking và Cache tokens!")
elif reasoning_tokens is not None:
    print("ℹ️ Proxy CÓ forward Thinking tokens, nhưng chưa thấy Cache tokens.")
else:
    print("⚠️ Proxy CHỈ trả về Input/Output tokens cơ bản, đã ẩn hoặc không forward Thinking/Cache.")
print("=" * 65)
