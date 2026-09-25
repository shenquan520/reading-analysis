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
    print("【门禁 7】共用词覆盖检查（关键词交集必须有归属决定，不许留白）")
    ok7 = gate_shared_words(root)
    ok8 = gate_card_hygiene(root)

    print()
    print("=" * 78)
    allok = ok1 and ok2 and ok3 and ok4 and ok5 and ok6 and ok7 and (ok8 is not False)
    # 第十三轮 N5：夹具告警**汇总成一行**（不是 26 行原文）——证据文件里真失败要能一眼看见。
    print(fixture_warning_summary())
    print("结论：", "🟢 全绿" if allok else "🔴 有门禁不过")
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
