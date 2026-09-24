#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""anti_patterns.py — 反模式系统的共享实现（加载 / 匹配 / 渲染）

**为什么有这个模块**：反模式层原先只做在 `build_standalone_analysis.py`（案例专用脚本）里，
而通用交付管线 `analysis_to_html.py` 没有它——按 SKILL.md 走的正式交付根本不会出现反模式层。
故把实现抽成单一来源，两个渲染器共用，避免两套逻辑分叉。

对外接口：
    index_path(root)                 → 默认反模式表路径（RA_AP_INDEX 可覆盖）
    load_index(path)                 → {AP-编号: {name, keywords, kw_list, symptom, why, how, card}}
    keywords(raw)                    → 关键词列表（顿号/逗号/斜杠/竖线 均为分隔符）
    match(note, index, gate=True)    → 命中编号列表（按命中数排序）；gate=意图闸门
    card(aid, index, **override)     → 单条反模式卡 HTML（空值行自动跳过）
    layer(ids, index, notes=None)    → 反模式层 HTML（条件触发，上限 2 条）
    CSS                              → 反模式层样式（渲染器注入 <style>）
    CN_NUM                           → 中文序号，供渲染器动态编号

设计红线（见 references/ANTI-PATTERNS.md「匹配原则」）：
  1. 条件触发：不命中返回空串，普通解析不多一个元素
  2. 上限 2 条：全弹＝噪音
  3. 关键词要带错误意图；闸门只是粗筛，宁可放宽（写窄会误伤合法自述）
