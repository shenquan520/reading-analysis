#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_anti_patterns.py — 反模式系统的交付层门禁（可复跑）

用途：每次改动 ANTI-PATTERNS.md / anti_patterns.py / 任一渲染器后跑一次，
      确认「用户看得见的层」没坏——这是静态体检（skill_audit.py）抓不到的部分。

四道门禁：
  1) 空行检查：交付 HTML 里不得出现「标签有、值为空」的反模式行
     （成因见第四轮复验 F1：数据只填 3 行、渲染器固定输出 4 行）
  2) 匹配回归：用 **固定回归套件** `ap_cases.py` 跑（历史失败用例必须命中、误报必须为空）
     —— 套件是追加式的，每轮复验发现的漏报/误报都进去且永不删除（第六轮 K1）
  3) 字段齐整：36 条五项必须有值（对接审计工具 G30：字段空了用户层会出空行）
  4) 管线冒烟：**通用交付管线**也必须能挂出反模式层
     （第五轮教训：反模式层曾只做在案例脚本里 → 按规范走的交付根本不出现该层）

用法：
    python verify_anti_patterns.py [--skill-root <skill 根>] [--analysis-dir <HTML 目录>]
默认 skill 根 = 本脚本所在目录的上一级；HTML 目录 = <skill 根>/dist/analysis
退出码：0 = 全绿；1 = 有门禁不过
"""
import argparse
import glob
import importlib.util
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import anti_patterns as aps          # 纯模块、无副作用：直接 import（不再切分源码——第六轮 K3）
import ap_cases                      # 固定回归套件（追加式，历史用例永不删）

EMPTY_ROW_RE = re.compile(
    r'<span class="ap-k">(为什么错|症状|你这次的症状|怎么防)</span><span class="ap-v">\s*</span>')


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


def gate_matching(root):
    """门禁 2：跑固定回归套件（口径 = 生产：开闸）"""
    idx = aps.load_index(aps.index_path(root))
    print()
    print(f"【门禁 2】匹配回归套件（反模式 {len(idx)} 条；用例见 ap_cases.py）")
    suites = [
        ("历史失败用例（须命中）", ap_cases.HISTORY, True),
        ("实战自述（须命中）", ap_cases.SELF_REPORT, True),
        ("内容描述·本机（须为空）", ap_cases.NEUTRAL_DESC, False),
        ("内容描述·审核方（须为空）", ap_cases.NEUTRAL_REVIEWER, False),
        ("内容描述·加固（须为空）", ap_cases.NEUTRAL_HARD, False),
        ("关键词宽度试纸（须为空）", ap_cases.NEUTRAL_KEYWORD_WIDTH, False),
        ("真实误报回归（须为空）", ap_cases.REGRESSED_FP, False),
    ]
    ok = True
    for name, cases, should_hit in suites:
        miss = [t for t in cases if bool(aps.match(t, idx)) != should_hit]
        good = not miss
        ok = ok and good
        print(f"  {'✅' if good else '❌'} {name:24} {len(cases) - len(miss)}/{len(cases)}")
        for t in miss[:6]:
            print(f"        {'漏' if should_hit else '误'}：{t} -> {aps.match(t, idx) or '（空）'}")
    return ok


def gate_field_integrity(index):
    need = ("keywords", "symptom", "why", "how", "card")
    bad = [(k, f) for k, v in index.items() for f in need if not str(v.get(f, "")).strip()]
    print()
    print("【门禁 3】反模式字段齐整（五项必填，对接 G30）")
    if bad:
        for k, f in bad:
            print(f"  ❌ {k}：字段「{f}」为空")
    else:
        print(f"  ✅ {len(index)} 条五项全有值")
    return not bad


def gate_pipeline(root):
    """门禁 4：通用交付管线也必须能挂出反模式层（第五轮补的洞，防它长回来）"""
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
    ap.add_argument("--skill-root", default=os.path.dirname(HERE))
    ap.add_argument("--analysis-dir", default=None,
                    help="交付 HTML 目录，默认 <skill-root>/dist/analysis")
    a = ap.parse_args()
    root = os.path.abspath(a.skill_root)
    adir = a.analysis_dir or os.path.join(root, "dist", "analysis")

    print("反模式系统 · 交付层门禁")
    print(f"skill 根：{root}")
    print("=" * 78)

    index = aps.load_index(aps.index_path(root))
    print(f"反模式表：解析到 {len(index)} 条")
    print()

    ok1 = gate_empty_rows(adir, [os.path.join(root, "**", "反模式*.html")])
    ok2 = gate_matching(root)
    ok3 = gate_field_integrity(index)
    ok4 = gate_pipeline(root)

    print()
    print("=" * 78)
    allok = ok1 and ok2 and ok3 and ok4
    print("结论：", "🟢 全绿" if allok else "🔴 有门禁不过")
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
