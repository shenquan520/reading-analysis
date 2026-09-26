#!/usr/bin/env python3
"""build_cards_batch.py — 从 references/cards/ 生成网站 cards 集合的整批导入 JSON

用法：python build_cards_batch.py [--source reading] [--version reading-v20260926]
                                [--src references/cards] [--out dist]
产出：<out>/cards_batch_<version>.json（card_id/title/content/cards_version/source）
      <out>/card_names_<version>.json（card_id -> title 映射，便利贴标题用）

约定：卡文件名以数字开头（A/B 系）或 R<数字>（R 系）；INDEX / card-template / 00-index 不入批次。

★★ 版本号规范：**`<source>-v<YYYYMMDD>`**（2026-09-26 第十九轮补，代价是一次真事故）

  网站 `cards` 表里**阅读和翻译共表**，靠 `cards_version` 前缀区分：
      reading-v20260910（127 张） / trans-v20260910（191 张）
  而"整批替换"的逻辑是**删掉 cards_version ≠ 新版本**的记录。

  事故：本脚本曾产出 `v20260926`（**没有 source 前缀**）→ 若按它执行，
  判断式就是 `cards_version != 'v20260926'` → **`trans-v20260910` 也不等于它
  → 翻译的 191 张会被一起删掉**。而批次 JSON 原先**没有 `source` 字段**，
  网站端拿不到「只动阅读」的依据。（隔壁核查时发现，未造成损失。）

  → 现在：① 版本号**强制规范化**成 `<source>-v<日期>`，不合规就**自动纠正并告警**；
          ② 每张卡带 `source` 字段，让「只动哪一批」有据可依。
  **靠"记得那么写"挡不住，写进脚本才挡得住。**
"""
import argparse, datetime, io, json, os, re
from collections import Counter


def normalize_version(ver, source):
    """把版本号规范化成 `<source>-v<YYYYMMDD>`；不合规则纠正并返回 (新值, 告警)"""
    m = re.search(r"(\d{8})\s*$", ver or "")
    if not m:
        return ver, f"⚠️ 版本号 `{ver}` 里找不到 8 位日期，无法规范化"
    fixed = f"{source}-v{m.group(1)}"
    if ver == fixed:
        return ver, None
    return fixed, (f"⚠️ 版本号 `{ver}` 不符合规范 `<source>-v<日期>` → **已自动纠正为 `{fixed}`**\n"
                   f"   （旧写法会让「按版本整批替换」误删其它 source 的卡）")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="reading",
                    help="来源标识，须与网站 cards.source 一致（reading / translation）")
    ap.add_argument("--version", default=None,
                    help="完整版本号如 reading-v20260926；省略则用 <source>-v<今天>")
    ap.add_argument("--src", default="references/cards")
    ap.add_argument("--out", default="dist")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    ver = a.version or f"{a.source}-v{datetime.date.today():%Y%m%d}"
    ver, warn = normalize_version(ver, a.source)
    if warn:
        print(warn)

    cards, names, skipped = [], {}, []
    for root, dirs, fs in os.walk(a.src):
        dirs[:] = [d for d in dirs if d != "_archive"]
        for f in sorted(fs):
            if not f.endswith(".md") or "index" in f.lower() or f == "card-template.md":
                continue
            fp = os.path.join(root, f)
            rel = os.path.relpath(fp, a.src).replace("\\", "/")
            series = rel.split("/")[0]
            cid = None
            if series == "A-analysis" and (m := re.match(r"(\d+)", f)): cid = "A" + m.group(1)
            elif series == "B-skills" and (m := re.match(r"(\d+)", f)): cid = "B" + m.group(1)
            elif series == "REVIEW" and (m := re.match(r"R(\d+)", f)): cid = "R" + m.group(1)
            if not cid:
                skipped.append(rel); continue
            s = io.open(fp, encoding="utf-8").read()
            m = re.match(r"#\s*(.+)", s)
            title = m.group(1).strip() if m else cid
            cards.append({"card_id": cid, "title": title, "content": s,
                          "cards_version": ver, "source": a.source})
            names[cid] = title

    cards.sort(key=lambda c: (c["card_id"][0], int(re.sub(r"\D", "", c["card_id"]))))
    p1 = os.path.join(a.out, f"cards_batch_{ver}.json")
    p2 = os.path.join(a.out, f"card_names_{ver}.json")
    io.open(p1, "w", encoding="utf-8").write(json.dumps(
        {"cards_version": ver, "source": a.source, "total": len(cards), "cards": cards},
        ensure_ascii=False, indent=1))
    io.open(p2, "w", encoding="utf-8").write(json.dumps(names, ensure_ascii=False, indent=1))
    dist = dict(Counter(x["card_id"][0] for x in cards))
    dups = [i for i, n in Counter(x["card_id"] for x in cards).items() if n > 1]
    print(f"生成 {len(cards)} 张（{dist}）版本 {ver} 来源 {a.source} -> {p1}")
    print(f"卡名映射 {len(names)} 条 -> {p2}")
    if dups: print("!! 重复 id:", dups)
    if skipped: print("跳过（无编号，如需入卡请先编号）:", skipped)


if __name__ == "__main__":
    main()
