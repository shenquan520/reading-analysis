#!/usr/bin/env python3
"""build_cards_batch.py — 从 references/cards/ 生成网站 cards 集合的整批导入 JSON

用法：python build_cards_batch.py [--version v20260910] [--src references/cards] [--out dist]
产出：<out>/cards_batch_<version>.json（card_id/title/content/cards_version）
      <out>/card_names_<version>.json（card_id -> title 映射，便利贴标题用）

约定：卡文件名以数字开头（A/B 系）或 R<数字>（R 系）；INDEX / card-template / 00-index 不入批次。
"""
import argparse, io, json, os, re
from collections import Counter

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="v20260910")
    ap.add_argument("--src", default="references/cards")
    ap.add_argument("--out", default="dist")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

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
            cards.append({"card_id": cid, "title": title, "content": s, "cards_version": a.version})
            names[cid] = title

    cards.sort(key=lambda c: (c["card_id"][0], int(re.sub(r"\D", "", c["card_id"]))))
    p1 = os.path.join(a.out, f"cards_batch_{a.version}.json")
    p2 = os.path.join(a.out, f"card_names_{a.version}.json")
    io.open(p1, "w", encoding="utf-8").write(json.dumps(
        {"cards_version": a.version, "total": len(cards), "cards": cards}, ensure_ascii=False, indent=1))
    io.open(p2, "w", encoding="utf-8").write(json.dumps(names, ensure_ascii=False, indent=1))
    dist = dict(Counter(x["card_id"][0] for x in cards))
    dups = [i for i, n in Counter(x["card_id"] for x in cards).items() if n > 1]
    print(f"生成 {len(cards)} 张（{dist}）-> {p1}")
    print(f"卡名映射 {len(names)} 条 -> {p2}")
    if dups: print("!! 重复 id:", dups)
    if skipped: print("跳过（无编号，如需入卡请先编号）:", skipped)

if __name__ == "__main__":
    main()