"""
import io
import os
import re

CN_NUM = "一二三四五六七八九十"


def index_path(root):
    """反模式表路径：默认 <root>/references/ANTI-PATTERNS.md，可用 RA_AP_INDEX 覆盖。"""
    return os.environ.get("RA_AP_INDEX", os.path.join(str(root), "references", "ANTI-PATTERNS.md"))


def esc(t):
    return (str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def inline(t):
    """字段内的极简 markdown：**加粗** 与 `代码`，其余原样转义。"""
    t = esc(t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    return t


FIELDS = (("- **匹配关键词**", "keywords"), ("- **症状**", "symptom"),
          ("- **为什么错**", "why"), ("- **怎么防**", "how"),
          ("- **挂卡**", "card"))


def load_index(path=None):
    """解析 ANTI-PATTERNS.md → {AP-编号: {...}}

    一行一字段；缩进子行会并入上一个命中的字段（兜底，防多行写法被静默丢成空值）。
    """
    if path is None:
        path = index_path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        t = io.open(path, encoding="utf-8").read()
    except (FileNotFoundError, OSError):
        return {}
    pats, cur, last_key = {}, None, None
    for ln in t.split("\n"):
        m = re.match(r"^### (AP-\d+)\s*(.+)$", ln.strip())
        if m:
            cur = m.group(1)
            pats[cur] = {"name": m.group(2).strip(), "keywords": [], "symptom": "",
                         "why": "", "how": "", "card": ""}
            last_key = None
            continue
        if cur is None:
            continue
        raw, s = ln.rstrip(), ln.strip()
        hit = False
        for pre, key in FIELDS:
            if s.startswith(pre):
                pats[cur][key] = s[len(pre):].lstrip("：: ").strip()
                last_key, hit = key, True
                break
        if not hit and last_key and raw[:1] in (" ", "\t") and s.startswith("- "):
            pats[cur][last_key] = (pats[cur][last_key] + " " + s.lstrip("- ").strip()).strip()
    for ap in pats.values():
        ap["kw_list"] = keywords(ap["keywords"])
    return pats


def keywords(raw):
    """关键词串 → 列表（顿号/中文逗号/斜杠/竖线/英文逗号 均为分隔符）"""
    parts = re.split(r"[、，,/／|]+", str(raw))
    return [p.strip().strip('"“”') for p in parts if p.strip()]


# 意图闸门：粗筛「这句像不像在说自己犯错」，挡住纯内容提问。
#
# 设计依据（第六轮复验 K2 三条 + 本机实测）：
#   · 真正决定误报的是**关键词宽度**（关键词窄则误报为 0）；闸门是粗筛。
#   · 但闸门**不是冗余**：关闸实测，27 条「正常提问/正常描述」有 25 条会被宽关键词打中。
#     （这条纠正了第四轮的判断——当时那批误报样本没打到关键词宽度上。）
#   · 闸门过窄会**内耗**：关键词本可命中的合法自述被自己挡掉（K2-a/b/c 全是这类）。
#     → 故闸门取「宁可放宽」策略，安全交给关键词。
#
# 五类信号，命中任一即视为「在自述」：
GATE_RE = re.compile(
    # ① 第一人称 + 差错/习惯词（窗口 30 字；曾为 {0,12}，「我一看到 however 就以为转折」差 1 字被拦）
    r"我\s*[^。！？\n]{0,30}?(错|搞反|搞混|搞错|分不清|分不开|误判|误解|读错|选错|看错|选|栽|翻车|吃亏|漏|忽略"
    r"|没注意|没看清|不会|不懂|老是|总是|经常|每次|一直|容易|习惯|以为|觉得|感觉"
    r"|太大|太宽|太空|太细|太碎|太泛|太抽象|不准确)"
    # ② 独立差错动词 / 出错结构（含「一看到…就」这类无第一人称的关联式）
    r"|(错在|搞反了|搞混了|分不清|误判|误解了|栽在|翻车|总把|老是|每次都|容易把|漏了|看漏|忽略|没看清"
    r"|没注意|以为.*?是|总是把|经常把|就选|动不动|一看到|一遇到|碰到.*?就)"
    # ③ 第一人称习惯 / 自我判定（「我觉得」在此放行：AP-02 关键词「我觉得算」需要它）
    r"|(我的问题|我的毛病|我总|我老是|我经常|我每次|我容易|我不会|我总是|我一直|我觉得|我感觉)"
    # ④ 无第一人称的自述起手式（K2-c：「概括起来要么太细要么太空」原被一刀切拦掉）
    r"|(概括起来|做起来|写起来|答起来|分析起来|这类题|这类题目|这种题|每次遇到)"
    # ⑤ 作答证据痕迹（对答案/复盘/被骗——这类明说了「我做错了」）
    r"|(明明有|明明想到|明明说|明明选|对答案|复盘|选成|选错|答错|丢分|扣分|被选项骗|被骗|上当了)"
)

# ===== 施事判定（2026-09-24 第七轮 L2 补）=====
#
# 问题：关键词匹配「词」，不匹配「词的语法角色」。同一串字，主语不同、含义相反——
#   · 「**这段**概括得太宽了」→ 主语是文章 → 用户在**评价** → 不该弹
#   · 「**我**概括得太宽」    → 主语是用户 → 在**自述** → 该弹
# 第七轮实测：生产口径下这类误报 8/14（用户评价文章，系统却断言「你自述了这个错误」）。
#
# 判据：关键词命中后，看它**左侧窗口**里的主体是谁——是「这段/这个选项/作者/文中」→ 否决。
# 两个例外（保护真自述）在 strong_self() 里。

# 评价对象：毛病属于文章/题目，不属于用户
EVAL_OBJECT_RE = re.compile(
    r"(这段|这句|这一句|这个选项|这道题|这题|这个题|这个干扰项|这个错误选项|这个错项|"
    r"这两句|该段|该句|该选项|该题|本段|本句|这篇|这篇文章|全文|"
    r"作者|文中|原文|文本|第[一二三四五六七八九十\d]+段)")

# 认知框架前缀：「我觉得 X」里的 X 是**看法**，不是**行为**，故不享受强自指保护
COGNITION_RE = re.compile(r"我\s*(觉得|感觉|认为|看|读|想|发现|注意到|判断|估计)")

# 强自指（我 + 行为/习惯）：明说自己在犯错
SELF_STRONG_RE = re.compile(
    r"我[^。！？\n]{0,12}?(总是|老是|经常|每次|一直|容易|习惯|分不清|搞反|搞混|漏了|看漏|忽略"
    r"|没注意|没看清|选错|选成|错在|做错|答错|不会|犯|踩)"
    r"|我的(问题|毛病|习惯)"
    r"|(总把|总是把|经常把)")

# 频率副词：出现即说明在讲「习惯」，而习惯只能属于人、不可能是文章的性质
FREQ_RE = re.compile(r"(我总是|我老是|我经常|我每次|我一直|老是|总是|经常|每次都|动不动|一碰到|一遇到)")

# 左窗口宽度（字）：主体词距关键词多远算「这个关键词的主语」
WIN = 10


def strong_self(note):
    """强自指两层判定（任一成立即保护，不再走评价对象否决）

    ① 频率副词独立成立：「老是/总是/经常」说的是习惯 → 习惯属于人
       （保住「我看这段**总是**看不出层级」——提到段落，但说的是自己）
    ② 剥离认知框架后找「我 + 行为」：「我觉得 X」里的 X 是看法，不予保护
       （否则「我觉得这段的概括**漏了**重点」会被误当成自述）
    """
    if FREQ_RE.search(note):
        return True
    return bool(SELF_STRONG_RE.search(COGNITION_RE.sub("", note)))


def agent_ok(note, aid, index):
    """施事判定：这条命中该不该保留（毛病属于用户，还是属于文章？）"""
    if strong_self(note):
        return True
    for k in (index[aid].get("kw_list") or keywords(index[aid].get("keywords", ""))):
        i = note.find(k)
        if i < 0:
            continue
        if EVAL_OBJECT_RE.search(note[max(0, i - WIN): i]):
            return False
    return True


def match(note, index, gate=True):
    """扫「用户自述 / 错因」→ 命中编号列表（按关键词命中数排序）

    gate=True（**生产口径**）三层：
      ① 意图闸门：无自述信号直接返回空（防把内容描述当认错）
      ② 关键词命中
      ③ **施事判定**：关键词的主语是「这段/这个选项/作者」而非「我」→ 否决（用户在评价，不是自述）
    gate=False（**裸关键词口径**）：只做 ②，用于测**关键词宽度**（宽度指标，不设 0 阈值）。

    注意：字符串匹配只是**兜底**——「错选项构造」「错因归类」这两类触发
    字符串判不出来（自动匹配只认「自述」），由 agent 判定后用 JSON 的
    `anti_patterns` + `ap_trigger` 显式传入。
    """
    if not note:
        return []
    if gate and not GATE_RE.search(note):
        return []
    hits = []
    for aid, ap in index.items():
        kws = ap.get("kw_list") or keywords(ap.get("keywords", ""))
        n = sum(1 for k in kws if k and k in note)
        if n:
            hits.append((aid, n))
    hits.sort(key=lambda x: (-x[1], x[0]))
    out = [a for a, _ in hits]
    if gate:
        out = [a for a in out if agent_ok(note, a, index)]
    return out


def card(aid, index, symptom=None, why=None, how=None):
    """单条反模式卡 HTML（警示色，与知识卡区分）

    字段策略：四项必填（症状/为什么错/怎么防），渲染时**空值跳过**——
    兜底防「新增条目漏填」导致用户可见层出现空行。
    """
    ap = index.get(aid)
    if not ap:
        return ""
    c = re.sub(r"[（(].*?[)）]", "", ap.get("card", "")).split()
    c = c[0] if c else ""            # 剥掉「（类5）」这类内部细分标签
    rows = [
        ("你这次的症状", inline(symptom or ap["symptom"])),
        ("为什么错", inline(why or ap["why"])),
        ("怎么防", inline(how or ap["how"])),
    ]
    body = "".join(
        '<div class="ap-row"><span class="ap-k">%s</span><span class="ap-v">%s</span></div>' % (k, v)
        for k, v in rows if v and v.strip()
    )
    return ('<div class="ap">'
            '<div class="ap-hd"><span class="ap-ico">!</span>'
            '<div class="ap-ttl">反模式 %s · %s<span>本次命中</span></div></div>'
            '<div class="ap-bd">%s'
            '<div class="ap-ft">📖 原卡：%s</div>'
            '</div></div>') % (aid, esc(ap["name"]), body, esc(c) or "见反模式表")


# 反模式层的**触发源 → 条幅文案**。
#
# 必须如实标注来源：第六轮 L3 冷启动实测抓到——一个「纯提问、无自述」的交付里，
# 条幅却写着「来自你自述的错误」。这等于**把用户的提问断言成他在认错**，
# 正是本系统最该避免的误读；而且它还会反过来诱导产出把「选项构造」写成
# 「你选了 X」（实测同一次冷启动里就出现了这种臆断）。
# 见 SKILL.md「反模式响应」节：未声明来源时不得断言。
TRIGGER_LABELS = {
    "自述": "来自你自述的错误",
    "错选项构造": "来自本题错选项的构造",
    "错因": "来自你写的错因",
    "主动点名": "你点名的反模式",
}
# 来源未声明时的中性文案：只陈述「相关」，不臆断用户做过什么
DEFAULT_TRIGGER_LABEL = "与本题证据链相关"


def layer(ids, index, notes=None, limit=2, source=None):
    """反模式层（条件触发）：不命中返回空串；上限 limit 条，超出只列名。

    source：触发源（见 TRIGGER_LABELS）。**不确定就传 None**——不要猜，
    猜错会把「用户的提问」说成「用户的错误」。
    """
    if not ids:
        return ""
    notes = notes or {}
    shown = [a for a in ids if a in index][:limit]
    if not shown:
        return ""
    body = "".join(card(a, index, **{k: v for k, v in notes.get(a, {}).items()
                                    if k in ("symptom", "why", "how")})
                   for a in shown)
    more = ""
    rest = [a for a in ids if a in index][limit:]
    if rest:
        names = "、".join("%s %s" % (a, index[a]["name"]) for a in rest)
        more = '<div class="ap-more">另有命中（本次从略，避免噪音）：%s</div>' % esc(names)
    bar = TRIGGER_LABELS.get(source or "", DEFAULT_TRIGGER_LABEL)
    return ('<div class="ap-layer"><div class="ap-bar">⚠️ 反模式层 · %s</div>' % esc(bar)
            + body + more + '</div>')


def hint(ids, index):
    """题内一行提示（可选）：`⚠️ 反模式命中：AP-02 …`"""
    names = [a for a in ids if a in index]
    if not names:
        return ""
    txt = "、".join("%s %s" % (a, index[a]["name"]) for a in names)
    return '<div class="ap-inline">⚠️ 反模式命中：%s</div>' % esc(txt)


def resolve(data, index):
    """从交付 JSON 决定「本次要挂哪些反模式」——条件触发的判定处。

    JSON 字段：
      user_note      字符串。使用者自述的错误/错因 → 自动匹配（过意图闸门）
      anti_patterns  列表。agent 判定后显式指定，元素可为 "AP-02" 或
                     {"id": "AP-02", "symptom": "…", "why": "…", "how": "…"}（覆盖默认文案）
                     用于字符串匹配兜不住的触发：错选项构造、错因归类、主动点名
      ap_trigger     字符串（可选）。**声明触发源**，决定条幅文案，取值：
                     "自述" / "错选项构造" / "错因" / "主动点名"

    返回 (ids, notes, source)：
      source 用于条幅文案；**判不准就返回 None**（中性文案），不要臆断——
      把「用户在提问」说成「用户在认错」是本系统最不能犯的错。
      推断规则：JSON 显式声明 > 仅由 user_note 自动匹配（＝自述）> None（混合/未声明）
    """
    ids, notes = [], {}
    explicit = False
    for it in (data.get("anti_patterns") or []):
        if isinstance(it, str):
            aid = it.strip()
        elif isinstance(it, dict):
            aid = str(it.get("id", "")).strip()
            if aid:
                notes[aid] = {k: it[k] for k in ("symptom", "why", "how") if it.get(k)}
        else:
            continue
        if aid and aid in index:
            explicit = True
            if aid not in ids:
                ids.append(aid)
    auto = []
    for aid in match(data.get("user_note", ""), index):
        if aid not in ids:
            auto.append(aid)
            ids.append(aid)

    trig = str(data.get("ap_trigger", "") or "").strip()
    if trig in TRIGGER_LABELS:
        source = trig
    elif auto and not explicit:
        source = "自述"
    else:
        source = None      # 混合来源或未声明 → 不臆断
    return ids, notes, source


CSS = """
/* ===== 反模式层（警示红，与知识卡橙区分）===== */
.ap-layer{margin:26px 0 10px}
.ap-bar{background:#fdeaea;border:1px solid #f0d5d5;border-radius:8px 8px 0 0;padding:8px 14px;font-size:13.5px;font-weight:600;color:#7a1f1f}
.ap{background:#fff;border:1px solid #f0d5d5;border-top:none;overflow:hidden}
.ap:last-of-type{border-radius:0 0 10px 10px}
.ap-hd{display:flex;gap:9px;align-items:flex-start;padding:11px 14px;background:#fdf4f4;border-bottom:1px solid #f5dede}
.ap-ico{flex:0 0 auto;width:21px;height:21px;border-radius:50%;background:#a32d2d;color:#fff;font-size:12.5px;display:flex;align-items:center;justify-content:center;margin-top:2px;font-weight:700}
.ap-ttl{font-size:14px;font-weight:600;color:#7a1f1f;line-height:1.45}
.ap-ttl span{display:block;font-size:11.5px;color:#a32d2d;font-weight:400;margin-top:2px}
.ap-bd{padding:10px 14px}
.ap-row{display:flex;gap:8px;margin:7px 0;font-size:13.5px;align-items:flex-start}
.ap-k{flex:0 0 76px;color:#9a7b7b;font-size:12.5px;padding-top:2px}
.ap-v{flex:1}
.ap-v em{font-style:normal;background:#fdeaea;padding:1px 5px;border-radius:3px;color:#7a1f1f}
.ap-v code{background:#fdf4f4;border-radius:3px;padding:0 3px;font-size:12px}
.ap-ft{border-top:1px dashed #f0dada;margin-top:9px;padding-top:7px;font-size:11.5px;color:#9a7b7b}
.ap-more{background:#fdf4f4;border:1px solid #f0d5d5;border-top:none;border-radius:0 0 8px 8px;padding:7px 14px;font-size:12px;color:#8a6a6a}
.ap-inline{background:#fdeaea;border-left:3px solid #a32d2d;border-radius:0 6px 6px 0;padding:6px 10px;font-size:12.5px;color:#7a1f1f;margin:8px 0}
"""
