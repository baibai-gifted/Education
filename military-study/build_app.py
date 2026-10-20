# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 baibai
"""Build an offline study page from an audited, unmodified source snapshot.

Inputs are source/questions-raw.json, source/extraction-audit.json and
app-template.html. Empty, inconsistent or unaudited inputs stop before writes.
Original source answers, explanations, citations, row identities and repeated
question numbers are retained. Review hints describe question features, not
historical error rates, and never supply a missing factual explanation.
"""

from __future__ import annotations

import argparse
import base64
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unicodedata
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent
MARKER = "/*__QUESTION_DATA__*/"
AVATAR_MARKER = "__AUTHOR_AVATAR_DATA_URI__"
EXPECTED_COUNT = 4733  # The count displayed by the linked source, not an extraction result.
SOURCE_URL = "https://www.kdocs.cn/l/coCdkuO5iIU8"
ALLOWED_TYPES = {"single", "multiple", "judge", "text"}

NEGATIVE = re.compile(
    r"不属于|不包括|不包含|不正确|不符合|不准确|不恰当|不应该|不应当|"
    r"不具有|不可能|不能|不是|错误的(?:是|有)|错误说法|不予|无关|不涉及|不适用"
)
NUMBERS = re.compile(
    r"\d+(?:[.．]\d+)?\s*(?:%|％|年|月|日|世纪|周年|年代|公里|千米|米|"
    r"万人|亿人|人|万|亿|次|条|项|个|级|倍|小时|分钟)|"
    r"第[一二三四五六七八九十百零〇0-9]+(?:次|个|条|届|代|阶段)"
)
DATE_WORDS = re.compile(r"哪一年|何年|何时|几月|几日|年代|世纪|时间|纪念日|成立于|颁布于|实施于")
ORDER = re.compile(r"最早|最先|首次|最初|先后|前后顺序|第一(?:次|个|位|部)|始于|起源于|先于|晚于")
CONCEPT = re.compile(r"根本|基本|核心|宗旨|本质|目的|任务|主体|主导|原则|方针|职能|基础|前提|关键|实质|首要")
ABSOLUTE = re.compile(r"一切|所有|全部|任何|只要|只有|必须|一定|必然|总是|始终|完全|绝对|唯一|只能|一律|绝不|永远|不得|从来|仅仅|一概")
PERSON = re.compile(r"哪位|谁(?:是|最先|首先|首次|提出|创立|建立|创作|发明|领导)|由谁|何人|创立者|创始人|提出者|奠基人|首创|首次提出|最早提出|首次使用")


def unique_hits(pattern: re.Pattern, value: str, limit: int = 4) -> list[str]:
    return list(dict.fromkeys(match.group(0).strip() for match in pattern.finditer(value)))[:limit]


def quote_hits(hits: list[str]) -> str:
    return "、".join(f"“{hit}”" for hit in hits)


def review_hints(question: dict) -> tuple[list[str], list[str]]:
    """Return concrete reading/memory advice only; infer no answer or fact."""
    if question["type"] not in {"single", "multiple", "judge"}:
        return [], []
    stem = question["stem"]
    option_text = "\n".join(option["text"] for option in question["options"])
    tags, reasons = [], []
    hits = unique_hits(NEGATIVE, stem)
    if hits:
        tags.append("否定表述")
        if question["type"] == "judge":
            reasons.append(f"题干含{quote_hits(hits)}，注意否定词指向的对象和范围，再结合原文核对；否定句本身不代表错误。")
        else:
            reasons.append(f"题干含{quote_hits(hits)}，注意否定范围，先辨清题目要求，再逐项核对选项。")
    hits = unique_hits(NUMBERS, stem + "\n" + option_text)
    date_hits = unique_hits(DATE_WORDS, stem)
    if hits or date_hits:
        tags.append("数字与时间")
        reasons.append(f"题面含{quote_hits((hits or date_hits)[:4])}，把数字、时间与对应事件或对象连在一起记，并核对单位和适用条件。")
    hits = unique_hits(ORDER, stem)
    if hits:
        tags.append("时间与先后")
        reasons.append(f"题干强调{quote_hits(hits)}，区分首次发生、提出、正式确立与后续发展，按题目要求核对先后。")
    hits = unique_hits(CONCEPT, stem)
    if hits:
        tags.append("概念边界")
        reasons.append(f"题干含{quote_hits(hits)}等限定，辨清题目问的是哪一层概念，不把相关表述直接当作同义答案。")
    if question["type"] == "judge":
        hits = unique_hits(ABSOLUTE, stem)
        if hits:
            tags.append("判断范围")
            reasons.append(f"判断句含{quote_hits(hits)}，核对它限定的对象、范围和前提；绝对词本身不能直接说明句子错误。")
    hits = unique_hits(PERSON, stem)
    if hits:
        tags.append("人物与贡献")
        reasons.append(f"题干含{quote_hits(hits)}，把人物或机构与具体贡献对应，分清提出、创立、领导和发展等不同关系。")
    return tags, reasons


