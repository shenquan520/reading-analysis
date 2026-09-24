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
    """门禁 2：匹配回归套件，**双口径如实报数**（第七轮 G31：只报开闸＝假绿）

    口径设计（诚实分工，别再自欺）：
      · 现实中性样本 —— **门禁**：开闸 0 误报 **且** 闭闸 0 误报
        （含义：关键词本身对「现实提问」就足够窄，不是全靠闸门兜着）
      · 概念名试纸   —— **诊断**：概念名是给 agent 的语义提示必须保留，
        它们会被正常提问打中，靠闸门挡 → 只报「开闸/闭闸」两个数，不设通过条件
    """
    idx = aps.load_index(aps.index_path(root))
    print()
    print(f"【门禁 2】匹配回归套件（反模式 {len(idx)} 条；用例见 ap_cases.py）")
    print(f"  {'样本集':24}{'条数':>5}{'开闸误报':>9}{'闭闸误报':>9}  判读")

    def line(name, cases, should_hit, mode):
        """mode 三档（语义要清楚，别把「生产口径硬门禁」写成「诊断」）：
          dual —— 开闸 **和** 闭闸都必须 0：本组关键词单独就得够窄（最硬的一档）
          prod —— 生产口径（开闸）必须 0；闭闸只报数：本组靠闸门或施事判定挡，属「该挡就该挡」
          diag —— 只报数不设阈值：本组是宽度指标（概念名必然出现在正常句里）
        """
        on_miss = [t for t in cases if bool(aps.match(t, idx, gate=True)) != should_hit]
        off_miss = [t for t in cases if bool(aps.match(t, idx, gate=False)) != should_hit]
        on_bad, off_bad = len(on_miss), len(off_miss)
        if should_hit:
            good = (on_bad == 0)
            verdict = "命中率" if good else f"漏 {on_miss[:3]}"
        elif mode == "dual":
            good = (on_bad == 0 and off_bad == 0)
            verdict = "关键词单独就够（闭闸也 0）" if good else \
                      (f"❌ 闭闸漏 {off_bad} 条：{off_miss[:2]}" if on_bad == 0 else f"❌ 开闸漏 {on_miss[:2]}")
        elif mode == "prod":
            good = (on_bad == 0)
            verdict = (f"生产口径 0（闭闸会命中 {off_bad}/{len(cases)}，由闸门/施事判定挡住）"
                       if good else f"❌ 开闸漏 {on_miss[:2]}")
        else:
            good = True
            verdict = f"诊断·宽度指标（闭闸命中 {off_bad}/{len(cases)}，不设阈值，上升即预警）"
        print(f"  {'✅' if good else '❌'} {name:22}{len(cases):>5}{on_bad:>9}{off_bad:>9}  {verdict}")
        return good

    ok = True
    # 命中侧（只看开闸口径）
    ok &= line("历史失败用例（须命中）", ap_cases.HISTORY, True, "prod")
    ok &= line("实战自述（须命中）", ap_cases.SELF_REPORT, True, "prod")
    # 误报侧·最硬一档：关键词单独就得够窄
    print("  --- 误报侧·【dual】关键词单独就得够窄（开闸与闭闸都必须 0）---")
    ok &= line("内容描述·本机", ap_cases.NEUTRAL_DESC, False, "dual")
    ok &= line("内容描述·审核方", ap_cases.NEUTRAL_REVIEWER, False, "dual")
    ok &= line("内容描述·加固", ap_cases.NEUTRAL_HARD, False, "dual")
    ok &= line("真实误报回归", ap_cases.REGRESSED_FP, False, "dual")
    # 误报侧·生产口径硬门禁：靠闸门 / 施事判定挡
    print("  --- 误报侧·【prod】生产口径必须 0（该挡就该挡；闭闸报数）---")
    ok &= line("评价文章·报告 8 条", ap_cases.NEUTRAL_EVAL, False, "prod")
    ok &= line("评价文章·他方 6 条", ap_cases.NEUTRAL_EVAL_OK, False, "prod")
    ok &= line("评价文章·冗长 4 条", ap_cases.NEUTRAL_EVAL_LONG, False, "prod")
    # 防御：施事判定最容易误伤「自述里合法提到段落」
    print("  --- 审核方第五轮 9 条真实自述（补登记；当时 4/9）---")
    ok &= line("第五轮·真实自述 9", ap_cases.ROUND5_SELF, True, "prod")
    print("  --- 审核方第九轮双向对照（施事判定四层定版）---")
    ok &= line("第九轮·评价文章 10", ap_cases.ROUND9_EVAL, False, "prod")
    ok &= line("第九轮·自述 12", ap_cases.ROUND9_SELF, True, "prod")
    print("  --- 防御·施事判定不得过杀（必须仍命中）---")
    ok &= line("话题句（对象词在前）", ap_cases.SELF_TOPIC_FIRST, True, "prod")
    ok &= line("自述 + 对象词（主语前置）", ap_cases.SELF_WITH_OBJECT, True, "prod")
    # 诊断：宽度指标
    print("  --- 误报侧·【diag】宽度指标（只报数，不设阈值）---")
    ok &= line("关键词宽度试纸", ap_cases.NEUTRAL_KEYWORD_WIDTH, False, "diag")
    # 有意不弹的记录（设计决定，报出来免得被当漏报去"修"）
    if getattr(ap_cases, "DELIBERATE_SKIP", None):
        print(f"  ℹ️ 有意不弹 {len(ap_cases.DELIBERATE_SKIP)} 条（设计决定，非漏报）")
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
    """门禁 4：通用交付管线也必须能挂出反模式层，且条幅文案要如实标注触发源

    · 第五轮补：反模式层曾只做在案例脚本里，通用管线没接 → 按规范走的交付根本不出现该层
    · 第六轮 L3 冷启动补：条幅曾硬编码「来自你自述的错误」，纯提问的交付也会这么写
      → 把「用户在提问」断言成「用户在认错」，是本系统最不能犯的错
    """
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
        ("不命中（应无层）", {}, False, "四", None),
        ("自述命中（应有层）", {"user_note": "我总在这类题上翻车，看着挺对就选了"}, True, "五", "自述"),
        ("显式指定（应有层）", {"anti_patterns": [{"id": "AP-05"}]}, True, "五", None),
        # ↓ 第六轮 L3 冷启动抓到的回归：纯提问 + 显式指定时，
        #   条幅曾硬编码成「来自你自述的错误」——把用户的提问断言成他在认错。
        ("纯提问+显式（条幅不得说自述）", {"user_note": "我想知道为什么选 B 不选 A",
                                          "anti_patterns": ["AP-04"]}, True, "五", "NOT_SELF"),
        ("显式声明来源＝错选项构造", {"anti_patterns": ["AP-04"], "ap_trigger": "错选项构造"},
         True, "五", "错选项构造"),
    ]
    ok = True
    for name, extra, want_layer, want_sec, want_src in cases:
        d = dict(base)
        d.update(extra)
        html = mod.build(d)
        has = '<div class="ap-layer">' in html
        sec = re.findall(r'<h2>([一二三四五])、复盘</h2>', html)
        got_sec = sec[0] if sec else "?"
        empty = len(re.findall(r'<span class="ap-v">\s*</span>', html))
        bar = re.search(r'<div class="ap-bar">([^<]*)</div>', html)
        got_bar = bar.group(1) if bar else ""
        src_ok = True
        if want_src == "NOT_SELF":
            src_ok = bool(got_bar) and ("自述" not in got_bar)
        elif want_src:
            # 用标签表精确比对（不要子串匹配：文案里可能多虚词，如「错选项的构造」）
            src_ok = got_bar == "⚠️ 反模式层 · " + aps.TRIGGER_LABELS[want_src]
        good = (has == want_layer) and (got_sec == want_sec) and empty == 0 and src_ok
        ok = ok and good
        note = f"  条幅={got_bar}" if got_bar else ""
        print(f"  {'✅' if good else '❌'} {name}：反模式层={'有' if want_layer else '无'}（期望{'有' if want_layer else '无'}）"
              f"  复盘={got_sec}（期望{want_sec}）  空行={empty}{note}")

    # —— 段落层 5 件套（第六轮 L3 冷启动补：管线只出 2 件，三个 agent 各自绕道）——
    print("  段落层 5 件套（SKILL 要求：原文/译文/段旨/段意概括/段间关系）")
    EN = "Concrete and asphalt absorb sunlight during the day."
    shapes = [
        ("items 写法", {"passage": {"items": [{"en": EN, "zh": "混凝土吸热。", "function": "现象引入",
                                               "summary": "热岛成因。", "relation": "为 P2 供前提。"}]}}),
        ("平行数组写法", {"passage": {"paragraphs": [EN], "functions": ["现象引入"],
                                      "translations": ["混凝土吸热。"], "summaries": ["热岛成因。"],
                                      "relations": ["为 P2 供前提。"]}}),
        # 按注释的字面写法：只给 paragraph_notes（段旨也在 note 里）。
        # 第八轮 M3：原 fixture 额外塞了 passage.functions，掩盖了「照字面写会丢段旨」的问题。
        ("paragraph_notes 写法（字面）", {"passage": {"paragraphs": [EN]},
                                        "paragraph_notes": [{"trans": "混凝土吸热。", "function": "现象引入",
                                                             "summary": "热岛成因。", "relation": "为 P2 供前提。"}]}),
    ]
    for name, extra in shapes:
        d = dict(base)
        d.update(extra)
        html = mod.build(d)
        got = {"原文": EN[:12] in html, "译文": "混凝土吸热。" in html,
               "段旨": "段旨" in html, "段意概括": "段意概括" in html, "段间关系": "段间关系" in html}
        good = all(got.values())
        ok = ok and good
        print(f"  {'✅' if good else '❌'} {name}：{sum(got.values())}/5",
              "" if good else f"缺 {[k for k, v in got.items() if not v]}")
    return ok


