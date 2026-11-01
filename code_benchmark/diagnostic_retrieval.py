"""Corpus v0 and lexical retrieval for arms K and KS (openspec change diagnostic-prospective-campaign,
tasks 7.2-7.3; design Decisions 7 and 11).

Corpus v0 is the full text of the documents the adjudicated audit cites for the evidence anchors plus
distractor documents (data/diagnostic_prospective_v1/corpus_v0_sources.json), chunked by article ("Điều").
Retrieval is deterministic BM25 over those articles under a hashed configuration (retrieval_v0.json). Raw
pages, the corpus and the retrieved-evidence records stay under the ignored all_res/.
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
import urllib.request
from collections import Counter
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

try:
    from code_benchmark import diagnostic_prospective as dp
    from code_benchmark import vi_multimodel as v1
except ImportError:  # executed from code_benchmark/
    import diagnostic_prospective as dp
    import vi_multimodel as v1

SOURCES_PATH = dp.DATA_DIR / "corpus_v0_sources.json"
CONFIG_PATH = dp.DATA_DIR / "retrieval_v0.json"
CORPUS_DIR = dp.ROOT / "all_res" / "diagnostic_prospective" / "corpus_v0"
RETRIEVAL_DIR = dp.ROOT / "all_res" / "diagnostic_prospective" / "retrieval"
ROLES = ("cited", "cited_other", "predecessor")
# The source site serves an empty body to unknown clients, so the fetcher presents a common browser.
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
CHUNK_KEYS = ("chunk_id", "doc_id", "doc_title", "article", "locator", "text", "text_sha256", "source_ref")
_ARTICLE_HEAD = re.compile(r"^Điều\s+(\d+[a-zđ]?)\s*[.:]", re.IGNORECASE)
_LOCATOR_ARTICLE = re.compile(r"^Điều\s+(\d+[a-zđ]?)\b", re.IGNORECASE)
_DIEU_TAG = re.compile(r"<(/?)dieu\b[^>]*>", re.IGNORECASE)
# The page scripts mention "<dieu>" in comments, so scripts, styles and comments go before tags are read.
_NON_CONTENT = re.compile(r"<script\b.*?</script\s*>|<style\b.*?</style\s*>|<!--.*?-->", re.IGNORECASE | re.DOTALL)
_OPTION = re.compile(r"^([A-E])\.\s+(.+)$")
_WORD = re.compile(r"\w+")
_BLOCK_TAGS = frozenset({"p", "br", "div", "tr", "li", "table", "h1", "h2", "h3", "h4", "h5", "h6", "khoan", "diem"})
_MIN_VERBATIM_CHARS = 30


def _fail(message: str) -> SystemExit:
    return SystemExit(f"Error: {message}")


def _load_json_bytes(path: Path, label: str) -> tuple[Any, str]:
    try:
        raw = path.read_bytes()
        return json.loads(raw), v1.sha256_bytes(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise _fail(f"cannot read {label} {path}: {exc}") from exc


# ---------------------------------------------------------------- sources and configuration

def load_sources(path: Path = SOURCES_PATH) -> tuple[dict[str, Any], str]:
    """The corpus document list and its SHA-256. Fails closed on duplicates, unknown roles or non-https URLs."""
    sources, digest = _load_json_bytes(path, "corpus sources")
    documents = sources.get("documents") if isinstance(sources, dict) else None
    if not isinstance(documents, list) or not documents:
        raise _fail(f"{path.name}: documents must be a non-empty list")
    ids = [document.get("doc_id") for document in documents]
    if len(set(ids)) != len(ids):
        raise _fail(f"{path.name}: duplicate doc_id")
    cited = {document["doc_id"] for document in documents if document.get("role") == "cited"}
    for document in documents:
        where = f"{path.name}: {document.get('doc_id')}"
        if document.get("role") not in ROLES:
            raise _fail(f"{where}: role must be one of {list(ROLES)}")
        if not all(isinstance(document.get(key), str) and document[key].strip() for key in ("doc_id", "title", "url")):
            raise _fail(f"{where}: doc_id, title and url are required")
        if not document["url"].startswith("https://"):
            raise _fail(f"{where}: sources are fetched over https only")
        if (document["role"] == "predecessor") != ("predecessor_of" in document):
            raise _fail(f"{where}: predecessor_of is required for a predecessor and only for one")
        if document["role"] == "predecessor" and document["predecessor_of"] not in cited:
            raise _fail(f"{where}: predecessor_of names no cited document")
    return sources, digest


def load_config(path: Path = CONFIG_PATH) -> tuple[dict[str, Any], str]:
    """The retrieval configuration and the SHA-256 of its bytes (the registered retrieval_config_sha256)."""
    config, digest = _load_json_bytes(path, "retrieval configuration")
    bm25 = config.get("bm25") if isinstance(config, dict) else None
    if (not isinstance(bm25, dict) or config.get("unit") != "article" or config.get("query") != "mc_body"
            or not isinstance(config.get("bigrams"), bool) or not isinstance(config.get("top_k"), int)
            or config["top_k"] < 1 or not all(isinstance(bm25.get(key), (int, float)) for key in ("k1", "b"))):
        raise _fail(f"{path.name}: expected unit=article, query=mc_body, bigrams, top_k >= 1 and bm25.k1/b")
    return config, digest


def fetch(url: str, timeout: float = 60.0) -> bytes:
    if not url.startswith("https://"):
        raise _fail(f"corpus sources are fetched over https only: {url}")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "vi,en;q=0.8"})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310 - https only, checked above
        return response.read()


# ---------------------------------------------------------------- articles

class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def html_to_text(fragment: str) -> str:
    """Visible text of an HTML fragment, one line per block, NFC, single spaces, no empty lines."""
    parser = _Text()
    parser.feed(fragment)
    parser.close()
    text = unicodedata.normalize("NFC", "".join(parser.parts)).replace("\xa0", " ")
    lines = (re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in text.split("\n"))
    return "\n".join(line for line in lines if line)


def parse_articles(page: str) -> list[tuple[str, str]]:
    """The top-level <dieu> elements of a document page, in order, as (article number, text).

    The page's table of contents lists article titles outside these elements, and an article that quotes
    another (an amending article) keeps the quoted one in its own text. Fails closed on a page without
    articles, an element that does not open with its heading, an unclosed element or a repeated number."""
    articles: list[tuple[str, str]] = []
    depth = start = 0
    page = _NON_CONTENT.sub("", page)
    for match in _DIEU_TAG.finditer(page):
        if match.group(1) != "/":
            if depth == 0:
                start = match.end()
            depth += 1
        elif depth:
            depth -= 1
            if depth == 0:
                text = html_to_text(page[start:match.start()])
                head = _ARTICLE_HEAD.match(text)
                if not head:
                    raise _fail(f"an article element does not open with its heading: {text[:60]!r}")
                articles.append((head.group(1).lower(), text))
    if depth:
        raise _fail("the page ends inside an article element")
    if not articles:
        raise _fail("the page has no article elements")
    numbers = [number for number, _ in articles]
    repeated = sorted({number for number in numbers if numbers.count(number) > 1})
    if repeated:
        raise _fail(f"repeated article numbers {repeated[:5]}")
    return articles


def document_chunks(document: dict[str, Any], page: str) -> list[dict[str, Any]]:
    return [{"chunk_id": f"{document['doc_id']}#dieu-{number}", "doc_id": document["doc_id"],
             "doc_title": document["title"], "article": number, "locator": f"Điều {number}", "text": text,
             "text_sha256": v1.sha256_bytes(text.encode("utf-8")), "source_ref": document["url"]}
            for number, text in parse_articles(page)]


def load_corpus(corpus_dir: Path = CORPUS_DIR) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Chunks and manifest of a built corpus, verified against the manifest's corpus_sha256 and chunk hashes."""
    manifest, _ = _load_json_bytes(corpus_dir / "manifest.json", "corpus manifest")
    try:
        raw = (corpus_dir / "corpus.jsonl").read_bytes()
    except OSError as exc:
        raise _fail(f"cannot read corpus {corpus_dir}: {exc}") from exc
    if v1.sha256_bytes(raw) != manifest.get("corpus_sha256"):
        raise _fail(f"{corpus_dir.name}/corpus.jsonl does not match its manifest")
    chunks = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    for chunk in chunks:
        if set(chunk) != set(CHUNK_KEYS) or v1.sha256_bytes(chunk["text"].encode("utf-8")) != chunk["text_sha256"]:
            raise _fail(f"corpus chunk {chunk.get('chunk_id')} is malformed or its text hash differs")
    if len({chunk["chunk_id"] for chunk in chunks}) != len(chunks):
        raise _fail("duplicate corpus chunk ids")
    return chunks, manifest


