import re

def extract_answer(raw_text: str) -> str:
    if not raw_text:
        return ""
    raw = raw_text.strip()

    # 1. Exact match / start with single option (e.g. 'A', 'A.', 'A)', '(A)', '**A**')
    m = re.match(r'^(?:\*{1,2}|\()?\s*([A-Ea-e])\s*(?:\*{1,2}|\))?[\.\:\s]*$', raw)
    if m:
        return m.group(1).upper()

    # 2. Key phrases in Vietnamese & English
    m = re.search(r'(?:đáp án|câu trả lời|chọn|kết quả|answer|option|choice)\s*(?:là|đúng|chính xác|là:|:)?\s*[\*\(\[]*\s*([A-Ea-e])\b', raw, re.IGNORECASE)
    if m:
        return m.group(1).upper()

    # 3. Standalone uppercase letter A-E (e.g. '... is B ...' or '... (C) ...')
    m = re.search(r'(?<!\w)([A-E])(?!\w)', raw)
    if m:
        return m.group(1).upper()

    # 4. Standalone lowercase letter a-e
    m = re.search(r'(?<!\w)([a-e])(?!\w)', raw)
    if m:
        return m.group(1).upper()

    return ""

def build_prompt(question: str, choices: list) -> str:
    text_choice = '\n'.join(str(c) for c in choices)
    prompt = (
        "Chỉ đưa ra chữ cái đứng trước câu trả lời đúng (A, B, C, D hoặc E) của câu hỏi trắc nghiệm sau: \n"
        + question
        + "\n\n"
        + text_choice
        + "\n"
        + "Đáp án: "
    )
    return prompt

def test_extract_answer():
    test_cases = [
        ('A', 'A'),
        ('A.', 'A'),
        ('b)', 'B'),
        ('(C)', 'C'),
        ('**D**', 'D'),
        ('Đáp án là B.', 'B'),
        ('Đáp án: C', 'C'),
        ('Chọn đáp án D', 'D'),
        ('The correct answer is E.', 'E'),
        ('Option A is correct', 'A'),
        ('Câu hỏi này đáp án là B', 'B'),
        ('Kết quả: D', 'D'),
        ('The choice is (C)', 'C'),
        ('Không có đáp án đúng trong các lựa chọn', ''),
        ('Tôi không biết câu trả lời này', ''),
        ('Hãy giải thích chi tiết câu này', ''),
        ('', ''),
    ]

    for text, expected in test_cases:
        res = extract_answer(text)
        assert res == expected, f'Failed for "{text}": got "{res}", expected "{expected}"'

    print("PASS: test_extract_answer (17 cases)")

def test_build_prompt_parity():
    question = "Thủ đô của Việt Nam là gì?"
    choices = ["A. Hà Nội", "B. TP. Hồ Chí Minh", "C. Đà Nẵng", "D. Hải Phòng"]
    prompt = build_prompt(question, choices)
    
    expected = (
        "Chỉ đưa ra chữ cái đứng trước câu trả lời đúng (A, B, C, D hoặc E) của câu hỏi trắc nghiệm sau: \n"
        + question
        + "\n\n"
        + "A. Hà Nội\nB. TP. Hồ Chí Minh\nC. Đà Nẵng\nD. Hải Phòng"
        + "\n"
        + "Đáp án: "
    )
    assert prompt == expected
    print("PASS: test_build_prompt_parity")

if __name__ == "__main__":
    test_extract_answer()
    test_build_prompt_parity()
    print("All unit tests completed successfully!")