def gate_required_fields(root):
    """门禁 5：规范标「必填」的项，通用管线必须真承载（第十一轮 L3 冷启动补）

    三个洞（都是 L3 零记忆 agent 跑出来的，静态体检与差分抓不到）：
      ① **缺口栏 + 可迁移原则**：SKILL.md 要求「逐题必填」、且称缺口为「最值钱的产出」，
         而通用管线压根不承载（只有案例脚本有）→ 走通用管线的交付，缺口只能折进 why，机器不可校验。
         **这是同一个洞的第二次**（上一次是反模式层只做在案例脚本里）。
      ② **复盘前缀写死「错题归因：」**：无错题场景下前缀仍声称有错题
         （与第六轮修过的「条幅误归因」同类，当时只修了条幅那一处）。
      ③ **AP-02 × AP-03 共用词**：同一输入弹两张卡、其中一张不对题（互斥对治它）。

    ★ 判据一律**验到元素级**（数 `class="gap"` 这类元素），不 grep 关键字——
      恒定注入的 CSS 里也有同名 class 与注释，关键字搜索会全绿。
      这条方法论是审核方在 L3 里送回来的（他们的反例 agent 主动提醒）。
    """
    fp = os.path.join(root, "scripts", "analysis_to_html.py")
    print()
    print("【门禁 5】规范「必填」项在通用管线的承载力（缺口栏 / 复盘前缀 / 互斥对）")
    if not os.path.isfile(fp):
        print("  ⚠️ 未找到 analysis_to_html.py，跳过")
        return True
    spec = importlib.util.spec_from_file_location("a2h_rf", fp)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except SystemExit:
        pass

    base = {
        "title": "必填项冒烟", "summary": {}, "passage": {},
        "questions": [{"q": "q1", "answer": "B", "why": "w", "cards": []}],
        "review": {},
    }
    ok = True

    # ---- ① 缺口栏 + 可迁移原则（元素级）----
    d = dict(base, questions=[{"q": "q1", "answer": "B", "why": "w", "cards": [],
                               "gap": "某类题暂无判定规则，待立卡",
                               "transfer": "作用类题先问它控制了哪个变量"}])
    html = mod.build(d)
    n_gap = len(re.findall(r'<div class="gap">', html))
    n_note = len(re.findall(r'<div class="note">', html))
    empty_gap = len(re.findall(r'<div class="gap">\s*</div>', html))
    hit_gap = "▮缺口：" in html and "待立卡" in html
    hit_tr = "🎯 可迁移原则：" in html and "控制了哪个变量" in html
    good = (n_gap == 1 and n_note == 1 and empty_gap == 0 and hit_gap and hit_tr)
    ok = ok and good
    print(f"  {'✅' if good else '❌'} 缺口栏+可迁移原则：gap 元素={n_gap} note 元素={n_note} "
          f"空元素={empty_gap} 文案命中={hit_gap and hit_tr}")

    # 中文键也认（agent 常写中文键）
    d2 = dict(base, questions=[{"q": "q1", "answer": "B", "why": "w", "cards": [],
                                "缺口": "无", "可迁移原则": "x"}])
    h2 = mod.build(d2)
    good2 = len(re.findall(r'<div class="gap">', h2)) == 1
    ok = ok and good2
    print(f"  {'✅' if good2 else '❌'} 中文键（缺口/可迁移原则）同样承载：gap 元素={len(re.findall(r'<div class=.gap.>', h2))}")

    # 两项皆空 → 不产出占位符（交付物保持干净），但**要有告警**（不静默）
    d3 = dict(base, questions=[{"q": "q1", "answer": "B", "why": "w", "cards": []}])
    buf = io.StringIO()
    _old = sys.stderr
    sys.stderr = buf
    try:
        h3 = mod.build(d3)
    finally:
        sys.stderr = _old
    good3 = ('<div class="gap">' not in h3) and ("warn" in buf.getvalue())
    ok = ok and good3
    print(f"  {'✅' if good3 else '❌'} 缺字段：交付物无占位符={('<div class=.gap.>' not in h3)} "
          f"stderr 有告警={('warn' in buf.getvalue())}")

    # ---- ② 复盘前缀随场景变化 ----
    def label_of(kind):
        dd = dict(base, review={"error_pattern": "e"})
        if kind:
            dd["review"]["kind"] = kind
        h = mod.build(dd)
        m = re.search(r'<p><b>([^<]*)</b>', h)
        return m.group(1) if m else ""
    lab_q, lab_n, lab_p = label_of("错题"), label_of(None), label_of("要点")
    good4 = (lab_q == "错题归因：" and lab_p == "本题要点：" and "错题" not in lab_n)
    ok = ok and good4
    print(f"  {'✅' if good4 else '❌'} 复盘前缀：声明错题={lab_q!r} 未声明={lab_n!r}（**不得含「错题」**）声明要点={lab_p!r}")

    # ---- ③ 互斥对：共用词的两条不一起弹 ----
    cases = getattr(ap_cases, "EXCLUSIVE_CASES", [])
    if cases:
        idx = aps.load_index(aps.index_path(root))
        bad = []
        for text, must_have, must_not in cases:
            hits = aps.match(text, idx)
            if must_have not in hits or must_not in hits:
                bad.append((text, hits))
        good5 = not bad
        ok = ok and good5
        print(f"  {'✅' if good5 else '❌'} 互斥对（共 {len(cases)} 例）："
              f"{'全部只留对题的那条' if good5 else bad[:2]}")
    return ok


