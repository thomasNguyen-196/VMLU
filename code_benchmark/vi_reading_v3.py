"""Reading scorer vi-reading-v3: vi-reading-v2 after removing Markdown emphasis and code marks
(openspec change diagnostic-router-loop, decision 10).

vi-reading-v2 (`vi_multimodel.score_vi_reading` on the line after the last final-answer label) keeps `*` and `` ` ``
on word tokens. A bolded answer such as `**từ 20% đến 30%**` therefore loses token-F1 and exact match although its
words are right, and a bolded label followed by a line break (`**Trả lời:**` then the answer) is read as an empty
answer. v3 deletes every `*` and `` ` `` from the response and from the reference, then applies v2 unchanged. No gold
answer of the reading sets contains either mark.

v2 stays the frozen scorer of every card registered with it; v3 is a separate, named version reported beside it.
Stdlib only, apart from the frozen v2 functions.
"""
from __future__ import annotations

from typing import Any

try:
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import vi_multimodel as v1

SCORER_VERSION = "vi-reading-v3"
BASE_VERSION = "vi-reading-v2"
MARKS = "*`"
_DELETE = str.maketrans("", "", MARKS)


def strip_marks(text: str) -> str:
    return str(text or "").translate(_DELETE)


def score_reading(raw_response: str, gold_answer: str) -> dict[str, Any]:
    """{prediction, em, token_f1} of one reading response, scored as score_vi_multimodel.score_rows scores v2."""
    prediction = v1.extract_final_answer(strip_marks(raw_response))
    return {"prediction": prediction, **v1.score_vi_reading(prediction, strip_marks(gold_answer))}


def rescore_row(row: dict[str, Any]) -> dict[str, Any]:
    """A copy of a scored row with v3 values. Multiple-choice rows come back unchanged.

    The scored text is `scoring_response` when the row has one (the diagnostic campaign keeps the raw reply in
    `raw_response` and what was scored beside it), otherwise `raw_response`."""
    if "token_f1" not in row:
        return dict(row)
    text = row["scoring_response"] if "scoring_response" in row else row["raw_response"]
    return {**row, **score_reading(str(text), str(row["gold_answer"])), "scorer_version": SCORER_VERSION}
