#!/usr/bin/env python3
"""
Test Cache Probe: Kiểm tra thực tế xem CommandCode có ghi nhận Cache Hit Token hay không.

Theo tài liệu chính thức của Google Gemini API:
Ngưỡng tối thiểu (Min token limit) để kích hoạt Implicit Caching trên Gemini 3.8 Flash là:
>>> 4.096 TOKENS <<<

Vì vậy, nếu prompt dưới 4.096 tokens thì cache hit CHẮC CHẮN = 0.
Script này sẽ tạo một văn bản ngữ cảnh cố định > 4.500 tokens, gửi 2 request liên tiếp:
- Request 1: Nạp cache trên server Google (warmup).
- Request 2: Giữ nguyên tiền tố văn bản đó, hỏi tiếp câu hỏi thứ hai.
"""

import os
import sys
import time
import json
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

BASE_URL = os.getenv("COMMANDCODE_BASE_URL", "").strip()
API_KEY = os.getenv("COMMANDCODE_API_KEY", "").strip()
MODEL = os.getenv("COMMANDCODE_MODEL", "google/gemini-3.8-flash").strip()

if not API_KEY or not BASE_URL:
    print("❌ LỖI: Thiếu cấu hình trong file .env")
    sys.exit(1)

from openai import OpenAI

client = OpenAI(
    base_url=BASE_URL,
    api_key=API_KEY,
)

print("=" * 65)
print(f"🧪 KIỂM TRA IMPLICIT CONTEXT CACHING TRÊN GEMINI 3.8 FLASH")
print(f"• Endpoint : {BASE_URL}")
print(f"• Model    : {MODEL}")
print(f"• Quy tắc Google: Gemini 3.8 Flash yêu cầu tối thiểu 4.096 tokens để bật Cache!")
print("=" * 65)

# Tạo một đoạn tài liệu dài chuẩn xác khoảng 4.500 - 5.000 tokens
sample_text_paragraph = (
    "Bộ luật Dân sự số 91/2015/QH13 quy định địa vị pháp lý, chuẩn mực pháp lý về cách ứng xử "
    "của cá nhân, pháp nhân; quyền, nghĩa vụ về nhân thân và tài sản của cá nhân, pháp nhân trong "
    "các quan hệ được hình thành trên cơ sở bình đẳng, tự do ý chí, độc lập về tài sản và tự chịu trách nhiệm. "
    "Quan hệ dân sự có yếu tố nước ngoài là quan hệ dân sự thuộc một trong các trường hợp sau đây: "
    "Có ít nhất một trong các bên tham gia là cá nhân, pháp nhân nước ngoài; "
    "Các bên tham gia đều là công dân Việt Nam, pháp nhân Việt Nam nhưng việc xác lập, thay đổi, thực hiện "
    "hoặc chấm dứt quan hệ đó xảy ra tại nước ngoài; "
    "Các bên tham gia đều là công dân Việt Nam, pháp nhân Việt Nam nhưng đối tượng của quan hệ dân sự đó ở nước ngoài.\n"
)

# Lặp lại để đạt khoảng 4.500+ tokens
long_context = (sample_text_paragraph * 45)

messages_1 = [
    {
        "role": "system",
        "content": (
            "Bạn là một chuyên gia phân tích luật pháp Việt Nam. Dưới đây là tài liệu tham khảo:\n\n"
            + long_context
        ),
    },
    {"role": "user", "content": "Tóm tắt ngắn gọn trong 1 câu: Tài liệu trên nói về bộ luật nào?"},
]

print(f"\n📡 [LẦN 1] Gửi request với prompt dài (~4.500+ tokens) để nạp cache (warm-up)...")
t0 = time.perf_counter()
try:
    res1 = client.chat.completions.create(
        model=MODEL,
        messages=messages_1,
    )
    lat1 = time.perf_counter() - t0
    u1 = res1.usage
    p1 = getattr(u1, "prompt_tokens", 0)
    c1 = getattr(getattr(u1, "prompt_tokens_details", None), "cached_tokens", 0)
    print(f"✅ Lần 1 xong trong {lat1:.2f}s | Prompt tokens: {p1} | Cached tokens: {c1}")
except Exception as e:
    print(f"❌ Lỗi ở Lần 1: {e}")
    sys.exit(1)

# Gửi tiếp lần 2 ngay lập tức với cùng system prompt / context dài, chỉ đổi câu hỏi cuối
messages_2 = [
    {
        "role": "system",
        "content": (
            "Bạn là một chuyên gia phân tích luật pháp Việt Nam. Dưới đây là tài liệu tham khảo:\n\n"
            + long_context
        ),
    },
    {"role": "user", "content": "Quan hệ dân sự có yếu tố nước ngoài bao gồm những trường hợp nào? Trả lời thật ngắn gọn."},
]

print(f"\n📡 [LẦN 2] Gửi request ngay lập tức với CÙNG tiền tố ngữ cảnh dài để kiểm tra Cache Hit...")
t1 = time.perf_counter()
try:
    res2 = client.chat.completions.create(
        model=MODEL,
        messages=messages_2,
    )
    lat2 = time.perf_counter() - t1
    u2 = res2.usage
    p2 = getattr(u2, "prompt_tokens", 0)
    prompt_details_2 = getattr(u2, "prompt_tokens_details", None)
    c2 = getattr(prompt_details_2, "cached_tokens", 0) if prompt_details_2 else None
    reasoning_2 = getattr(getattr(u2, "completion_tokens_details", None), "reasoning_tokens", 0)

    print(f"✅ Lần 2 xong trong {lat2:.2f}s")
    print("\n" + "─" * 65)
    print("📊 KẾT QUẢ USAGE LẦN 2 (RAW):")
    if hasattr(u2, "model_dump"):
        print(json.dumps(u2.model_dump(), indent=2, ensure_ascii=False))
    else:
        print(u2)

    print("─" * 65)
    print(f"• Input tokens (Prompt)       : {p2}")
    print(f"• Output tokens (Completion)  : {getattr(u2, 'completion_tokens', 0)}")
    print(f"• Thinking tokens (Reasoning) : {reasoning_2}")
    print(f"• 🎯 CACHE HIT TOKENS         : {c2}")
    print("=" * 65)
    if c2 and c2 > 0:
        print(f"🎉 XÁC NHẬN: Cache Hit thành công {c2} tokens! CommandCode forward chuẩn 100%!")
    else:
        print(f"ℹ️ Cache Hit vẫn bằng 0. (Proxy không chia sẻ cache session hoặc Google chưa kịp cache giữa 2 request độc lập).")
    print("=" * 65)

except Exception as e:
    print(f"❌ Lỗi ở Lần 2: {e}")
