# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 baibai
"""Package the populated, self-contained study app for offline distribution."""

from pathlib import Path
import hashlib
import json
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent


def main():
    bank_path = ROOT / "source" / "questions.json"
    if not bank_path.is_file():
        raise SystemExit("尚无真实题库，停止打包。")
    bank = json.loads(bank_path.read_text(encoding="utf-8-sig"))
    questions = bank.get("questions", []) if isinstance(bank, dict) else bank
    if not questions:
        raise SystemExit("题库为空，停止打包。")
    if not isinstance(bank, dict) or not bank.get("integrity", {}).get("countMatchesSourcePage"):
        raise SystemExit("题数尚未与原资料核对一致，停止正式打包。")
    if any(not q.get("explanation", "").strip() and not q.get("supplementalExplanation", "").strip()
           for q in questions):
        raise SystemExit("仍有题目缺少解析，停止正式打包。")
    html = (ROOT / "index.html").read_text(encoding="utf-8-sig")
    if "/*__QUESTION_DATA__*/" in html or "const DATA =" not in html:
        raise SystemExit("HTML 尚未完成数据注入，停止打包。")
    start = html.index("const DATA =") + len("const DATA =")
    embedded, _ = json.JSONDecoder().raw_decode(html[start:].lstrip())
    if len(embedded.get("questions", [])) != len(questions):
        raise SystemExit("HTML 题数与整理数据不一致，停止打包。")
    count = len(questions)
    for required in ("LICENSE", "NOTICE.md"):
        if not (ROOT / required).is_file():
            raise SystemExit(f"缺少分发许可文件：{required}")
    pitfalls = sum(q.get("pitfall") is True for q in questions)
    review = sum(q.get("answerStatus") == "review" for q in questions)
    supplements = sum(bool(q.get("supplementalExplanation")) for q in questions)
    readme = (
        "知序 · 军事理论刷题\n\n"
        "使用方法\n"
        "1. 将 ZIP 全部解压到一个文件夹。\n"
        "2. 用 Edge、Chrome 或其他现代浏览器打开 index.html。\n"
        "3. 选择章节、题型、顺序或随机练习，独立作答后提交查看答案与解析。\n\n"
        f"本包包含 {count} 道原题，预标易混题 {pitfalls} 道，答案待核验 {review} 道。\n"
        "易混题依据问法、数字时间、概念边界等特征整理，不代表历史错误率。\n"
        "待核验题只提供参考，不参与自动判分。多选题须完整选对。\n"
        f"原资料缺失的 {supplements} 题解析已依据公开官方条令补充，逐题标注补充解析、条号及链接。\n"
        "原答案或同题答案有冲突的题仅供自查，不自动判分；原文答案均保留。\n"
        "来源中的全部答案不等于已经逐题独立事实核验。学习模块仅用于辅助导航。\n\n"
        "学习记录\n"
        "答错会自动加入错题本，可手动加入或移出；收藏用于保存想复习的题。\n"
        "记录保存在各自浏览器里，不自动上传，不会随 ZIP 发给别人，也不跨设备同步。\n"
        "更换浏览器、移动 HTML 文件或清理浏览器数据可能影响记录，请定期导出 JSON 备份。\n"
        "在“数据与说明”中可以导入、导出学习记录。\n\n"
        "快捷键\n"
        "1–9 选择选项；Enter 提交或下一题；左右方向键切题；F 收藏；R 重练。\n\n"
        "本包只需 index.html，支持离线使用，无需安装或启动服务器。\n"
        "分享给别人时发送整个 ZIP 即可。\n\n"
        "作者：baibai；导航中的“作者”页可查看头像与版本下载链接。\n"
        "程序源码采用 AGPL-3.0-only，详见 LICENSE；第三方题库内容权利见 NOTICE.md。\n"
        "源码：https://github.com/baibai-gifted/Education/tree/main/military-study\n"
        "下载：https://github.com/baibai-gifted/Education/releases\n\n"
        "原资料：https://www.kdocs.cn/l/coCdkuO5iIU8\n"
    )
    bundle = ROOT / "军事理论刷题包.zip"
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.write(ROOT / "index.html", "军事理论刷题/index.html")
        z.writestr("军事理论刷题/使用说明.txt", readme.encode("utf-8-sig"))
        for filename in ("LICENSE", "NOTICE.md"):
            z.write(ROOT / filename, "军事理论刷题/" + filename)
    with tempfile.TemporaryDirectory(prefix="study-package-", dir=ROOT) as directory:
        restored_root = Path(directory).resolve()
        if restored_root.parent != ROOT or not restored_root.name.startswith("study-package-"):
            raise SystemExit("解压校验临时目录未处于工作目录内。")
        with zipfile.ZipFile(bundle) as z:
            expected = {"军事理论刷题/index.html", "军事理论刷题/使用说明.txt",
                        "军事理论刷题/LICENSE", "军事理论刷题/NOTICE.md"}
            if set(z.namelist()) != expected or z.testzip() is not None:
                raise SystemExit("压缩包校验失败。")
            z.extractall(directory)
        original = (ROOT / "index.html").read_bytes()
        restored = (Path(directory) / "军事理论刷题" / "index.html").read_bytes()
        if hashlib.sha256(original).digest() != hashlib.sha256(restored).digest():
            raise SystemExit("解压后的 HTML 校验失败。")
        for filename in ("LICENSE", "NOTICE.md"):
            if (ROOT / filename).read_bytes() != (restored_root / "军事理论刷题" / filename).read_bytes():
                raise SystemExit(f"解压后的许可文件校验失败：{filename}")
    print(json.dumps({"path": str(bundle), "questions": count,
                      "pitfalls": pitfalls, "review": review,
                      "bytes": bundle.stat().st_size,
                      "sha256": hashlib.sha256(bundle.read_bytes()).hexdigest(),
                      "archiveAndRestoreCheck": "PASS"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