# ---------------------------------------------------------------- BM25

def tokenize(text: str, bigrams: bool) -> list[str]:
    """Lower-cased NFC runs of word characters (Vietnamese syllables and numbers), plus adjacent pairs."""
    words = _WORD.findall(unicodedata.normalize("NFC", text).lower())
    return (words + [f"{a}_{b}" for a, b in zip(words, words[1:], strict=False)]) if bigrams else words


class BM25:
    """Okapi BM25 with Lucene's non-negative idf; each distinct query token counts once."""

    def __init__(self, documents: list[list[str]], k1: float, b: float) -> None:
        if not documents:
            raise _fail("BM25 needs at least one document")
        self.k1, self.b = float(k1), float(b)
        self.tf = [Counter(tokens) for tokens in documents]
        self.length = [len(tokens) for tokens in documents]
        self.average = sum(self.length) / len(documents) or 1.0
        df = Counter(term for counts in self.tf for term in counts)
        n = len(documents)
        self.idf = {term: math.log(1 + (n - count + 0.5) / (count + 0.5)) for term, count in df.items()}

    def scores(self, query: list[str]) -> list[float]:
        terms = [term for term in dict.fromkeys(query) if term in self.idf]
        result = []
        for counts, length in zip(self.tf, self.length, strict=True):
            norm = self.k1 * (1 - self.b + self.b * length / self.average)
            result.append(sum(self.idf[term] * counts[term] * (self.k1 + 1) / (counts[term] + norm)
                              for term in terms if term in counts))
        return result


