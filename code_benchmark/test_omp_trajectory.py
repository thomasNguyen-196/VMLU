"""Offline tests for MC-113's omp trajectory parser (omp_trajectory). The tool-result formats are those recorded from
omp 18.0.0 against a scripted server (all_res/diagnostic_legal_agent_omp/probe_20261113 and the offline runs of tasks
1.2 to 1.4); hits go through MC-112's `provision_hits` unchanged."""
import json
import unittest

from code_benchmark import diagnostic_legal_agent as la
from code_benchmark import omp_trajectory as ot

LAW = "luat-giam-dinh-tu-phap-2012.txt"
OTHER = "luat-ke-toan-2015.txt"
ANCHOR = "Điều 7. Tiêu chuẩn bổ nhiệm giám định viên tư pháp"


def call(call_id: str, tool: str, **arguments) -> dict:
    return {"id": call_id, "type": "function",
            "function": {"name": tool, "arguments": json.dumps({"i": "Doing it", **arguments}, ensure_ascii=False)}}


def body(*turns: tuple[dict, str | None]) -> dict:
    """A request body: system, user, then for each (call, result) an assistant tool call and, if the result is not
    None, its tool message."""
    messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": [{"type": "text", "text": "q"}]}]
    for tool_call, result in turns:
        messages.append({"role": "assistant", "content": "", "tool_calls": [tool_call]})
        if result is not None:
            messages.append({"role": "tool", "tool_call_id": tool_call["id"], "content": result})
    return {"model": "Qwen3.5-9B-65K", "messages": messages}


def records(*bodies: dict) -> list[dict]:
    return [{"n": n, "outcome": "ok", "body_received": json.dumps(b, ensure_ascii=False)}
            for n, b in enumerate(bodies, 1)]


def hits(observations: list[dict], file: str = LAW, anchor: str = ANCHOR) -> dict:
    return la.provision_hits(observations, [{"file": file, "anchor_line": anchor}])[0]


WHOLE_READ = "\n".join(["Luật Giám định tư pháp 2012", "Điều 1. Phạm vi điều chỉnh", "[…139ln elided…]",
                        "Điều 40. Hiệu lực thi hành", "", "",
                        "[Showing lines 1-81 and 221-300 of 300; 139 middle lines (23.8KB) elided. Use :301 to "
                        "continue. Read artifact://0 for full output. Some lines truncated to 768 chars]"])
GREP = "\n".join([f"# {OTHER}", " 40|", "*41|Điều 7. Kế toán viên", "", f"# {LAW}", " 61|Chương II",
                  f" 62|{ANCHOR}", "*63|1. Công dân Việt Nam thường trú tại Việt Nam có đủ tiêu chuẩn", "",
                  "Showing files 1-20 of 293. Use skip=20 for the next page, or narrow paths/pattern."])