def validate_inputs(raw: object, audit: object) -> list[dict]:
    if not isinstance(raw, list) or not raw:
        raise ValueError("原始题库为空或结构无效；不会覆盖现有 HTML 或题库。")
    if not isinstance(audit, dict) or audit.get("sourceUnchanged") is not True:
        raise ValueError("提取审计未确认源提取快照保持不变；停止构建。")
    if audit.get("questionCount") != len(raw):
        raise ValueError(f"原始题数 {len(raw)} 与审计题数 {audit.get('questionCount')} 不一致；停止构建。")
    ids = set()
    for offset, question in enumerate(raw, 1):
        if not isinstance(question, dict):
            raise ValueError(f"第 {offset} 项不是题目对象。")
        identifier = question.get("id")
        if not isinstance(identifier, str) or not identifier or identifier in ids:
            raise ValueError(f"第 {offset} 项缺少唯一行标识；禁止以重复题号代替或静默去重。")
        ids.add(identifier)
        sheet, row = question.get("sourceSheetIndex"), question.get("sourceRow")
        if isinstance(sheet, int) and isinstance(row, int):
            expected = f"s{sheet:02d}-r{row:06d}"
            if identifier != expected:
                raise ValueError(f"题目 {identifier} 与工作表/行身份 {expected} 不一致。")
        else:
            raise ValueError(f"题目 {identifier} 缺少原工作表序号或 Excel 行号。")
        if question.get("type") not in ALLOWED_TYPES:
            raise ValueError(f"题目 {identifier} 的题型无效。")
        for field in ("stem", "explanation", "sourceAnswer", "sourceCitation", "sourceRef"):
            if not isinstance(question.get(field), str):
                raise ValueError(f"题目 {identifier} 的原文字段 {field} 必须为字符串。")
        if not isinstance(question.get("options"), list) or any(
            not isinstance(option, dict) or not isinstance(option.get("key"), str)
            or not isinstance(option.get("text"), str) for option in question["options"]
        ):
            raise ValueError(f"题目 {identifier} 的选项结构无效。")
        if not isinstance(question.get("answer"), (list, str)):
            raise ValueError(f"题目 {identifier} 的答案结构无效。")
        if question.get("answerStatus") not in {"source", "review"}:
            raise ValueError(f"题目 {identifier} 缺少明确的答案状态。")
    return raw