@dataclass(frozen=True)
class Index:
    chunks: list[dict[str, Any]]
    bm25: BM25
    config: dict[str, Any]
    config_sha256: str
    corpus_sha256: str


def build_index(chunks: list[dict[str, Any]], manifest: dict[str, Any], config: dict[str, Any],
                config_sha256: str) -> Index:
    if manifest.get("corpus_id") != config.get("corpus_id"):
        raise _fail(f"retrieval configuration is for corpus {config.get('corpus_id')!r}, "
                    f"not {manifest.get('corpus_id')!r}")
    bm25 = BM25([tokenize(chunk["text"], config["bigrams"]) for chunk in chunks],
                config["bm25"]["k1"], config["bm25"]["b"])
    return Index(chunks, bm25, config, config_sha256, str(manifest["corpus_sha256"]))


def rank(index: Index, query: str) -> list[tuple[int, float]]:
    """(chunk position, score) for every chunk with a positive score, best first; ties keep corpus order."""
    scores = index.bm25.scores(tokenize(query, index.config["bigrams"]))
    return sorted(((position, score) for position, score in enumerate(scores) if score > 0),
                  key=lambda pair: (-pair[1], pair[0]))


def mc_query(item: v1.EvalItem) -> str:
    """The request-time text of a multiple-choice item: its question and options, without the instruction."""
    parts = dp.parse_frozen_prompt(item)
    if parts.kind != "mc":
        raise _fail(f"{item.run_key}: retrieval queries are defined for multiple-choice items only")
    return parts.body


def retrieved_record(index: Index, item: v1.EvalItem, required_sufficiency: str) -> dict[str, Any]:
    """One arm-K record: the top-k articles as provisions plus the ranking that produced them."""
    query = mc_query(item)
    top = rank(index, query)[:index.config["top_k"]]
    if not top:
        raise _fail(f"{item.run_key}: no corpus article shares a token with the query")
    return {
        "dataset_id": item.dataset_id, "item_id": item.item_id,
        "provisions": [{key: index.chunks[position][key] for key in dp.PROVISION_KEYS} for position, _ in top],
        "ranking": [{"chunk_id": index.chunks[position]["chunk_id"], "score": round(score, 6),
                     "text_sha256": index.chunks[position]["text_sha256"]} for position, score in top],
        "query_sha256": v1.sha256_bytes(query.encode("utf-8")),
        "corpus_sha256": index.corpus_sha256, "retrieval_config_sha256": index.config_sha256,
        "eligibility": {"input_evidence_sufficiency": required_sufficiency},
    }


# ---------------------------------------------------------------- checks