class Parse(unittest.TestCase):
    def test_whole_file_read_counts_only_the_shown_lines(self):
        obs = ot.omp_observations(records(body((call("c0", "read", path=LAW), WHOLE_READ))))
        self.assertEqual(obs[0]["read_file"], LAW)
        self.assertEqual(obs[0]["lines"][LAW], ["Luật Giám định tư pháp 2012", "Điều 1. Phạm vi điều chỉnh",
                                                "Điều 40. Hiệu lực thi hành", "", ""])
        # the anchor sits in the elided middle: the file was opened, its provision not read
        self.assertEqual(hits(obs), {"seen": False, "read": False, "opened": True})
        self.assertEqual(hits(obs, anchor="Điều 1. Phạm vi điều chỉnh"), {"seen": True, "read": True, "opened": True})

    def test_selector_and_absolute_paths_name_the_file(self):
        result = f"{ANCHOR}\n1. Công dân\n\n[Showing lines 61-80 of 400. Use :81 to continue]"
        for path in (f"{LAW}:61-80", f"{LAW}:64", f"/work/van-ban-phap-luat/{LAW}", f"./{LAW}:raw"):
            obs = ot.omp_observations(records(body((call("c0", "read", path=path), result))))
            self.assertEqual(obs[0]["read_file"], LAW, path)
            self.assertEqual(hits(obs), {"seen": True, "read": True, "opened": True}, path)

    def test_grep_blocks_count_matches_and_context_as_seen(self):
        obs = ot.omp_observations(records(body((call("c0", "grep", pattern="Công dân", path="."), GREP))))
        self.assertEqual(obs[0]["lines"][OTHER], ["", "Điều 7. Kế toán viên"])
        self.assertIn(ANCHOR, obs[0]["lines"][LAW])  # shown as context, not as the match
        self.assertEqual(hits(obs), {"seen": True, "read": False, "opened": False})

    def test_a_grep_of_one_file_has_no_header(self):
        result = f" 61|Chương II\n*62|{ANCHOR}\n 63|1. Công dân"
        obs = ot.omp_observations(records(body((call("c0", "grep", pattern="^Điều 7", path=LAW), result))))
        self.assertEqual(obs[0]["lines"], {LAW: ["Chương II", ANCHOR, "1. Công dân"]})
        self.assertTrue(hits(obs)["seen"])

    def test_glob_directories_urls_internal_documents_and_outside_paths_show_nothing(self):
        cases = [(call("c0", "glob", path="*.txt"), f"{LAW}\n{OTHER}"),
                 (call("c1", "read", path="."), f".\n  - {LAW}   17.5KB    1d ago"),
                 (call("c2", "read", path="https://example.com"),
                  "URL: https://example.com\nContent-Type: unknown\nMethod: failed\nNotes: Failed to fetch URL"),
                 (call("c3", "read", path="omp://"), f"# omp docs\n{ANCHOR}"),
                 (call("c4", "read", path="/etc/passwd"), f"root:x:0:0\n{ANCHOR}")]
        obs = ot.omp_observations(records(body(*cases)))
        self.assertEqual([o["lines"] for o in obs], [{}] * 5)
        self.assertEqual([o["status"] for o in obs], ["completed", "completed", "error", "completed", "completed"])
        self.assertEqual(hits(obs), {"seen": False, "read": False, "opened": False})

    def test_tool_errors_and_results_that_never_reached_the_model(self):
        obs = ot.omp_observations(records(body((call("c0", "read", path="khong-co.txt"), "Path 'khong-co.txt' not found"),
                                               (call("c1", "read", path=LAW), None))))
        self.assertEqual([(o["call_id"], o["status"], o["lines"]) for o in obs], [("c0", "error", {})])

    def test_a_spilled_read_read_back_counts_as_a_read_of_its_file(self):
        full = f"Luật Giám định tư pháp 2012\n{ANCHOR}\n\n[Full output: artifact://0 in the session file " \
               "/home/agent/.omp/agent/sessions/--work--/x/0.read.log (63.5KB). Use artifact://0:N-M to page]"
        first = body((call("c0", "read", path=LAW), WHOLE_READ))
        later = body((call("c0", "read", path=LAW), WHOLE_READ), (call("c1", "read", path="artifact://0"), full))
        obs = ot.omp_observations(records(first, later))
        self.assertEqual((obs[1]["source"], obs[1]["read_file"]), ("artifact://0", LAW))
        self.assertEqual(hits(obs), {"seen": True, "read": True, "opened": True})
        self.assertEqual(ot.selectors(obs), {"read_whole": 1, "read_range": 0, "read_spill": 1, "grep_next_page": 0})
        # the session file the note points to is the same artifact
        by_path = ot.omp_observations(records(body(
            (call("c0", "read", path=LAW), WHOLE_READ),
            (call("c1", "read", path="/home/agent/.omp/agent/sessions/--work--/x/0.read.log"), full))))
        self.assertEqual(by_path[1]["read_file"], LAW)

    def test_a_spilled_grep_read_back_counts_for_seen_only(self):
        spilled = GREP + "\n[Output spilled. Read artifact://3 for full output]"
        obs = ot.omp_observations(records(body((call("c0", "grep", pattern="x", path="."), spilled),
                                               (call("c1", "read", path="artifact://3"), GREP))))
        self.assertIsNone(obs[1]["read_file"])
        self.assertIn(ANCHOR, obs[1]["lines"][LAW])
        self.assertEqual(hits(obs), {"seen": True, "read": False, "opened": False})

    def test_a_shaken_result_reached_the_model_only_as_a_stub(self):
        # compaction elided the fresh read before any request carried it: opened, not read
        stub = "[shaken ~127 tokens — recover: artifact://0 (region 2)]"
        obs = ot.omp_observations(records(body((call("c0", "read", path=LAW), stub))))
        self.assertEqual(obs[0]["lines"], {LAW: []})
        self.assertEqual(hits(obs), {"seen": False, "read": False, "opened": True})

    def test_the_first_copy_of_a_result_wins_over_a_later_stub(self):
        result = f"{ANCHOR}\n1. Công dân"
        first = body((call("c0", "read", path=f"{LAW}:61-80"), result))
        shaken = body((call("c0", "read", path=f"{LAW}:61-80"), "[shaken ~90 tokens — recover: artifact://1 (region 1)]"))
        obs = ot.omp_observations(records(first, shaken))
        self.assertEqual(hits(obs), {"seen": True, "read": True, "opened": True})

    def test_selector_counts(self):
        obs = ot.omp_observations(records(body((call("c0", "read", path=f"{LAW}:61-80"), ANCHOR),
                                               (call("c1", "grep", pattern="x", skip=20), GREP),
                                               (call("c2", "read", path="khong-co.txt"), "Path 'khong-co.txt' not found"))))
        self.assertEqual(ot.selectors(obs), {"read_whole": 0, "read_range": 1, "read_spill": 0, "grep_next_page": 1})


if __name__ == "__main__":
    unittest.main()