def content_key(question: dict) -> str:
    # Exact text and exact option order: similar/reworded questions are not merged.
    return json.dumps([question["type"], question["stem"], question["options"]],
                      ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def answer_signature(question: dict) -> tuple | None:
    mapped = question.get("answer")
    if isinstance(mapped, list) and mapped:
        return "mapped", tuple(sorted(str(key) for key in mapped))
    if isinstance(mapped, str) and mapped.strip():
        return "text", mapped.strip()
    source = unicodedata.normalize("NFKC", question["sourceAnswer"]).strip()
    return ("unmapped_source", re.sub(r"\s+", "", source)) if source else None


def enrich_questions(raw: list[dict]) -> tuple[list[dict], list[dict]]:
    # raw is never modified. Source cell snapshots remain in questions-raw.json.
    questions = [{key: deepcopy(value) for key, value in question.items() if key != "sourceCells"}
                 for question in raw]
    groups = defaultdict(list)
    for question in questions:
        tags, reasons = review_hints(question)
        question["tags"] = list(dict.fromkeys([*question.get("tags", []), *tags]))
        question["pitfall"] = bool(reasons)
        question["pitfallReason"] = (
            "复习建议（根据题面特征整理，不代表实际错误率）：\n" + "\n".join(reasons)
            if reasons else ""
        )
        groups[content_key(question)].append(question)
    conflicts = []
    for key, group in groups.items():
        signatures = {signature for question in group
                      if (signature := answer_signature(question)) is not None}
        if len(signatures) < 2:
            continue
        group_id = "conflict-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
        conflicts.append({"groupId": group_id, "ids": [q["id"] for q in group],
                          "sourceRefs": [q["sourceRef"] for q in group],
                          "sourceAnswers": [q["sourceAnswer"] for q in group]})
        for question in group:
            question["answerStatus"] = "review"
            question["conflictGroupId"] = group_id
            peers = [q["sourceRef"] for q in group if q["id"] != question["id"]]
            displayed = "；".join(peers[:5]) + (f"；另 {len(peers) - 5} 条" if len(peers) > 5 else "")
            # Keep explanation unchanged; the UI displays this separate note.
            question["curationNote"] = (
                "整理提示：本题与其他来源行的题干、题型及选项完全相同，但原文答案存在不一致。"
                "已标为待核验，不自动判分；原文答案与解析均原样保留，未替你确定取舍。"
                + ("对应行：" + displayed + "。" if displayed else "")
            )
            question["tags"] = list(dict.fromkeys([*question["tags"], "原文答案冲突"]))
    return questions, conflicts


def add_learning_materials(questions: list[dict]) -> dict:
    """Apply separately attributed navigation and explanations; keep source fields."""
    by_id = {q["id"]: q for q in questions}
    modules_path = ROOT / "source" / "learning-modules.json"
    module_count = 0
    if modules_path.exists():
        modules = json.loads(modules_path.read_text(encoding="utf-8-sig"))
        if not isinstance(modules, dict) or set(modules) != set(by_id):
            raise ValueError("学习模块映射与原题 ID 集合不一致。")
        for identifier, module in modules.items():
            if not isinstance(module, str) or not module.strip() or len(module) > 36:
                raise ValueError(f"题目 {identifier} 的学习模块无效。")
            by_id[identifier]["sourceTopic"] = by_id[identifier]["topic"]
            by_id[identifier]["topic"] = module
        module_count = len(set(modules.values()))
    supplemented = set()
    official_hosts = {"81.cn", "www.81.cn", "mod.gov.cn", "www.mod.gov.cn",
                      "gov.cn", "www.gov.cn", "npc.gov.cn", "www.npc.gov.cn"}
    for filename in ("supplement-explanations-a.json", "supplement-explanations-b.json"):
        path = ROOT / "source" / filename
        if not path.exists():
            continue
        entries = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(entries, list):
            raise ValueError("补充解析必须为数组。")
        for entry in entries:
            identifier = entry.get("id") if isinstance(entry, dict) else None
            if identifier not in by_id or identifier in supplemented:
                raise ValueError(f"补充解析题目 ID 无效或重复：{identifier}")
            q = by_id[identifier]
            if q["explanation"].strip() or entry.get("sourceStem") != q["stem"]:
                raise ValueError(f"补充解析与原题不匹配，或试图覆盖原文解析：{identifier}")
            explanation = entry.get("explanation")
            citations = entry.get("citations")
            if not isinstance(explanation, str) or not explanation.strip() or not citations:
                raise ValueError(f"补充解析缺正文或出处：{identifier}")
            if not isinstance(citations, list) or not isinstance(entry.get("reviewRequired"), bool):
                raise ValueError(f"补充解析来源或核验状态无效：{identifier}")
            for citation in citations:
                if not isinstance(citation, dict):
                    raise ValueError(f"补充解析来源格式无效：{identifier}")
                url = urlparse(citation.get("url", ""))
                if url.scheme != "https" or url.hostname not in official_hosts:
                    raise ValueError(f"补充解析缺少合法官方出处：{identifier}")
                if not citation.get("title") or not citation.get("article"):
                    raise ValueError(f"补充解析缺官方文件名或具体条号：{identifier}")
            q["supplementalExplanation"] = explanation.strip()
            q["supplementalCitations"] = citations
            q["explanationKind"] = "supplement"
            if entry["reviewRequired"]:
                reason = entry.get("reviewReason", "").strip()
                if not reason:
                    raise ValueError(f"待核验解析未说明原因：{identifier}")
                q["answerStatus"] = "review"
                q["curationNote"] = (q.get("curationNote", "") + "\n整理核对：" + reason).strip()
                q["tags"] = list(dict.fromkeys([*q["tags"], "原答案待核验"]))
                q["pitfall"] = True
                q["pitfallReason"] = (q.get("pitfallReason", "") + "\n注意：" + reason).strip()
            supplemented.add(identifier)
    return {"supplementedExplanationCount": len(supplemented),
            "effectiveMissingExplanationCount": sum(
                not q["explanation"].strip() and not q.get("supplementalExplanation", "").strip()
                for q in questions),
            "learningModuleCount": module_count,
            "learningModuleCounts": dict(Counter(q["topic"] for q in questions))}


def make_bank(raw: list[dict], audit: dict, title: str,
              expected_count: int = EXPECTED_COUNT) -> dict:
    validate_inputs(raw, audit)
    questions, conflicts = enrich_questions(raw)
    additions = add_learning_materials(questions)
    count = len(questions)
    missing = {
        "stem": sum(not q["stem"].strip() for q in questions),
        "answer": sum(not q["sourceAnswer"].strip() for q in questions),
        "explanation": sum(not q["explanation"].strip() for q in questions),
        "citation": sum(not q["sourceCitation"].strip() for q in questions),
    }
    review_count = sum(q["answerStatus"] == "review" for q in questions)
    hints_count = sum(q["pitfall"] for q in questions)
    conflict_count = sum(len(group["ids"]) for group in conflicts)
    if count == expected_count:
        count_note = f"收录 {count:,} 题，已与来源页面标示题量核对一致。"
    else:
        difference = "少于" if count < expected_count else "多于"
        count_note = f"完整性提醒：本次实际提取 {count:,} 题，{difference}来源页面标示 {expected_count:,} 题，题库完整性待确认。"
    missing_note = (
        f"原资料有 {missing['citation']} 题未标细分出处，均保留工作表行号以便溯源。"
    )
    source_note = (
        count_note + missing_note
        + "原文答案与解析按资料保留，未对全库逐题独立事实核验。"
        + f"原缺解析中已依据官方条令补充 {additions['supplementedExplanationCount']} 题，逐题标为补充解析并列明出处；仍缺 {additions['effectiveMissingExplanationCount']} 题。"
        + f"易混题 {hints_count:,} 道，依据否定问法、数字时间、先后、概念边界、判断范围与人物贡献等题面特征提供复习建议，不代表历史错误率。"
        + f"待核验 {review_count} 题，涉及答案冲突或题意歧义，不自动判分。"
        + "重复编号与重复题均保留，以原工作表和 Excel 行定位。学习模块为辅助归类，原章节及来源标注另行保留。"
    )
    return {
        "title": title,
        "sourceUrl": audit.get("sourceUrl") or SOURCE_URL,
        "sourceNote": source_note,
        "questions": questions,
        "integrity": {
            **additions,
            "actualQuestionCount": count,
            "sourcePageDisplayedCount": expected_count,
            "countMatchesSourcePage": count == expected_count,
            "completenessStatus": "count-matched-not-content-certified" if count == expected_count else "needs-confirmation",
            "missingCounts": missing,
            "countsByType": dict(Counter(q["type"] for q in questions)),
            "countsByAnswerStatus": dict(Counter(q["answerStatus"] for q in questions)),
            "preMarkedPitfallCount": hints_count,
            "pitfallBasis": "Question-feature review suggestions; no historical error-rate data was used.",
            "conflictGroupCount": len(conflicts),
            "conflictQuestionCount": conflict_count,
            "conflictingAnswerGroups": conflicts,
            "duplicateNumberGroupsRetained": len(audit.get("duplicateNumbers", [])),
            "sourceFilename": audit.get("sourceFilename", ""),
            "sourceEvidenceSha256": audit.get("sourceSha256After", ""),
            "acquisitionMethod": audit.get("acquisitionMethod", audit.get("sourceKind", "audited-source-extraction")),
            "sourceVersion": audit.get("sourceVersion", audit.get("snapshotDataVersion")),
            "sourceChecksumMeaning": audit.get(
                "sourceChecksumMeaning",
                audit.get("sourceUnchangedMeaning", "提取审计所描述的源证据快照的 SHA-256；不表示原始 XLSX 文件的校验值。"),
            ),
            "sourceUnchangedDuringExtraction": audit.get("sourceUnchanged"),
            "builtAtUtc": datetime.now(timezone.utc).isoformat(),
        },
    }


def render_html(template: str, bank: dict) -> str:
    if template.count(MARKER) != 1 or "const DATA = " + MARKER + ";" not in template:
        raise ValueError("HTML 模板必须且只能包含一个指定的 DATA 注入占位符。")
    if not bank.get("questions"):
        raise ValueError("题库为空；禁止输出空题库覆盖现有页面。")
    # '<' escaping also prevents an embedded </script> from terminating the block.
    payload = json.dumps(bank, ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    if template.count(AVATAR_MARKER) != 1:
        raise ValueError("HTML 模板必须且只能包含一个作者头像占位符。")
    avatar = (ROOT / "assets" / "author-avatar.jpg").read_bytes()
    if not avatar.startswith(b"\xff\xd8\xff"):
        raise ValueError("作者头像必须是有效的 JPEG 文件。")
    avatar_uri = "data:image/jpeg;base64," + base64.b64encode(avatar).decode("ascii")
    return template.replace(MARKER, payload, 1).replace(AVATAR_MARKER, avatar_uri, 1)


def write_outputs(contents: list[tuple[Path, str]]) -> None:
    """Prepare both complete files before replacing either existing output."""
    temporary = []
    try:
        for output, content in contents:
            output.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                             dir=output.parent, prefix=output.name + ".",
                                             suffix=".tmp", delete=False) as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
                temporary.append((Path(handle.name), output))
        for staging, output in temporary:
            os.replace(staging, output)
    finally:
        for staging, _ in temporary:
            if staging.exists():
                staging.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=ROOT / "source" / "questions-raw.json")
    parser.add_argument("--audit", type=Path, default=ROOT / "source" / "extraction-audit.json")
    parser.add_argument("--template", type=Path, default=ROOT / "app-template.html")
    parser.add_argument("--output-json", type=Path, default=ROOT / "source" / "questions.json")
    parser.add_argument("--output-html", type=Path, default=ROOT / "index.html")
    parser.add_argument("--title", default="军事理论 · 学习题库")
    parser.add_argument("--expected-count", type=int, default=EXPECTED_COUNT)
    args = parser.parse_args()
    try:
        raw = json.loads(args.raw.read_text(encoding="utf-8-sig"))
        audit = json.loads(args.audit.read_text(encoding="utf-8-sig"))
        bank = make_bank(raw, audit, args.title, args.expected_count)
        html = render_html(args.template.read_text(encoding="utf-8"), bank)
        # Every input must remain a read-only source, including custom CLI paths.
        inputs = {path.resolve() for path in (args.raw, args.audit, args.template)}
        outputs = [args.output_json.resolve(), args.output_html.resolve()]
        if len(set(outputs)) != 2 or any(path in inputs for path in outputs):
            raise ValueError("输出路径必须互不相同，且不得覆盖任一输入文件。")
        write_outputs([(outputs[0], json.dumps(bank, ensure_ascii=False, indent=2) + "\n"),
                       (outputs[1], html)])
        print(json.dumps({"outputs": [str(path) for path in outputs],
                          **{key: bank["integrity"][key] for key in (
                              "actualQuestionCount", "sourcePageDisplayedCount", "countMatchesSourcePage",
                              "missingCounts", "countsByType", "countsByAnswerStatus",
                              "preMarkedPitfallCount", "conflictGroupCount", "conflictQuestionCount")},
                          "htmlBytes": len(html.encode("utf-8"))}, ensure_ascii=False, indent=2))
        if not bank["integrity"]["countMatchesSourcePage"]:
            print("WARNING: 实际题数与来源页面标示不一致；页面已明确标注完整性待确认。", file=sys.stderr)
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"Build stopped: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