def gate_numbering(root):
    """门禁 6：交付页面的章节编号必须连贯（第十二轮 L4 实测发现）

    现象（L4：零记忆 agent 真做一套题 + 老师角色交付，验实物时撞见）：
      反模式层出现时，复盘编号顺延到「五」（第八轮设计），但**层自己没标题**
      → 学生看到的是「一、二、三、**五**」，中间那个「四」在页面上根本不存在。
      设计意图（让位）是对的，实现漏了一半（没给层加标题）。

    判据：提取产出 HTML 里所有带编号的 h2，序列必须是「一、二、三…」连续无跳。
    两种情形都测：反模式层出现（应到「五」）／不出现（应到「四」）。
    """
    fp = os.path.join(root, "scripts", "analysis_to_html.py")
    print()
    print("【门禁 6】章节编号连贯（层出现时不跳号）")
    if not os.path.isfile(fp):
        print("  ⚠️ 未找到 analysis_to_html.py，跳过")
        return True
    spec = importlib.util.spec_from_file_location("a2h_num", fp)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except SystemExit:
        pass
    base = {"title": "编号冒烟",
            "summary": {"theme": "t", "flow": "a → b"},
            "passage": {"paragraphs": ["p1"], "functions": ["f1"]},
            "questions": [{"q": "q1", "answer": "B", "why": "w", "cards": [],
                           "gap": "x", "transfer": "y"}],
            "review": {"takeaway": "k"}}
    ok = True
    order = "一二三四五六"
    for name, extra in (("反模式层出现", {"user_note": "我老是凭感觉选，说不出依据"}),
                        ("反模式层不出现", {})):
        d = dict(base)
        d.update(extra)
        html = mod.build(d)
        seq = [n for n, _ in re.findall(r'<h2>([一二三四五六])、([^<]*)</h2>', html)]
        # 判据 = **序列内部连续无跳**（不是「必须从一数起」——前面几节可能因数据缺失而不输出，
        #   那不算跳号。第一版按「从一数起」写，fixture 缺 summary/passage 时立刻假阳性）。
        nums = [order.index(n) + 1 for n in seq]
        gaps = [(a, b) for a, b in zip(nums, nums[1:]) if b - a != 1]
        good = bool(nums) and not gaps
        ok = ok and good
        print(f"  {'✅' if good else '❌'} {name}：编号={''.join(seq)}"
              + (f"  ← 跳号 {gaps}" if gaps else "（连续无跳）"))
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
    ok5 = gate_required_fields(root)
    ok6 = gate_numbering(root)

    print()
    print("=" * 78)
    allok = ok1 and ok2 and ok3 and ok4 and ok5 and ok6
    print("结论：", "🟢 全绿" if allok else "🔴 有门禁不过")
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