def cited_articles(provisions: list[dict[str, Any]]) -> list[str]:
    """Chunk ids of the articles that oracle provisions come from, e.g. "79/2024/TT-BCA#dieu-37"."""
    cited = []
    for provision in provisions:
        match = _LOCATOR_ARTICLE.match(provision["locator"])
        if not match:
            raise _fail(f"cannot read an article number from locator {provision['locator']!r}")
        chunk_id = f"{provision['doc_id']}#dieu-{match.group(1).lower()}"
        if chunk_id not in cited:
            cited.append(chunk_id)
    return cited


def hit_report(index: Index, records: list[dict[str, Any]], oracle: dict[str, list[dict[str, Any]]],
               items: dict[str, v1.EvalItem]) -> dict[str, Any]:
    """Whether each anchor's top k holds an article the reviewer cited, with the full-ranking position of each."""
    rows = []
    for record in records:
        key = dp.item_key(record["dataset_id"], record["item_id"])
        ranking = [index.chunks[position]["chunk_id"]
                   for position, _ in rank(index, mc_query(items[f"{key}:{dp.MAIN_REPLICATE}"]))]
        top = [entry["chunk_id"] for entry in record["ranking"]]
        cited = cited_articles(oracle[key])
        positions = {chunk_id: ranking.index(chunk_id) + 1 if chunk_id in ranking else None for chunk_id in cited}
        rows.append({"item_key": key, "cited": cited, "retrieved": top, "rank_of_cited": positions,
                     "hit": any(chunk_id in top for chunk_id in cited),
                     "cited_in_top_k": sum(chunk_id in top for chunk_id in cited)})
    return {"top_k": index.config["top_k"], "anchors": len(rows), "hits": sum(row["hit"] for row in rows),
            "misses": [row["item_key"] for row in rows if not row["hit"]], "per_anchor": rows}


def _normalized(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).lower().split())


def mc_question_and_options(item: v1.EvalItem) -> tuple[str, list[str]]:
    lines = mc_query(item).split("\n")
    first_option = next((n for n, line in enumerate(lines) if _OPTION.match(line)), len(lines))
    options = [match.group(2) for match in map(_OPTION.match, lines[first_option:]) if match]
    return "\n".join(lines[:first_option]), options


def leak_report(chunks: list[dict[str, Any]], items: list[v1.EvalItem]) -> dict[str, Any]:
    """Benchmark text in the corpus. A question copied verbatim or an answer-key line fails the corpus; an
    option copied verbatim is counted only, since options are often worded from the provision itself."""
    corpus = "\n".join(_normalized(chunk["text"]) for chunk in chunks)
    questions, options = [], 0
    for item in items:
        question, choices = mc_question_and_options(item)
        if len(_normalized(question)) >= _MIN_VERBATIM_CHARS and _normalized(question) in corpus:
            questions.append(dp.item_key(item.dataset_id, item.item_id))
        options += sum(len(_normalized(text)) >= _MIN_VERBATIM_CHARS and _normalized(text) in corpus
                       for text in choices)
    answer_keys = [chunk["chunk_id"] for chunk in chunks if dp.ANSWER_KEY.search(chunk["text"])]
    return {"items_checked": len(items), "questions_in_corpus": questions, "answer_key_chunks": answer_keys,
            "options_verbatim_in_corpus": options, "min_verbatim_chars": _MIN_VERBATIM_CHARS,
            "model_outputs": "not applicable: the corpus is built only from fetched pages",
            "passed": not questions and not answer_keys}


def oracle_crosscheck(chunks: list[dict[str, Any]], oracle: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Each oracle provision against the corpus article it cites: every line of it should occur there."""
    by_id = {chunk["chunk_id"]: _normalized(chunk["text"]) for chunk in chunks}
    rows = []
    for key, provisions in sorted(oracle.items()):
        for provision in provisions:
            chunk_id = cited_articles([provision])[0]
            article = by_id.get(chunk_id)
            lines = [_normalized(line) for line in provision["text"].split("\n") if line.strip()]
            missing = None if article is None else sum(line not in article for line in lines)
            rows.append({"item_key": key, "chunk_id": chunk_id, "article_in_corpus": article is not None,
                         "lines": len(lines), "lines_missing": missing})
    return {"provisions": len(rows), "all_found": all(row["article_in_corpus"] and row["lines_missing"] == 0
                                                      for row in rows), "per_provision": rows}
