#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_anti_patterns.py — 反模式系统的交付层门禁（可复跑）

用途：每次改动 ANTI-PATTERNS.md / build_standalone_analysis.py 后跑一次，
      确认「用户看得见的层」没坏——这是静态体检（skill_audit.py）抓不到的部分。

两道门禁：
  1) 空行检查：交付 HTML 里不得出现「标签有、值为空」的反模式行
     （成因见第四轮复验 F1：数据只填 3 行、渲染器固定输出 4 行）
  2) 误报检查：描述文章内容的正常说法，不得被判成「自述错误」
     并附「召回对照」——真实自述必须命中，防止为压误报把召回也压没了

用法：
    python verify_anti_patterns.py [--skill-root <skill 根目录>] [--analysis-dir <HTML 目录>]
默认 skill 根 = 本脚本所在目录的上一级；HTML 目录 = <skill 根>/dist/analysis
退出码：0 = 全绿；1 = 有门禁不过
"""
import argparse
import glob
import io
import os
import re
import sys


# —— 门禁 2 的两个样本集 ——
# 内容描述型：正常提问/描述文章，绝不能命中（否则等于把用户的提问曲解成认错）
DESC = [
    '这篇讲的是因果关系的文章', '帮我看看这段的并列结构', '这篇文章用了很多比喻',
    '我想知道第三段的定义是什么', '这篇文章讲的是人生哲理', '这篇讲竹子的',
    '我想知道第3段什么意思', '我这次全对了', '我读不懂第三段',
    '这段的因果关系是什么', '分析一下这句用了什么手法', '这篇文章的观点很中立',
    '它的论证用了让步', '这篇明明是讲创新的为什么选B', '我觉得这段结构是总分总',
]
# 真实自述：应命中至少一条（不必指定哪条，语义匹配由 agent 主路径负责）
SELF = [
    '我总把例子当主旨', '选项里明明有原文的词', '看到 but 我就选后面那个',
    '题干限定词我没看清', '我总把并列当成一样重要', '我一直分不清让步和转折',
    '我老是读长难句读到一半就忘', '我总被张冠李戴的选项骗',
    '对完答案发现我把因果搞反了', '我选B是因为原文说能防虫，看着挺对',
]

EMPTY_ROW_RE = re.compile(
    r'<span class="ap-k">(为什么错|症状|你这次的症状|怎么防)</span><span class="ap-v">\s*</span>')


def load_matcher(skill_root):
    """只加载渲染脚本的「定义段」，不执行交付主体（避免副作用）。"""
    fp = os.path.join(skill_root, "scripts", "build_standalone_analysis.py")
    src = io.open(fp, encoding="utf-8").read()
    head = src.split("# ===== 便签定义 =====")[0]
    ns = {"__file__": os.path.abspath(fp)}
    exec(compile(head, "build_standalone_analysis_head", "exec"), ns)
    return ns["load_anti_patterns"](), ns["match_anti_patterns"]


def gate_empty_rows(analysis_dir, extra_globs):
    files = sorted(set(glob.glob(os.path.join(analysis_dir, "*.html"))))
    for g in extra_globs:
        files += glob.glob(g, recursive=True)
    files = sorted(set(files))
    bad = []
    for fp in files:
        t = io.open(fp, encoding="utf-8").read()
        for m in EMPTY_ROW_RE.finditer(t):
            bad.append((os.path.basename(fp), m.group(1)))
    print("【门禁 1】反模式空行检查 —— 门禁值 0 处")
    print(f"  扫描 {len(files)} 个 HTML")
    if bad:
        for b in bad[:10]:
            print(f"  ❌ {b[0]}: 「{b[1]}」值为空")
    else:
        print("  ✅ 0 处")
    return not bad


def gate_matching(ap_index, matcher):
    print()
    print("【门禁 2】误报 / 召回 检查")
    print("  --- 内容描述型（应全部为空）---")
    fp = []
    for t in DESC:
        h = matcher(t, ap_index)
        if h:
            fp.append((t, h))
        print(f"    {t} -> {h if h else '空 ✅'}")
    print(f"  误报：{len(fp)}/{len(DESC)}", "✅ 全清" if not fp else "❌")
    print()
    print("  --- 对照：真实自述（应命中，防「修误报修出漏报」）---")
    fn = []
    for t in SELF:
        h = matcher(t, ap_index)
        if not h:
            fn.append(t)
        print(f"    {t} -> {h if h else '空 ❌'}")
    print(f"  漏报：{len(fn)}/{len(SELF)}", "✅ 全命中" if not fn else "❌")
    return (not fp) and (not fn)


def gate_field_integrity(ap_index):
    """字段齐整（对接审计工具 G30：字段写了但值为空 → 用户层空行/整行消失）"""
    need = ("keywords", "symptom", "why", "how", "card")
    bad = [(k, f) for k, v in ap_index.items() for f in need if not str(v.get(f, "")).strip()]
    print()
    print("【门禁 3】反模式字段齐整（五项必填，对接 G30）")
    if bad:
        for k, f in bad:
            print(f"  ❌ {k}：字段「{f}」为空")
    else:
        print(f"  ✅ {len(ap_index)} 条五项全有值")
    return not bad


def gate_pipeline(root):
    """门禁 4·管线冒烟：**通用交付管线**也必须能挂出反模式层。

    这一项是补历史的洞：反模式层曾只做在案例脚本里，通用管线（analysis_to_html.py）
    没有它 → 按 SKILL.md 走的正式交付根本不会出现反模式层。
    """
    import importlib.util
    fp = os.path.join(root, "scripts", "analysis_to_html.py")
    print()
    print("【门禁 4】通用管线冒烟（analysis_to_html.py 能否挂出反模式层）")
    if not os.path.isfile(fp):
        print("  ⚠️ 未找到 analysis_to_html.py，跳过")
        return True
    spec = importlib.util.spec_from_file_location("a2h", fp)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except SystemExit:
        pass
    base = {
        "title": "管线冒烟", "summary": {"theme": "t"},
        "passage": {"paragraphs": ["p1"], "functions": ["f1"]},
        "questions": [{"q": "q1", "answer": "B", "why": "w", "cards": []}],
        "review": {"takeaway": "k"},
    }
    cases = [
        # (名称, 追加字段, 期望有层, 期望复盘序号)
        ("不命中（应无层）", {}, False, "四"),
        ("自述命中（应有层）", {"user_note": "我总在这类题上翻车，看着挺对就选了"}, True, "五"),
        ("显式指定（应有层）", {"anti_patterns": [{"id": "AP-05"}]}, True, "五"),
    ]
    ok = True
    for name, extra, want_layer, want_sec in cases:
        d = dict(base)
        d.update(extra)
        html = mod.build(d)
        has = '<div class="ap-layer">' in html
        sec = re.findall(r'<h2>([一二三四五])、复盘</h2>', html)
        got_sec = sec[0] if sec else "?"
        empty = len(re.findall(r'<span class="ap-v">\s*</span>', html))
        good = (has == want_layer) and (got_sec == want_sec) and empty == 0
        ok = ok and good
        print(f"  {'✅' if good else '❌'} {name}：反模式层={'有' if has else '无'}（期望{'有' if want_layer else '无'}）"
              f"  复盘={got_sec}（期望{want_sec}）  空行={empty}")
    return ok


def main():
    ap = argparse.ArgumentParser()
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--skill-root", default=os.path.dirname(here))
    ap.add_argument("--analysis-dir", default=None,
                    help="交付 HTML 目录，默认 <skill-root>/dist/analysis")
    a = ap.parse_args()
    root = os.path.abspath(a.skill_root)
    adir = a.analysis_dir or os.path.join(root, "dist", "analysis")

    print("反模式系统 · 交付层门禁")
    print(f"skill 根：{root}")
    print("=" * 78)

    index, matcher = load_matcher(root)
    print(f"反模式表：解析到 {len(index)} 条")
    print()

    ok1 = gate_empty_rows(adir, [os.path.join(root, "**", "反模式*.html")])
    ok2 = gate_matching(index, matcher)
    ok3 = gate_field_integrity(index)
    ok4 = gate_pipeline(root)

    print()
    print("=" * 78)
    allok = ok1 and ok2 and ok3 and ok4
    print("结论：", "🟢 全绿" if allok else "🔴 有门禁不过")
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
