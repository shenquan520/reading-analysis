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
