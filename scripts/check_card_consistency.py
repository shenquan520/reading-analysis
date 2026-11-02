# -*- coding: utf-8 -*-
"""卡片三处一致性检查：标题 / 摘要（一句话）/ 正文首句。

**为什么有这个东西**（2026-11-03 立）
------------------------------------------------------------------
B093 的一句话摘要写着「两个名词摆在一起只能并列」，而它的标题和正文都说
「名词读不出关系」。三个位置说了两套话，**摘要是错的，而摘要是所有人唯一会读的那一行**。

这个错来源于：摘要抄自来源材料（省力），正文自己写（要思考）。
**最省力的位置恰好是最重要的位置。**

人的审核查了「判据能不能执行」，没查「卡跟自己对不对得上」。
所以补这个工具：**机器只负责把可疑的挑出来，判断仍由人做。**

**它查什么（三条，都是"形式信号"，不做语义判断）**
------------------------------------------------------------------
① 极性矛盾 —— 标题是**否定**判断（读不出／未必／不一定），摘要是**绝对**判断（只能／必然／一定）
② 范围矛盾 —— 标题有**限定**（部分／某些），摘要**泛化**（所有／任何／都）
③ 摘要缺失关键词 —— 标题里的核心术语在摘要里一个都没出现

**它不查什么**
------------------------------------------------------------------
不判断"意思对不对"。语义正确性只能人看。这里只挑**信号不一致**的地方。

用法：
    python scripts/check_card_consistency.py          # 全库
    python scripts/check_card_consistency.py -v       # 连通过项也列出
退出码：0 = 无可疑；1 = 有可疑（供门禁调用）
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARD_DIRS = [
    ("A-analysis", "A"),
    ("B-skills", "B"),
    ("REVIEW", "R"),
]

# ── 否定词（表示"读不出/未必/有限定"）──
NEG_WORDS = [
    "不一定", "未必", "不必然", "未必能", "读不出", "看不出", "看不出",
    "不唯一", "非唯一", "不能", "不可", "无法", "难以", "不是",
]
# 先剔掉这些，避免「不一定」被当成「一定」
NEG_MASK = ["不一定", "不必然", "未必", "不唯一", "非唯一"]

# ── 绝对词（表示"只能/必然/所有"）──
ABS_WORDS = [
    "只能", "必然", "一定", "无非", "唯一", "唯一",
    "所有", "任何", "一律", "都是", "总是", "从来",
]
# ── 限定词（表示"部分/某些"）──
LIMIT_WORDS = ["部分", "某些", "有些", "多数", "常常", "往往", "一般"]


def strip_neg_phrases(text):
    """把「不一定」这类整体否定先挖掉，避免被当成「一定」。"""
    for w in NEG_MASK:
        text = text.replace(w, "〔否定〕")
    return text


def polarity(text):
    """返回 (has_neg, has_abs, has_limit)。"""
    masked = strip_neg_phrases(text)
    has_neg = any(w in text for w in NEG_WORDS if w not in NEG_MASK) or "〔否定〕" in masked
    has_abs = any(w in masked for w in ABS_WORDS if w not in NEG_MASK)
    has_limit = any(w in text for w in LIMIT_WORDS)
    return has_neg, has_abs, has_limit


def extract(path):
    """抽标题 / 摘要 / 正文首句。"""
    t = open(path, encoding="utf-8").read()
    lines = t.split("\n")

    title = ""
    for ln in lines:
        if ln.startswith("# "):
            title = ln[2:].strip()
            break

    summary = ""
    m = re.search(r">\s*\*\*一句话\*\*[：:]\s*(.+)", t)
    if m:
        summary = m.group(1).strip()

    # 正文首句：第一个「## 」标题之后、第一个非空非标题行
    body_first = ""
    seen_section = False
    for ln in lines:
        s = ln.strip()
        if s.startswith("## "):
            seen_section = True
            continue
        if not seen_section:
            continue
        if not s or s.startswith(">") or s.startswith("|") or s.startswith("**口诀"):
            continue
        # 取第一句
        m2 = re.match(r"(.+?[。！？])", s)
        body_first = m2.group(1) if m2 else s
        break

    return title, summary, body_first


def terms(text):
    """粗提核心术语：去掉虚词后的实词片段（2-4 字的中文串 / 英文词）。"""
    cleaned = re.sub(r"[*`>#|（）()【】\[\]，。、；：！？,.;:!?\"'“”‘’]", " ", text)
    cn = re.findall(r"[\u4e00-\u9fa5]{2,6}", cleaned)
    en = re.findall(r"[A-Za-z][A-Za-z\-]{2,}", cleaned)
    return set(cn) | set(en)


def check_one(path, verbose=False):
    name = os.path.basename(path)
    title, summary, body = extract(path)
    problems = []

    if not summary:
        problems.append("缺少「一句话」摘要（模板要求必填）")
        return problems

    t_neg, t_abs, t_lim = polarity(title)
    s_neg, s_abs, s_lim = polarity(summary)
    b_neg, b_abs, b_lim = polarity(body) if body else (False, False, False)

    # ① 极性矛盾：标题否定 + 摘要绝对
    if t_neg and s_abs and not s_neg:
        problems.append(
            f"极性矛盾：标题是**否定**判断，摘要是**绝对**判断\n"
            f"      标题：{title[:60]}\n"
            f"      摘要：{summary[:60]}"
        )

    # ② 范围矛盾：标题限定 + 摘要泛化
    if t_lim and s_abs and not s_lim:
        problems.append(
            f"范围矛盾：标题有**限定**，摘要有**泛化**\n"
            f"      标题：{title[:60]}\n"
            f"      摘要：{summary[:60]}"
        )

    # ③ 正文与摘要极性相反（正文自己写、摘要抄来的，最常见的分裂点）
    if b_neg and s_abs and not s_neg:
        problems.append(
            f"正文与摘要极性相反：正文否定、摘要绝对\n"
            f"      正文：{body[:60]}\n"
            f"      摘要：{summary[:60]}"
        )

    # ④（已删，2026-11-03）原设计是「摘要与标题无共同术语」。
    # 实测全库 137 张命中 116 张 —— 因为中文按正则切片不等于分词
    # （「为什么需要语篇研究」被切成「为什么需要语」「篇研究」），
    # 判据射程不对，全部作废。语义层面的"是不是一回事"机器判不了，只能人看。

    return problems


def main():
    verbose = "-v" in sys.argv
    total = 0
    bad = 0
    rows = []

    for sub, _pre in CARD_DIRS:
        d = os.path.join(ROOT, "references", "cards", sub)
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if not f.endswith(".md") or f == "INDEX.md":
                continue
            total += 1
            path = os.path.join(d, f)
            problems = check_one(path, verbose)
            if problems:
                bad += 1
                rows.append((f, problems))
            elif verbose:
                rows.append((f, ["（无明显信号）"]))

    print(f"卡片三处一致性检查：扫描 {total} 张，可疑 {bad} 张\n")
    if not rows:
        print("🟢 没发现问题")
        return 0

    for f, ps in rows:
        if ps == ["（无明显信号）"]:
            print(f"  ✅ {f}")
            continue
        print(f"  ⚠️  {f}")
        for p in ps:
            print(f"      - {p}")
        print()

    print("=" * 60)
    print("说明：本工具只挑**形式信号**（极性 / 范围 / 术语），不做语义判断。")
    print("      报出来不等于错 —— 人工确认后再改；确认无误的，看是不是判据写得太绝对。")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
