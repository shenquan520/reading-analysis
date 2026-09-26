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
  5) 必填项承载力：规范标「逐题/逐段必填」的项，通用管线必须真承载（第十一轮 L3，元素级）
  6) 章节编号连贯：反模式层出现/不出现两种情形下，页面编号都不得跳号（第十二轮 L4 实测）
  7) 共用词覆盖：关键词有交集的卡对必须有归属决定（切分/互斥/并存），不许留白（第十二轮 P2）
  8) 卡库卫生：重复块 / 标题编号跳号 / 标题粘连（第十二轮，评审 L4 交付件时顺手抓到）
  9) 文档取值清单与代码一致：同一文档里两处清单不许各说各话（第十六轮 S2）

用法：
    python verify_anti_patterns.py [--skill-root <skill 根>] [--analysis-dir <HTML 目录>]
默认 skill 根 = 本脚本所在目录的上一级；HTML 目录 = <skill 根>/dist/analysis
退出码：0 = 全绿；1 = 有门禁不过
"""
import argparse
import glob
import importlib.util
import io
import json
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import anti_patterns as aps          # 纯模块、无副作用：直接 import（不再切分源码——第六轮 K3）
import ap_cases                      # 固定回归套件（追加式，历史用例永不删）

EMPTY_ROW_RE = re.compile(
    r'<span class="ap-k">(为什么错|症状|你这次的症状|怎么防)</span><span class="ap-v">\s*</span>')

# 夹具用到的选项集，抽成模块常量：**别在 questions 字面量里嵌套 dict 字面量**——
# 审计工具 G33 用 `"questions": [{[^}]*}` 读 fixture 键集，`[^}]*` 会在**内层 options 的
# 第一个 `}`** 处提前截断，于是把 A/B/C/D 当成「fixture 多给的字段」报出来（本轮实测踩到）。
# 契约本来允许四个选项，那是 G33 的读取方式问题，但**夹具没理由去触发它**。
OPTS4 = {"A": "甲", "B": "乙", "C": "丙", "D": "丁"}
OPTS2 = {"A": "甲", "B": "乙"}

# —— 夹具渲染的 stderr 统一捕获（第十三轮 N5）——
# 为什么：夹具**故意**给不完整数据 → 渲染器按规范打 [warn]/[tip]。
#   那些是**夹具的**告警，不是交付物的问题。原样漏到 stdout 会混进证据文件
#   （实测 **26 行**，审核方原话：「真有失败会被淹掉」）。
# 捕获之后还多一个好处：**可以收进判定**——要断言「必填缺字段必须吭声」时直接读这个缓冲
#   （门禁 5 已经在这么做，但只有那两处做了，其余 7 处都在裸跑）。
_FIXTURE_WARNINGS = []


def _quiet(fn, *a, **kw):
    """跑一次夹具渲染 → (结果, 捕获到的 stderr 文本)

    ⚠️ 用 try/finally 复位 stderr：否则一次异常会把整个进程的 stderr 留在缓冲里，
       后续所有输出（含真正的失败原因）静默丢失——比噪声更坏。
    """
    buf = io.StringIO()
    old = sys.stderr
    sys.stderr = buf
    try:
        r = fn(*a, **kw)
    finally:
        sys.stderr = old
    err = buf.getvalue()
    if err.strip():
        _FIXTURE_WARNINGS.append(err.strip())
    return r, err


def fixture_warning_summary():
    """给证据文件一行**汇总**，而不是把 26 行原始告警倒进去。"""
    if not _FIXTURE_WARNINGS:
        return "夹具渲染器告警：0 行"
    n = sum(len(x.split("\n")) for x in _FIXTURE_WARNINGS)
    kinds = sorted(set(re.findall(r"^\[(\w+)\]", "\n".join(_FIXTURE_WARNINGS), re.M)))
    return ("夹具渲染器告警：%d 行（%s）——**已捕获、未原样输出**；"
            "故意缺字段的夹具应有告警，其余位置由各门禁断言" % (n, "/".join(kinds) or "?"))


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
        return (True if _require("analysis_to_html.py") else False)
    spec = importlib.util.spec_from_file_location("a2h", fp)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except SystemExit:
        pass
    base = {
        "title": "管线冒烟", "summary": {"theme": "t"},
        "passage": {"paragraphs": ["p1"], "functions": ["f1"]},
        # 第十三轮 N5：夹具**补全必填项**（gap/transfer/options），这样「无意外告警」本身
        #   就成了一条可断言的性质——哪天真漏了字段，这里会立刻红，而不是默默多几行噪声。
        "questions": [{"q": "q1", "answer": "B", "why": "w", "cards": [],
                       "gap": "无", "transfer": "按主题相关度先筛",
                       "options": OPTS4}],
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
    quiet_ok = True
    for name, extra, want_layer, want_sec, want_src in cases:
        d = dict(base)
        d.update(extra)
        html, werr = _quiet(mod.build, d)
        # 夹具已补全必填项 → **不该有任何告警**（第十三轮 N5：把夹具的 stderr 收进判定）
        if werr.strip():
            quiet_ok = False
            ok = False
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
    print(f"  {'✅' if quiet_ok else '❌'} 夹具必填项齐全（缺字段才该告警，此处不该有）")

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
        html, _ = _quiet(mod.build, d)
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
        return (True if _require("analysis_to_html.py") else False)
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
                               "transfer": "作用类题先问它控制了哪个变量",
                               "options": OPTS2}])
    html, _ = _quiet(mod.build, d)
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
                                "缺口": "无", "可迁移原则": "x",
                                "options": OPTS2}])
    h2, _ = _quiet(mod.build, d2)
    good2 = len(re.findall(r'<div class="gap">', h2)) == 1
    ok = ok and good2
    print(f"  {'✅' if good2 else '❌'} 中文键（缺口/可迁移原则）同样承载：gap 元素={len(re.findall(r'<div class=.gap.>', h2))}")

    # ---- ② 选项原文（第十二轮新增，三种写法都要承载）----
    # 契约声明「三种写法都吃」，那就三种都测——**声明了却只实现一种 = 契约骗人**
    # （本项目已因此吃过两次：段落层 5 件套、反模式层只做在案例脚本里）。
    opt_shapes = {
        "字典": {"A": "选项甲", "B": "选项乙", "C": "选项丙", "D": "选项丁"},
        "列表对象": [{"key": "A", "text": "选项甲"}, {"key": "B", "text": "选项乙"}],
        "纯列表": ["选项甲", "选项乙", "选项丙"],
    }
    for sname, sval in opt_shapes.items():
        dq = dict(base, questions=[{"q": "q1", "answer": "B", "why": "w", "cards": [],
                                    "gap": "无", "transfer": "x", "options": sval}])
        hq, _ = _quiet(mod.build, dq)
        n_opt = len(re.findall(r'<span class="opt-k">', hq))
        want = len(sval) if not isinstance(sval, dict) else len(sval)
        good = (n_opt == want) and "选项甲" in hq
        ok = ok and good
        print(f"  {'✅' if good else '❌'} 选项原文·{sname}写法：opt 元素={n_opt}（期望 {want}）")

    # 缺 options → 不塞占位符，但要有提示（与 gap 告警同族：不静默）
    dq0 = dict(base, questions=[{"q": "q1", "answer": "B", "why": "w", "cards": [],
                                 "gap": "无", "transfer": "x"}])
    hq0, werr0 = _quiet(mod.build, dq0)
    good0 = ('<span class="opt-k">' not in hq0) and ("tip" in werr0)
    ok = ok and good0
    print(f"  {'✅' if good0 else '❌'} 缺 options（无占位符 + 有提示）："
          f"opt 元素={len(re.findall(r'<span class=.opt-k.>', hq0))}"
          f" 提示={'有' if 'tip' in werr0 else '无'}")

    # 两项皆空 → 不产出占位符（交付物保持干净），但**要有告警**（不静默）
    d3 = dict(base, questions=[{"q": "q1", "answer": "B", "why": "w", "cards": []}])
    h3, werr = _quiet(mod.build, d3)
    good3 = ('<div class="gap">' not in h3) and ("warn" in werr)
    ok = ok and good3
    print(f"  {'✅' if good3 else '❌'} 缺字段：交付物无占位符={('<div class=.gap.>' not in h3)} "
          f"stderr 有告警={('warn' in werr)}（已捕获，未原样输出）")

    # ---- ② 复盘前缀随场景变化 ----
    def label_of(kind):
        dd = dict(base, review={"error_pattern": "e"},
                  questions=[{"q": "q1", "answer": "B", "why": "w", "cards": [],
                              "gap": "无", "transfer": "x", "options": OPTS2}])
        if kind:
            dd["review"]["kind"] = kind
        h, _ = _quiet(mod.build, dd)
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

    # ---- ④ 「两句都真」：各自有独立证据时两条都留（第十二轮 P3 口径） ----
    both = getattr(ap_cases, "EXCLUSIVE_BOTH_TRUE", [])
    if both:
        idx = aps.load_index(aps.index_path(root))
        bad6 = []
        for text, must_all in both:
            hits = aps.match(text, idx)
            if any(x not in hits for x in must_all):
                bad6.append((text, hits, must_all))
        good6 = not bad6
        ok = ok and good6
        print(f"  {'✅' if good6 else '❌'} 互斥口径·两句都真（共 {len(both)} 例）："
              f"{'两条都留（不按命中数硬丢）' if good6 else bad6[:2]}")
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
        return (True if _require("analysis_to_html.py") else False)
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
                           "gap": "x", "transfer": "y",
                           "options": OPTS2}],
            "review": {"takeaway": "k"}}
    ok = True
    order = "一二三四五六"
    for name, extra in (("反模式层出现", {"user_note": "我老是凭感觉选，说不出依据"}),
                        ("反模式层不出现", {})):
        d = dict(base)
        d.update(extra)
        html, _ = _quiet(mod.build, d)
        seq = [n for n, _ in re.findall(r'<h2>([一二三四五六])、([^<]*)</h2>', html)]
        # 判据 = **序列内部连续无跳**（不是「必须从一数起」——前面几节可能因数据缺失而不输出，
        #   那不算跳号。初版按「从一数起」写，fixture 缺 summary/passage 时立刻假阳性）。
        nums = [order.index(n) + 1 for n in seq]
        gaps = [(a, b) for a, b in zip(nums, nums[1:]) if b - a != 1]
        good = bool(nums) and not gaps
        ok = ok and good
        print(f"  {'✅' if good else '❌'} {name}：编号={''.join(seq)}"
              + (f"  ← 跳号 {gaps}" if gaps else "（连续无跳）"))
    return ok


def _uncovered_pairs(index):
    """扫出「关键词有交集、却没有归属决定」的卡对 → [(AP-a, AP-b, [共用词])]"""
    covered = set()
    for pair in (getattr(aps, "EXCLUSIVE_PAIRS", None) or []):
        covered.add(tuple(sorted(pair[:2])))
    for row in (getattr(aps, "COEXIST_OK", None) or []):
        covered.add(tuple(sorted(row[:2])))
    return [(a, b, w) for a, b, w in aps.keyword_intersections(index)
            if tuple(sorted((a, b))) not in covered]


def gate_shared_words(root):
    """门禁 7：共用词覆盖检查（第十二轮 P2）

    任何两条反模式的关键词若有交集，**必须有归属决定**，不许留白：
      ① **切分**（把词归给更对题的那条）→ 交集为空，不进表（首选）
      ② **互斥**（`EXCLUSIVE_PAIRS`）——成对命中时按独立证据判定丢不丢
      ③ **并存**（`COEXIST_OK`，须写明「为什么两条都对题」）

    留白的后果：同一段自述弹两张卡、其中一张不对题。AP-09 × AP-14 就是这么漏的——
    **机制立好了、表是手搓的、没有覆盖检查**，与「手工标记清单」同一个形状的错
    （第十一轮 T1 已为手工清单补过配置化改造，同一课在关键词表上又踩一次）。

    ⚠️ 覆盖检查最容易变成**空转门禁**：当前交集恰好为 0 时它也会报绿。
    故下面带**自测夹具**——造一份含共用词的假索引，验证这个检查真的会报。
    不验证的话，「绿」只说明没查东西（这条纪律见 VERIFICATION.md）。
    """
    idx = aps.load_index(aps.index_path(root))
    bad = _uncovered_pairs(idx)

    # —— 自测夹具：证伪「这个检查不是空转」——
    fake = {
        "AP-90": {"name": "夹具甲", "kw_list": ["共用词X", "甲独有"]},
        "AP-91": {"name": "夹具乙", "kw_list": ["共用词X", "乙独有"]},
    }
    fixture_hits = _uncovered_pairs(fake)
    fixture_ok = len(fixture_hits) == 1 and fixture_hits[0][0] == "AP-90"

    n_pairs = len(aps.keyword_intersections(idx))
    ok = (not bad) and fixture_ok
    print(f"  {'✅' if (not bad) else '❌'} 关键词交集 {n_pairs} 对，未归属 "
          f"{len(bad)} 对"
          + (f" → {[(a, b, w) for a, b, w in bad]}" if bad else "（切分/互斥/并存 三选一，无留白）"))
    print(f"  {'✅' if fixture_ok else '❌'} 自测夹具：造一对共用词，检查器"
          f"{'能报出来' if fixture_ok else '**没报**（门禁空转！）'}"
          f"  → {fixture_hits}")
    if not fixture_ok:
        print("       ⚠️ 夹具没过 = 这道门禁查不出东西，绿了也不代表安全")
    return ok


def gate_card_hygiene(root):
    """门禁 8：卡库卫生 —— 重复块 / 标题编号跳号 / 标题粘连（2026-09-25 第十二轮立）

    由来：审核方评审 L4 交付件时**顺手查了它引用的两张卡**，抓到两处：
      · B083 整块「四选项全错案例」连表格重复两遍（10 处重复行）
      · B037 标题编号 一、二、三、三点五、**五**、六点五、**六** —— 六跑到六点五后面
    他指出：**B037 这个「编号缺一节」和交付页那个「三→五」是同一个病**——
    长文档里条件插入或后期补写最容易把编号搞断，而**肉眼很难发现**。

    所以把交付页的检查（门禁 6）推广到卡库：一边是学生看到的页，一边是我们自己读的卡，
    同一个病就同一套门禁。

    三条判据（**都用块级，避免样板行假阳性**）：
      ① 重复块：连续 3 行且总长 ≥120 字的两段完全相同（单行重复多为「适用题型」样板，不算）
      ② 编号跳号：`## 中文数字、` 序列内部必须连续（允许「点五」这种半步编号）
      ③ 标题粘连：行首不是 `#` 却含 `## ` —— 标题被粘在上一行末尾
    **三条都带自测夹具**：造一份必然违规的假卡，验证检查器真会报（否则交集恰好为空时报绿＝没查）。
    """
    import hashlib

    cards_dir = os.path.join(root, "references", "cards")
    print("【门禁 8】卡库卫生（重复块 / 编号跳号 / 标题粘连）")
    if not os.path.isdir(cards_dir):
        print("  ⏭️ 无 references/cards/ → 跳过（不算通过）")
        return SKIP

    CN = {c: i + 1 for i, c in enumerate("一二三四五六七八九十")}

    def scan_one(text):
        """返回 (重复块列表, 跳号列表, 粘连列表)

        ⚠️ 三条判据都被**实测假阳性**打磨过（初版在根目录文档上 4 报 4 假），
           收紧依据写在各自那一行——**门禁喊狼来了就会被忽略，那比没有门禁更坏**：
             · `CASE-FEEDING-PROMPT.md`：示例模板里的 `## 一、闭卷结果` 在**代码围栏内**，
               不是文档标题 → 先剥围栏
             · 某个**内部账本文件**：`> ## ⚠️ 重启必读` 是**引用块里的标题**，合法
             · `HANDBOOK.md`：正文里**提到**某个标题（中文引号/反引号包裹），合法
             · `CHANGELOG.md`：相邻两批的**样板三行**（「本批首次 Read 时…」）逐字相同，合法
               → 重复块窗口从 3 行提到 5 行、总长提到 200 字，样板行不再触发
        """
        # 剥掉代码围栏（``` … ```）——围栏里的是示例，不是文档结构
        body = re.sub(r"(?ms)^```.*?^```", "", text)
        lines = [l.rstrip() for l in body.split("\n")]
        dup, seen = [], {}
        for i in range(len(lines) - 4):
            blk = "\n".join(lines[i:i + 5])
            if len(blk.strip()) < 200:
                continue
            h = hashlib.md5(blk.encode()).hexdigest()
            if h in seen and abs(seen[h] - i) > 5:
                dup.append((seen[h] + 1, i + 1, lines[seen[h]].strip()[:48]))
            else:
                seen[h] = i
        raw = re.findall(r"(?m)^##\s*([一二三四五六七八九十]+)(点五)?[、.]", body)
        seq = [CN[b] + (0.5 if h else 0) for b, h in raw if b in CN]
        jumps = [(seq[i], seq[i + 1]) for i in range(len(seq) - 1) if seq[i + 1] > seq[i] + 1]
        glue = []
        for ln in lines:
            st = ln.lstrip()
            if not st or st.startswith("#") or st.startswith(">"):
                continue                      # 标题行 / 引用块标题 → 合法
            if "|" in ln[:3]:
                continue
            m = re.search(r"\S\s*#{2,4}\s+\S", ln)
            if not m:
                continue
            # 反引号 / 中文引号包裹的「提到某标题」→ 合法，不算粘连
            frag = ln[max(0, m.start() - 2):m.end()]
            if re.search(r"[`「『“\"']", frag):
                continue
            glue.append(ln.strip()[:52])
        return dup, jumps, glue

    # —— 自测夹具：证伪「这三条不是空转」——
    # 故意造三处违规：① 一 → 三（跳号）② 标题粘在上一行末尾（缺换行）③ 三段块重复两遍
    _blk = ("重复块内容重复块内容重复块内容重复块内容重复块内容重复块内容重复块内容重复块内容\n"
            "第二行第二行第二行第二行第二行第二行第二行第二行第二行第二行第二行第二行第二行\n"
            "第三行第三行第三行第三行第三行第三行第三行第三行第三行第三行第三行第三行第三行\n"
            "第四行第四行第四行第四行第四行第四行第四行第四行第四行第四行第四行第四行第四行\n"
            "第五行第五行第五行第五行第五行第五行第五行第五行第五行第五行第五行第五行第五行")
    fake = "\n".join([
        "## 一、甲",
        "",
        "正文行正文行正文行正文行正文行正文行正文行正文行正文行正文行正文行正文行",
        "某些内容写完之后忘了换行，标题就粘上来了## 二、乙",   # ← 粘连（行首不是 #）
        "",
        _blk,
        "",
        _blk,
        "",
        "## 四、丁",                                          # ← 跳号（一 → 四，缺二三）
    ])
    fd, fj, fg = scan_one(fake)
    fixture_ok = bool(fd) and bool(fj) and bool(fg)
    print(f"  {'✅' if fixture_ok else '❌'} 自测夹具：重复块{len(fd)} / 跳号{fj} / 粘连{len(fg)}"
          f" —— {'三项都能报出来' if fixture_ok else '**检查器空转！**'}")

    files = sorted(glob.glob(os.path.join(cards_dir, "**", "*.md"), recursive=True))
    # 根目录的长文档也扫——**同一个病同一个门禁**：
    #   VERIFICATION.md 自己就曾乱序（八 → 十 → 九 → 十一），因为「插入新节时只编号不排序」。
    #   交付页跳号、卡片 B037 编号断裂、文档节号乱序——三处同一个成因，别只修一处。
    files += sorted(glob.glob(os.path.join(root, "*.md")))
    bad_dup, bad_num, bad_glue = [], [], []
    for fp in files:
        rel = os.path.relpath(fp, root).replace("\\", "/")
        text = io.open(fp, encoding="utf-8").read()
        d, j, g = scan_one(text)
        if d:
            bad_dup.append((rel, d))
        if j:
            bad_num.append((rel, j))
        if g:
            bad_glue.append((rel, g))
    print(f"  扫了 {len(files)} 个 md 文件（卡库 + 根目录文档）："
          f"重复块 {len(bad_dup)} / 跳号 {len(bad_num)} / 粘连 {len(bad_glue)}")
    for rel, d in bad_dup[:4]:
        print(f"      ❌ 重复块 {rel}：L{d[0][0]} 与 L{d[0][1]} | {d[0][2]}")
    for rel, j in bad_num[:6]:
        print(f"      ❌ 编号跳号 {rel}：{j}")
    for rel, g in bad_glue[:4]:
        print(f"      ❌ 标题粘连 {rel}：{g[0]}")
    ok = fixture_ok and not (bad_dup or bad_num or bad_glue)
    if not fixture_ok:
        print("      ⚠️ 夹具没过 = 这道门禁查不出东西，绿了也不代表安全")

    # —— 判据 ④：卡文件 ↔ 索引登记一致性（2026-09-26 第十九轮补）——
    #
    # 由来：封版前查「索引里的数字对不对」，顺手发现 **B086 有卡文件、索引表格里没有它那一行**。
    #   那次转正 B086 时只改了索引的**说明行**（「86 张（B001–B086）」）、**忘了加表格行** ——
    #   又一个「改了一处、没改配套的另一处」。
    #   ★ 而 INDEX 是「分析任何题目**必先来这里检索**」的入口 →
    #     **漏登记 = 这张卡在实际使用中检索不到**（不是排版问题，是功能问题）。
    #   前三条判据查「卡内容本身」，**都不查「卡有没有被登记」**——这个射程此前无人守。
    #
    # 判据（兼容两种索引格式，不猜）：
    #   目录下每个卡文件的**编号**或**文件名主干**，必须在对应索引里出现一次。
    #   · B/A 系用表格式 `| 086 | …`
    #   · R 系用链接式 `[R1-what](R1-what.md)`
    #   任一形式命中即算登记 → 两种格式都能过，不会误报。
    INDEXES = {"B-skills": "INDEX.md", "A-analysis": "INDEX.md", "REVIEW": "00-index.md"}

    def _scan_index(cards_root):
        """返回 {子目录: (卡文件列表, 未登记的列表)}"""
        out = {}
        for sub, idxname in INDEXES.items():
            d = os.path.join(cards_root, sub)
            if not os.path.isdir(d):
                continue
            idx = os.path.join(d, idxname)
            if not os.path.isfile(idx):
                out[sub] = (["<索引文件缺失>"], ["<索引文件缺失>"])
                continue
            itext = io.open(idx, encoding="utf-8").read()
            cards = []
            for f in sorted(os.listdir(d)):
                if not f.endswith(".md") or f in ("INDEX.md", "00-index.md", "card-template.md"):
                    continue
                stem = os.path.splitext(f)[0]
                m = re.match(r"([A-Za-z]*)(\d+)", stem)
                num = m.group(2) if m else ""
                # 命中任一种登记形式即算已登记
                hit = (stem in itext) or (num and re.search(r"\|\s*0*%s\s*\|" % num, itext))
                if not hit and num:
                    hit = bool(re.search(r"[\[\(][^\]\)]*%s[^\]\)]*[\]\)]" % re.escape(stem), itext))
                cards.append((f, hit))
            unreg = [f for f, hit in cards if not hit]
            out[sub] = ([f for f, _ in cards], unreg)
        return out

    # 自测夹具：造「有卡但索引没登记」的假场景 → 必须报
    _fake_root = tempfile.mkdtemp(prefix="idxfix_")
    try:
        _fd = os.path.join(_fake_root, "B-skills")
        os.makedirs(_fd)
        io.open(os.path.join(_fd, "001-a.md"), "w", encoding="utf-8").write("# A\n")
        io.open(os.path.join(_fd, "002-b.md"), "w", encoding="utf-8").write("# B\n")
        io.open(os.path.join(_fd, "INDEX.md"), "w", encoding="utf-8").write(
            "| 编号 | 卡名 |\n|---|---|\n| 001 | 甲 |\n")      # 只登记 001
        _r = _scan_index(_fake_root)
        idx_fix_ok = _r.get("B-skills", (None, []))[1] == ["002-b.md"]
    finally:
        shutil.rmtree(_fake_root, ignore_errors=True)
    print(f"  {'✅' if idx_fix_ok else '❌'} 自测夹具：索引漏登记能被检出"
          f"（假场景：001 已登记 / 002 未登记）")

    unreg_all = []
    if os.path.isdir(cards_dir):
        for sub, (cards_, unreg) in _scan_index(cards_dir).items():
            if unreg:
                unreg_all.append((sub, unreg))
    if unreg_all:
        print(f"  ❌ **有卡但索引没登记**（索引是检索入口，漏登记＝这张卡用不上）：")
        for sub, unreg in unreg_all:
            print(f"      · {sub}/：{len(unreg)} 张未登记 → {unreg[:5]}")
    else:
        print("  ✅ 卡文件与索引登记一致（三个子目录全过）")

    ok = ok and idx_fix_ok and not unreg_all
    return ok


def gate_list_consistency(root):
    """门禁 9：同一份文档里的「状态/取值清单」必须与代码一致（第十六轮 S2 立）

    案件（审核方报）：`references/缺口台账.md` 的 §一 列了 **6 个**取值（含 `待核`）、
    代码 `VALID_STATUS` 也是 **6 个**，而 **§二「状态取值」表格只有 5 行** —— 漏了 `待核`。

    **为什么之前没被抓到**：审计工具 **G40** 管的是「**表格行的字段 vs 同一行的备注**」，
    **不查「文档里两个清单是否一致」**——那是另一个射程。本项目此前也没有这道门禁。

    判据（确定性、不猜）：
      · 从 `gap_ledger.VALID_STATUS` 取权威清单（代码是唯一事实源）
      · 在台账文档里找「回引号包裹的状态词」出现处，按**段落/表格块**分组
      · 每一组若**自称是取值清单**（组内 ≥2 个合法状态词），则必须与权威清单**完全一致**
        —— 缺一个 / 多一个都报

    ★ 附自测夹具：造一份缺 `待核` 的假文档 → 必须报出来；造一份完整的 → 不许报。
      没有夹具 = 可能因为「文档恰好都对」而恒绿（本项目已被这条教训咬过三次）。
    """
    import importlib.util as _ilu
    fp = os.path.join(root, "scripts", "gap_ledger.py")
    ledger = os.path.join(root, "references", "缺口台账.md")
    print()
    print("【门禁 9】文档里的取值清单必须与代码一致（同一文档两套口径 = 读者不知信哪个）")
    if not os.path.isfile(fp) or not os.path.isfile(ledger):
        return _optional_dep("gap_ledger.py", "缺口台账.md")
    spec = _ilu.spec_from_file_location("gl_lc", fp)
    mod = _ilu.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except SystemExit:
        pass
    valid = list(getattr(mod, "VALID_STATUS", []))

    def _scan(text):
        """返回 [(位置, 实得集合, 缺, 多)]

        两种真·清单形态（**散文里提到状态词不算**）：
          ① **表格块里某一列**：连续 `|` 行的同一列，多行取值都是合法状态词
          ② **单行列全**：一行内回引号块用 `/`、`、` 分隔并列列出，且该行几乎没有表意汉字

        ⚠️ 初版判据写成「相邻行里出现 ≥2 个状态词就算清单」→ **在真文档上 2 报 2 假**：
            · 「要么回退 `待立卡`，要么挂 `待核` 进人工队列」——一句话里提了两个状态
            · 「`暂不新建` 与 `驳回` **都必须有理由**」——同上
            **散文提到状态词，与「列一张清单」是两回事。**
           （又一次「判据过粗 → 假阳性」，与门禁 8 初版同一个病。）
        """
        lines = text.split("\n")
        bad = []
        ok_full = set(valid)

        # ① 表格块：连续 `|` 行 → 逐列取「整格就是一个合法状态词」的行
        i = 0
        while i < len(lines):
            if lines[i].lstrip().startswith("|"):
                j = i
                while j < len(lines) and lines[j].lstrip().startswith("|"):
                    j += 1
                cols = {}
                for ln in lines[i:j]:
                    for k, c in enumerate(x.strip() for x in ln.strip().strip("|").split("|")):
                        m = re.fullmatch(r"`([^`\n]+)`", c)
                        if m and m.group(1) in valid:
                            cols.setdefault(k, set()).add(m.group(1))
                for k, s in cols.items():
                    if len(s) >= 2 and s != ok_full:
                        bad.append((i + 1, s, sorted(ok_full - s), sorted(s - ok_full)))
                i = j
            else:
                i += 1

        # ② 单行列全：该行去掉回引号块后几乎无表意汉字（≤2 个），且并列列出 ≥3 个状态词
        for idx, ln in enumerate(lines, 1):
            toks = []
            for m in re.finditer(r"`([^`\n]+)`", ln):
                for part in re.split(r"\s*[/、,，|]\s*", m.group(1)):
                    if part in valid:
                        toks.append(part)
            if len(toks) < 3:
                continue
            residue = re.sub(r"`[^`\n]*`", "", ln)
            if len(re.findall(r"[\u4e00-\u9fff]", residue)) > 2:
                continue          # 这是散文，不是清单
            s = set(toks)
            if s != ok_full:
                bad.append((idx, s, sorted(ok_full - s), sorted(s - ok_full)))
        return bad

    # —— 自测夹具 ——
    fx_bad = "".join("| `%s` | x |\n" % s for s in valid if s != "待核")   # 表格缺 待核
    fx_ok = "".join("| `%s` | x |\n" % s for s in valid)                  # 表格列全
    fx_line_ok = f"取值：`{' / '.join(valid)}`。\n"                        # 单行列全
    fx_prose = ("要么回退 `待立卡`，要么挂 `待核` 进人工队列。\n"           # 散文提及 → 不许报
                "`暂不新建` 与 `驳回` 都必须有理由——否则它们就是捷径。\n")
    fx_line_bad = f"取值：`{' / '.join([s for s in valid if s != '待核'])}`。\n"
    fixture_ok = (len(_scan(fx_bad)) == 1 and len(_scan(fx_ok)) == 0
                  and len(_scan(fx_line_ok)) == 0 and len(_scan(fx_prose)) == 0
                  and len(_scan(fx_line_bad)) == 1)
    print(f"  {'✅' if fixture_ok else '❌'} 自测夹具（表格缺词报 / 表格全不报 / 单行列全不报"
          f" / **散文提及不报** / 单行缺词报）")
    if not fixture_ok:
        print("      ⚠️ 夹具没过 = 这道门禁查不出东西，绿了也不代表安全")
        return False

    bad = _scan(io.open(ledger, encoding="utf-8").read())
    ok = not bad
    if ok:
        print(f"  ✅ 台账里出现的「取值清单」共 {len(valid)} 项，与代码 VALID_STATUS 完全一致")
    else:
        for line, s, missing, extra in bad[:5]:
            print(f"  ❌ 台账 L{line} 的取值清单与代码不一致"
                  f"（缺 {missing or '—'}／多 {extra or '—'}）")
    return ok


def _find(names):
    """在一组候选位置里找文件，返回「找到的」与「没找到的」"""
    found, missing = [], []
    for n in names:
        ok = any(os.path.isfile(os.path.join(d, n)) for d in (
            HERE, os.path.dirname(HERE), os.path.join(os.path.dirname(HERE), "scripts")))
        (found if ok else missing).append(n)
    return found, missing


def _require(*names):
    """依赖是**每个包都该随包发布**的（如管线脚本）→ 缺失 = ❌ 判红

    ★ 第十八轮自抓：本脚本原有 4 处「依赖缺失 → `return True`」——
      而 `analysis_to_html.py` **是开源包本就随包发布的文件** →
      它被删了，门禁 4/5/6 会集体静默回绿。**与审核方报我的那个 `continue` 同一个病。**
    """
    _found, missing = _find(names)
    if missing:
        print(f"  ❌ **必需依赖缺失**：{'、'.join(missing)}"
              f" → 本门禁无法执行，**判红**（不是跳过）")
        print("      → 依赖不在＝这条门禁没查；**没查 ≠ 通过**。")
        return False
    return True


def _optional_dep(*names):
    """依赖是**本地专用工具 + 它的数据**（公开包本就不含）→ 三态判定

    · **全部缺失** → ⚠️ 如实报「未查」，返回 `None`（不计入绿，也不冤枉本包）
    · **部分缺失** → ❌ 判红（这正是最该抓的组合：**工具在、它的数据却没了**）
    · 全在 → 正常执行（返回 True，由调用方继续跑真正的检查）
    """
    found, missing = _find(names)
    if not missing:
        return True
    if not found:
        print(f"  ⚠️ 本包不含 {'、'.join(names)}（均为本机专用工具/数据）"
              f" → **未查**，如实报，不计入绿")
        return None
    print(f"  ❌ **依赖不完整**：在 {'、'.join(found)}；"
          f"缺 {'、'.join(missing)}　← 工具在说明这是本地包，它的数据不该缺")
    return False


def _parse_kb_tree(text):
    """解析 SKILL.md「知识库结构」那种缩进树 → 完整路径列表（第二十轮补）

    ★ 为什么非要有这个：第一版门禁只扫「反引号包裹」与「带目录前缀」两种写法，
      而 SKILL.md 那张表是**缩进树**——藏掉 `references/templates/` 后门禁照样报 0 悬空。
      **门禁空转了。** 而这张表恰恰就是让那个零记忆 Agent 踩空的东西：
      它照表去找交付 JSON 契约模板，文件不在，只能去读渲染器源码反推字段名。

    形状（实测）：
        references/
        ├─ core-principles.md      说明
        ├─ theories/               说明
        │  └─ INDEX.md             说明
        CHANGELOG.md               说明        ← 顶格无符号 = 相对**包根**
    规则：缩进宽度 // 3 = 层级；`├─ A/` 声明目录，其子项拼在它下面。
    """
    out, stack, root = [], {}, None
    for ln in text.split("\n"):
        if not ln.strip():
            continue
        # 根行：顶格、以 / 结尾、无树符号
        if "├" not in ln and "└" not in ln and re.match(r"^\s*[A-Za-z0-9_\-./]+/\s*$", ln):
            root = ln.strip().rstrip("/")
            stack = {}
            continue
        m = re.match(r"^([\s│]*)[├└]─\s+([^\s]+)", ln)
        if m and root:
            depth = len(m.group(1)) // 3
            name = m.group(2)
            parent = "/".join(stack[d] for d in sorted(stack) if d < depth)
            full = (root + "/" + parent + "/" + name) if parent else (root + "/" + name)
            out.append(full.rstrip("/"))
            if name.endswith("/"):
                stack[depth] = name.rstrip("/")
            for d in [d for d in stack if d > depth or (not name.endswith("/") and d >= depth)]:
                del stack[d]
            continue
        # 顶格无符号 + 后面接说明文字 = 包根下的文件
        m2 = re.match(r"^([A-Za-z0-9_\-./]+)\s{2,}\S", ln)
        if m2 and root:
            out.append(m2.group(1).rstrip("/"))
    return out


def _docref_scan_text(text, doc, inpack, filler_prefix, filler_files, placeholder_re, ref_re):
    """门禁 10 的**唯一判据实现**：扫一段文档文本，返回悬空引用清单。

    ★ 为什么抽成函数（第二十轮，2026-09-26）：
      原先把判据在「主逻辑」和「自测夹具」里**各写了一遍**（复制粘贴）。
      夹具验证不了实现 —— 实现改了、夹具还是老逻辑，照样报「夹具通过」。
      这类「夹具与实现不同源」正是本项目的靶心（**能空转的门禁等于没有门禁**）。
      → 现在主逻辑与夹具都调这一个函数。

    四种写法都算「指令性引用」（第三、四种是第二十轮补的）：
      ① 反引号包裹：`` `references/x.md` ``
      ② 带目录前缀（无反引号）：`scripts/foo.py`
      ③ **裸写的脚本名**：`skill_audit.py` ← 第二十轮之前**不查**，
         所以「SKILL.md 让读者去跑一个包里没有的脚本」藏了很久（外部工具实测踩到）
      ④ 缩进树文件地图：由 `_parse_kb_tree()` 单独解析（**目录也算存在**，树里列的是目录）
    """
    missing = []

    def resolvable(ref):
        if ref.startswith(filler_prefix) or ref in filler_files:
            return True
        if placeholder_re.search(ref):
            return True
        cands = [ref, os.path.join(os.path.dirname(doc), ref).replace("\\", "/"),
                 os.path.normpath(os.path.join(os.path.dirname(doc), ref)).replace("\\", "/")]
        if any(c in inpack for c in cands):
            return True
        if "/" in ref:                                  # 后缀匹配：文档大量用相对简写
            return any(p.endswith("/" + ref) for p in inpack)
        return any(os.path.basename(p) == ref for p in inpack)

    checked = 0
    for m in ref_re.finditer(text):
        ref = (m.group(1) or m.group(2) or m.group(3) or "").strip()
        if not ref or ref.endswith("/"):
            continue
        checked += 1
        if not resolvable(ref):
            missing.append(ref)
    return missing, checked


def gate_doc_references(root):
    """【门禁 10】文档里的**指令性引用**必须真存在（第二十轮立，2026-09-26）

    ★ 由来（GitHub 发布物验收·第二十轮）：
      派一个零记忆 Agent 照 SKILL.md 干活，它照「知识库结构」那张表去拿交付 JSON 契约模板
      —— `references/templates/` **根本不在包里**（从来不在任何同步清单里，靠手工搬）。
      它只能去读 `analysis_to_html.py` 的源码反推字段名。
      **文档说「去读 X」而 X 不存在，等于给读者挖坑**——这是功能缺失，不是排版问题。

    三条假阳性防线（**喊狼来了比没有门禁更坏**）：
      1. **使用者自填区白名单**：README 明说 `theories/` 与 `cases/` 刻意留空
         （「用你自己的材料填充」）→ 引用它们**是合法的**，不报。
      2. **命名占位符白名单**：`case-NNN.md` 这类是模板里的占位名，不报。
      3. **只认两种写法**：反引号包裹的文件名、或带目录前缀的路径。
         缩进树里的裸文件名（如 `├─ core-principles.md`）**不算**——那是排版，
         且它相对的是父目录，逐行解析必然误报。
    """
    print("【门禁 10】文档里的指令性引用必须真存在（说「去读 X」而 X 不存在 = 给读者挖坑）")

    # 自填区 / 占位符白名单
    FILLER_PREFIX = ("references/theories/", "references/cases/", "theories/", "cases/")
    FILLER_FILES = {"references/my-patterns.md", "my-patterns.md", "references/theories/INDEX.md",
                    "references/cases/INDEX.md", "theories/INDEX.md", "cases/INDEX.md"}
    PLACEHOLDER_RE = re.compile(r"(NNN|XXX|\*)")

    REF_RE = re.compile(
        r"`([A-Za-z0-9_\-./]+\.(?:md|py|js|json|html))`"            # ① 反引号包裹
        r"|(?<![\w/`])((?:references|scripts)/[A-Za-z0-9_\-./]+)"    # ② 带目录前缀
        # ③ **裸写的脚本名**（无反引号、无目录前缀）——第二十轮补，专治
        #    「文档让读者去跑一个包里没有的脚本」那种藏得最深的悬空引用。
        #    ⚠️ 两个坑（第一版现场踩的）：
        #      ① alternation 顺序：`js` 排在 `json` 前 → `.audit.json` 被切成 `audit.js`
        #      ② 未排除前面紧跟的点号 → `<skill名>.audit.json` 里切出 `audit.json`
        #    只认 .py/.js/.json（脚本类）；`.md` 裸写太常见（INDEX.md 等同名多个），不纳入。
        r"|(?<![\w/`\-.])([A-Za-z_][A-Za-z0-9_\-]*\.(?:json|py|js))")

    inpack = set()
    for dp, dirs, fs in os.walk(root):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", ".audit_history")]
        for f in fs:
            inpack.add(os.path.relpath(os.path.join(dp, f), root).replace("\\", "/"))

    DOCS = ["SKILL.md", "README.md", "USER-GUIDE.md"]
    missing = {}
    checked = 0
    for doc in DOCS:
        p = os.path.join(root, doc)
        if not os.path.isfile(p):
            continue
        text = io.open(p, encoding="utf-8", errors="ignore").read()
        # ★ 判据只有一份（`_docref_scan_text`），主逻辑与自测夹具**共用**
        miss, n = _docref_scan_text(text, doc, inpack, FILLER_PREFIX, FILLER_FILES,
                                    PLACEHOLDER_RE, REF_RE)
        checked += n
        for ref in miss:
            missing.setdefault(ref, []).append(doc)

    for ref, docs in sorted(missing.items()):
        print(f"      ❌ 引用了不存在的文件：`{ref}`（{docs[0]}）")
    print(f"  在 {'/'.join(DOCS)} 里查了 {checked} 处引用，**悬空 {len(missing)} 处**")

    # —— 缩进树（SKILL.md「知识库结构」那种地图）单独走一遍 ——
    tree_missing = []
    for doc in DOCS:
        p = os.path.join(root, doc)
        if not os.path.isfile(p):
            continue
        text = io.open(p, encoding="utf-8", errors="ignore").read()
        for ref in _parse_kb_tree(text):
            if ref.startswith(FILLER_PREFIX) or ref in FILLER_FILES:
                continue
            if PLACEHOLDER_RE.search(ref):
                continue
            if ref in inpack or os.path.isdir(os.path.join(root, ref)):
                continue
            if "/" in ref and any(q.endswith("/" + ref) for q in inpack):
                continue
            tree_missing.append((ref, doc))
    for ref, doc in tree_missing:
        print(f"      ❌ 文件地图里的路径不存在：`{ref}`（{doc}）")
    print(f"  文件地图（缩进树）解析出 {len(_parse_kb_tree(io.open(os.path.join(root, DOCS[0]), encoding='utf-8').read())) if os.path.isfile(os.path.join(root, DOCS[0])) else 0} 条路径，**悬空 {len(tree_missing)} 条**")
    missing.update({r: [d] for r, d in tree_missing})

    # —— 自测夹具：这份夹具必须能报出来，否则门禁是空转的 ——
    #    ★ 夹具**调同一个判据函数**（`_docref_scan_text`），不再自己复写一遍逻辑。
    #      第二十轮之前两边各写一份 → 实现改了夹具也不知道，属于「夹具与实现不同源」。
    tmp = tempfile.mkdtemp(prefix="docref_")
    try:
        os.makedirs(os.path.join(tmp, "references"), exist_ok=True)
        os.makedirs(os.path.join(tmp, "scripts"), exist_ok=True)
        for f in (("references", "core-principles.md"), ("scripts", "real-script.py")):
            io.open(os.path.join(tmp, *f), "w", encoding="utf-8").write("# exists\n")
        io.open(os.path.join(tmp, "SKILL.md"), "w", encoding="utf-8").write(
            "# fake skill\n\n"
            "先读 `references/core-principles.md`（存在→不报），再跑 `scripts/ghost-script.py`（幽灵→报）。\n"
            "**裸写的脚本名也要查**：跑 skill_audit.py 核一遍（包里没有→报），"
            "但 scripts/real-script.py 是有的（→不报）。\n"
            "自填区与占位符不算：`references/theories/mine.md`、`references/cases/case-NNN.md`。\n")
        inpack2 = set()
        for dp, dirs, fs in os.walk(tmp):
            for f in fs:
                inpack2.add(os.path.relpath(os.path.join(dp, f), tmp).replace("\\", "/"))
        text2 = io.open(os.path.join(tmp, "SKILL.md"), encoding="utf-8").read()
        hits, _n = _docref_scan_text(text2, "SKILL.md", inpack2, FILLER_PREFIX, FILLER_FILES,
                                     PLACEHOLDER_RE, REF_RE)
        expect = ["scripts/ghost-script.py", "skill_audit.py"]
        fixture_ok = (hits == expect)
        print(f"  {'✅' if fixture_ok else '❌'} 自测夹具："
              f"{'报出两种写法的幽灵引用（带前缀 + 裸写），其余不误报' if fixture_ok else '期望 ' + str(expect) + '，实际 ' + str(hits)}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    ok = (not missing) and fixture_ok
    if not fixture_ok and not missing:
        print("      ⚠️ 夹具没过 = 这道门禁查不出东西，绿了也不代表安全")
    return ok


def _check_template_contract(root):
    """纯检查：模板每个非 `_` 字段是否都有归宿声明。

    **职责单一**：只读模板、算差异、返回结果（不打印、不建夹具、不递归）。
    打印与夹具在 `gate_template_render_contract` 里做。

    ⚠️ 踩过两次递归（同一处，值得记）：
      第一次：夹具写在门禁函数里、夹具又调门禁函数 → 无限递归（输出刷几百屏）。
      第二次：把门禁函数改名成 `_check` 后，**忘了把夹具段搬出去** → 夹具仍调 `_check` 自身 → 又递归。
      教训：**函数改名只是改名；「谁调谁」的关系要重新想一遍。**
      防范：夹具必须调「被检查的那段逻辑」，而那段逻辑里**不能含夹具**。

    返回：undeclared / stale 两个列表；模板不存在时返回 None（= 未查）。
    """
    import json as _json

    tpl = os.path.join(root, "references", "templates", "analysis-result.template.json")
    if not os.path.isfile(tpl):
        return None

    try:
        data = _json.loads(io.open(tpl, encoding="utf-8").read())
    except Exception:
        return False, "模板不是合法 JSON"

    if "_渲染说明" not in data:
        return False, "模板缺 `_渲染说明` 表——每个字段的归宿必须显式声明"

    spec = data["_渲染说明"]
    spec_keys = set(spec.keys())

    # 说明表的键可以是**精确路径**或**带 * 的通配**（`summary.*` / `questions[].card_names.*`）
    import re as _re
    spec_pats = []
    for k in spec_keys:
        if k.startswith("_"):
            continue
        rx = "^" + _re.escape(k).replace(r"\*", "[^.]+") + "$"
        spec_pats.append(_re.compile(rx))

    def covered(path):
        """⚠️ **父路径的声明不自动覆盖子路径** —— 否则 `questions` 一声明，
        `questions[].q` 全算覆盖，这道门禁就废了。
        需要整块声明的（键是动态的，如卡号→卡名）在说明表里写通配。"""
        return any(rx.match(path) for rx in spec_pats)

    def walk(o, path=""):
        out = []
        if isinstance(o, dict):
            for k, v in o.items():
                if k.startswith("_"):
                    continue
                p = f"{path}.{k}" if path else k
                out.append(p)
                if isinstance(v, dict):
                    out += walk(v, p)
                elif isinstance(v, list) and v and isinstance(v[0], dict):
                    out += walk(v[0], p + "[]")
        return out

    fields = walk(data)
    undeclared = [f for f in fields if not covered(f)]
    stale = [k for k in spec_keys
             if not k.startswith("_") and "*" not in k and k not in fields]
    return undeclared, stale


def gate_template_render_contract(root):
    """【门禁 11】交付模板的每个字段都要有「归宿声明」（第二十轮立，2026-09-26）

    ★ 由来（外部工具 ZCode 冷启动验收·第二十轮）：
      它填了 `questions[].user_wrong_choice` / `user_thinking`，然后如实报告
      「模板里有这两个字段，但渲染器不读」→ **使用者自己「当时为什么选错」的原话
      在交付页面上看不到**。顺着模板逐字段核下去，又发现 `review.dual_channel`
      （A032 双通道，本 skill 的核心方法论）同样是**只进 JSON、不进页面**。
      再往下还核出：**模板漏了 `gap`/`transfer` 这两个「逐题必填」字段** ——
      照模板填必然缺，渲染器会告警。

    为什么不做「模板键 ⊆ 渲染器读到的键」这种机器判定：
      实测模板里**本来就有一批字段渲染器不读且属有意为之**（`card_names` 用卡文件真标题替代、
      `meta.*`/`schema_version` 是元信息、`user_note` 是输入信号不是输出内容）——
      那个判据会**一口气报十几个假阳性**。按本项目既有纪律：
      **喊狼来了比没有门禁更坏。**

    → 改成**声明式**：模板里 `_渲染说明` 必须覆盖每一个非 `_` 字段，
      逐条写明「渲染成什么」或「为什么不渲染」。**零假阳性，且加字段必须当场想清归宿。**
      本门禁只查「有没有声明」，不判断声明得对不对（那要人看）——
      它挡的是「填了却没人读、而没人发现」这一类。
    """
    print("【门禁 11】交付模板字段的归宿声明（填了却没人读 = 读者以为填错了）")

    res = _check_template_contract(root)
    if res is None:
        print("  ⚠️ 找不到 references/templates/analysis-result.template.json → **未查**，如实报，不计入绿")
        return None
    if isinstance(res, tuple) and res and res[0] is False:
        print(f"  ❌ {res[1]}")
        undeclared, stale = [], []
        ok = False
        res = ([], [])
    else:
        undeclared, stale = res
        for f in undeclared:
            print(f"      ❌ 未声明归宿：`{f}` —— 加字段时要在 `_渲染说明` 里写明它渲染成什么/为什么不渲染")
        for k in stale:
            print(f"      ⚠️ 说明表里有 `{k}`，但模板里找不到对应字段（说明表过期了）")
        print(f"  → 未声明 {len(undeclared)} 个、过期 {len(stale)} 条")
        ok = not undeclared

    # —— 自测夹具：新加一个未声明字段，必须报出来 ——
    tmp = tempfile.mkdtemp(prefix="tplcontract_")
    fixture_ok = False
    try:
        os.makedirs(os.path.join(tmp, "references", "templates"), exist_ok=True)
        fake = {"_渲染说明": {"title": "渲染"}, "title": "x", "brand_new_field": "y"}
        io.open(os.path.join(tmp, "references", "templates", "analysis-result.template.json"),
                "w", encoding="utf-8").write(json.dumps(fake, ensure_ascii=False))
        sub = _check_template_contract(tmp)          # ★ 调纯检查，不调门禁本身
        fixture_ok = (isinstance(sub, tuple) and sub[0] == ["brand_new_field"])
        print(f"  {'✅' if fixture_ok else '❌'} 自测夹具："
              f"{'新加未声明字段能被检出' if fixture_ok else f'期望 [brand_new_field]，实际 {sub}'}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    ok = ok and fixture_ok
    if not fixture_ok and not undeclared:
        print("      ⚠️ 夹具没过 = 这道门禁查不出东西，绿了也不代表安全")
    return ok


def _check_py_env(root):
    """纯检查（不打印、不建夹具）：交付脚本 ①能不能被解析 ②import 是否只用标准库。

    ★ 射程是怎么定的（**这一条是本门禁最要紧的设计**）：

    直觉做法是「扫包内所有 `.py`」，实测**当场报红 5 种第三方依赖** —— 但全是
    `dist/_friend_pkg/scripts/` 里的 PDF/OCR 脚本（09-10 的历史快照），以及本地
    `scripts/` 下 6 个**读书工具**（`extract_text.py` / `ocr_pages.py` / `pdf_extract.py` /
    `pdf_page.py` / `probe_pdf.py` / `render_cards.py`，用 pymupdf / pypdf / rapidocr / markdown）。
    那些是**本地工作流工具，不随包发布** —— 拿它们判红就是喊狼来了。

    真正的射程应该跟**承诺的语义**对齐：说明书对读者承诺「不需要 `pip install` 任何东西」，
    这个承诺只覆盖**「我让你跑的那些脚本」**。→ 判据 = **被包内文档引用过的 `.py`**。

    于是分两档：
      · 被文档引用（读者会跑）→ 有第三方依赖 = **判红**（承诺被破坏）
      · 没被文档引用（本机专用工具）→ 只 **⚠️ 提示**，不判红（但也不静默吞掉）

    另：跳过 `dist/` 等产物目录（与项目既有 `skip_dirs` 约定一致）——
    否则同一份历史快照会被报 4 遍，噪音会淹没真信号。**跳过会打印出来。**

    返回 `(syntax, third_cited, third_uncited, n_scanned, skipped)`；拿不到标准库清单时返回 None。
    """
    import ast as _ast
    import sys as _sys

    std = set(getattr(_sys, "stdlib_module_names", ()))
    if not std:
        return None                      # 老 Python 拿不到标准库清单 → 未查（不假装通过）

    SKIP = {".git", "__pycache__", ".audit_history", "node_modules", ".venv", "dist", "_archive"}

    local = set()                        # 包内自己的模块（互相 import 是正常的）
    for dp, dirs, fs in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP]
        for f in fs:
            if f.endswith(".py"):
                local.add(f[:-3])

    # 文档引用过的脚本名 —— 这些才是「读者会跑的」，环境承诺对它们负责
    cited = set()
    for doc in ("SKILL.md", "README.md", "USER-GUIDE.md"):
        p = os.path.join(root, doc)
        if not os.path.isfile(p):
            continue
        for m in re.finditer(r"([A-Za-z_][A-Za-z0-9_\-]*\.py)", io.open(p, encoding="utf-8",
                                                                      errors="ignore").read()):
            cited.add(m.group(1))

    syntax, third_cited, third_uncited, scanned, skipped = [], {}, {}, 0, []
    for dp, dirs, fs in os.walk(root):
        hit = [d for d in dirs if d in SKIP]
        if hit:
            skipped.extend(f"{d}/" for d in hit)
        dirs[:] = [d for d in dirs if d not in SKIP]
        for f in sorted(fs):
            if not f.endswith(".py"):
                continue
            scanned += 1
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, root).replace("\\", "/")
            try:
                tree = _ast.parse(io.open(p, encoding="utf-8", errors="ignore").read())
            except SyntaxError as e:
                syntax.append((rel, f"第 {e.lineno} 行：{e.msg}"))
                continue
            for node in _ast.walk(tree):
                if isinstance(node, _ast.Import):
                    names = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, _ast.ImportFrom):
                    names = [(node.module or "").split(".")[0]] if getattr(node, "level", 0) == 0 else []
                else:
                    continue
                for n in names:
                    if not n or n in std or n in local:
                        continue
                    bucket = third_cited if f in cited else third_uncited
                    bucket.setdefault(n, []).append(rel)
    return syntax, third_cited, third_uncited, scanned, sorted(set(skipped))


def gate_delivery_env(root):
    """【门禁 12】交付脚本的**环境承诺**不许撒谎（第二十轮补，2026-09-26）

    ★ 由来：说明书对使用者承诺了「**不需要 `pip install` 任何东西**，脚本只用标准库」。
      这类承诺和别的文档承诺一样会腐化 —— 哪天有人给某个脚本加一行 `import requests`，
      文档那句话当场变成假的，而**没有任何东西会报**。
      → 本门禁守这条：**文档让读者跑的脚本，必须只用标准库、且语法能过。**

    ★ 与门禁 10 的分工：门禁 10 管「文档说去读 X，X 在不在」；
      本门禁管「文档说不用装东西，脚本是不是真不用装」。**两者都是「文档承诺 ↔ 实际」的核对。**

    三态：拿不到标准库清单（Python < 3.10）→ 报**未查**，不假装通过。
    """
    print("【门禁 12】交付脚本的环境承诺（文档说「不用装任何东西」，脚本得真不用）")

    res = _check_py_env(root)
    if res is None:
        print("  ⚠️ 当前 Python 拿不到标准库清单（需 3.10+ 的 sys.stdlib_module_names）"
              " → **未查**，如实报，不计入绿")
        return None
    syntax, third_cited, third_uncited, scanned, skipped = res

    if skipped:
        print(f"  ⏭️ 已跳过产物目录：{'、'.join(skipped)}（历史快照/打包产物，不是源码）")
    for rel, msg in syntax:
        print(f"      ❌ 语法错误：`{rel}` {msg} —— 读者拿到一跑就炸")
    for mod, users in sorted(third_cited.items()):
        print(f"      ❌ 第三方依赖：`{mod}` —— 被**文档引用过**的脚本用到"
              f"（{users[0]}），与「不需要 pip 装任何东西」的承诺矛盾")
    for mod, users in sorted(third_uncited.items()):
        print(f"      ⚠️ 第三方依赖（**不判红**）：`{mod}` 被 {len(users)} 个本地工具引用"
              f"（{users[0]}）—— 文档没让读者跑它，属本机工作流工具")
    print(f"  → 扫了 {scanned} 个脚本（不含已跳过目录）：语法错误 {len(syntax)} 个、"
          f"文档引用脚本的第三方依赖 {len(third_cited)} 种、本地工具 {len(third_uncited)} 种")

    # —— 自测夹具：① 语法坏的 ② 引第三方且**被文档引用**（该红）③ 引第三方但**没被引用**（只提示）——
    tmp = tempfile.mkdtemp(prefix="pyenv_")
    fixture_ok = False
    try:
        io.open(os.path.join(tmp, "SKILL.md"), "w", encoding="utf-8").write(
            "# 假 skill\n\n跑 `scripts/uses_third.py` 渲染。\n")
        os.makedirs(os.path.join(tmp, "scripts"), exist_ok=True)
        io.open(os.path.join(tmp, "scripts", "bad_syntax.py"), "w", encoding="utf-8").write("def f(:\n")
        io.open(os.path.join(tmp, "scripts", "uses_third.py"), "w", encoding="utf-8").write("import requests\n")
        io.open(os.path.join(tmp, "scripts", "local_only.py"), "w", encoding="utf-8").write("import pymupdf\n")
        io.open(os.path.join(tmp, "scripts", "clean.py"), "w", encoding="utf-8").write("import json, os, re\n")
        io.open(os.path.join(tmp, "scripts", "sibling.py"), "w", encoding="utf-8").write("import clean\n")
        sub = _check_py_env(tmp)
        got_syn = [r for r, _m in (sub[0] if sub else [])]
        got_c, got_u = sorted((sub[1] if sub else {}).keys()), sorted((sub[2] if sub else {}).keys())
        fixture_ok = (got_syn == ["scripts/bad_syntax.py"] and got_c == ["requests"]
                      and got_u == ["pymupdf"])
        print(f"  {'✅' if fixture_ok else '❌'} 自测夹具："
              f"{'语法错判红、文档引用脚本的第三方依赖判红、本地工具只提示、标准库不误报' if fixture_ok else f'期望 [bad_syntax.py]+[requests]+[pymupdf]，实际 {got_syn}+{got_c}+{got_u}'}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    ok = (not syntax) and (not third_cited) and fixture_ok
    if not fixture_ok and not syntax and not third_cited:
        print("      ⚠️ 夹具没过 = 这道门禁查不出东西，绿了也不代表安全")
    return ok


def _run_gate(label, thunk):
    """跑一道门禁，**捕获异常并记为失败** —— 一道门禁崩了不该让整份报告消失。

    ★ 由来（第二十轮，2026-09-26）：反证门禁 12 时给渲染器注入一行 `import requests`，
      门禁 4（管线冒烟）会**真的 import 渲染器** → 抛 `ModuleNotFoundError` →
      **整个脚本崩掉**，后面 8 道门禁一道都没跑，读者只看到一段 traceback。
      这是最坏的一类失败：不是「某个检查报红」，而是**报告根本不存在**。

    → 统一包装（`thunk` 是零参可调用，因为各门禁参数不同：有的吃 root、有的吃 index/目录）。
      语义上注意区分三态：
      · **崩溃 ≠「未查」**：未查是依赖不在（本包本就不该有），崩溃是检查本身出了问题。
        崩溃**判红**（它说明这个包有实质毛病，或这个检查有 bug，两种都要人来看）。
      · 其余门禁**继续跑** —— 一份只有第一道门禁的报告，比没有报告好不了多少。
    """
    try:
        return thunk()
    except Exception as e:
        print(f"      ❌ **这道门禁自己崩了**：{type(e).__name__}: {e}")
        print("         → 记为**失败**（不是「未查」、更不是通过）；其余门禁继续跑")
        return False


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

    ok1 = _run_gate("1 空行", lambda: gate_empty_rows(adir, [os.path.join(root, "**", "反模式*.html")]))
    ok2 = _run_gate("2 匹配回归", lambda: gate_matching(root))
    ok3 = _run_gate("3 字段齐整", lambda: gate_field_integrity(index))
    ok4 = _run_gate("4 管线冒烟", lambda: gate_pipeline(root))
    ok5 = _run_gate("5 必填项承载力", lambda: gate_required_fields(root))
    ok6 = _run_gate("6 章节编号", lambda: gate_numbering(root))
    print()
    print("【门禁 7】共用词覆盖检查（关键词交集必须有归属决定，不许留白）")
    ok7 = _run_gate("7 共用词覆盖", lambda: gate_shared_words(root))
    ok8 = _run_gate("8 卡库卫生", lambda: gate_card_hygiene(root))
    ok9 = _run_gate("9 取值清单一致", lambda: gate_list_consistency(root))
    print()
    print("【门禁 10】文档引用完整性")
    ok10 = _run_gate("10 文档引用", lambda: gate_doc_references(root))
    print()
    print("【门禁 11】交付模板字段归宿声明")
    ok11 = _run_gate("11 模板归宿声明", lambda: gate_template_render_contract(root))
    print()
    print("【门禁 12】交付脚本的环境承诺")
    ok12 = _run_gate("12 脚本环境承诺", lambda: gate_delivery_env(root))

    print()
    print("=" * 78)
    # 三态：True 通过 / False 失败 / **None = 未查（不计入绿）**
    _gates = [("1 空行", ok1), ("2 匹配回归", ok2), ("3 字段齐整", ok3),
              ("4 管线冒烟", ok4), ("5 必填项承载力", ok5), ("6 章节编号", ok6),
              ("7 共用词覆盖", ok7), ("8 卡库卫生", ok8), ("9 取值清单一致", ok9),
              ("10 文档引用", ok10), ("11 模板归宿声明", ok11), ("12 脚本环境承诺", ok12)]
    _unrun = [n for n, r in _gates if r is None]
    _fail = [n for n, r in _gates if r is False]
    allok = not _fail                      # 未查**不判红**，但也**不算绿**
    if _unrun:
        print(f"  ℹ️ 未执行的门禁（依赖本包不含）：{'、'.join(_unrun)}"
              f" —— **未查 ≠ 通过**，如实报出，不并入绿")
    # 第十三轮 N5：夹具告警**汇总成一行**（不是 26 行原文）——证据文件里真失败要能一眼看见。
    print(fixture_warning_summary())
    # 三态结论：🔴 有失败 / 🟡 实跑项全过但有未查项 / 🟢 实跑项全过且无未查
    if _fail:
        print(f"结论： 🔴 有门禁不过（{'、'.join(_fail)}）")
    elif _unrun:
        print(f"结论： 🟡 跑到的门禁全过；**{'、'.join(_unrun)} 未查**（本包不含其依赖）")
    else:
        print("结论： 🟢 全绿")
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
