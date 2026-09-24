#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阅读分析结果 → 网页 生成器
用法: python analysis_to_html.py <分析结果.json> [-o 输出.html]

反模式层（条件触发）：JSON 里给 user_note（使用者自述）即自动匹配，
或用 anti_patterns 显式指定（错选项构造 / 错因归类 / 主动点名三类靠 agent 判定）。
不命中则不出现在交付里。

逐题字段（**缺口栏与可迁移原则是规范里的「逐题必填」**，原文见 SKILL.md「交付结构定格」）：
  questions[].gap       缺口：没有卡能解释的判断（**无则写「无」**）——规范称其为「最值钱的产出」
  questions[].transfer  可迁移原则：这道题的解法能迁移到哪类题
  · 中文键同样接受：`缺口` / `可迁移原则`
  · 缺了不报错，但**会往 stderr 告警**（不静默）——学生看的页面里不塞占位符
  · 二者任一存在即渲染；`gap` 为空但 `transfer` 有值时，缺口渲染成「无」（规范用词）

复盘前缀（随场景变化，**不要写死**）：
  review.kind = "错题" → 「错题归因：」 ／ "要点" → 「本题要点：」
  未声明 → **中性「归因：」**（脚本不替使用者假定「本次有错题」）
  ⚠️ 与反模式条幅同一套做法：**硬编码前缀 + 场景会变 = 断言使用者没做过的事**。
"""
import json, pathlib, sys, html as H, re

BASE = pathlib.Path(__file__).parent
ROOT = BASE.parent                      # skill 根：references/ 与 dist/ 的上一级
sys.path.insert(0, str(BASE))
import anti_patterns as aps             # 反模式实现（与 build_standalone_analysis.py 共用）

CSS = """
body{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;max-width:780px;margin:0 auto;padding:24px 18px 60px;color:#1f2328;line-height:1.75;background:#fff}
h1{font-size:20px;border-bottom:3px solid #4f8cff;padding-bottom:10px;margin-top:0}
h2{font-size:16px;border-left:5px solid #4f8cff;padding-left:12px;background:#f6f8fa;padding:6px 12px;margin:26px 0 10px}
h3{font-size:14px;margin:16px 0 6px}
.meta{color:#57606a;font-size:12.5px;margin-bottom:18px}
.flow{background:#f0f4ff;border:1px solid #d0e2ff;border-radius:8px;padding:10px 14px;font-size:13.5px;margin:8px 0}
/* 段落层 5 件套 */
.p-func{background:#e8f1ff;padding:6px 12px;font-size:13px;font-weight:700;color:#185FA5;border-bottom:1px solid #d0e2ff}
.p-zh{padding:8px 12px;font-size:13.5px;line-height:1.9;color:#3a4450;background:#fafbfc;border-top:1px dashed #e3e8ee}
.p-sum{padding:8px 12px;font-size:13px;line-height:1.8;background:#f6f9ff;border-top:1px solid #e8eefb;color:#1f2328}
.p-rel{padding:8px 12px;font-size:13px;line-height:1.8;background:#f7fdf9;border-top:1px solid #e6f3ec;color:#1f2328}
.p-rel b,.p-sum b{color:#185FA5}
table{border-collapse:collapse;width:100%;margin:8px 0;font-size:13px}
th,td{border:1px solid #d0d7de;padding:6px 10px;text-align:left;vertical-align:top}
th{background:#f0f4ff;font-weight:600}
.q{border:1px solid #d0d7de;border-radius:10px;padding:12px 16px;margin:14px 0}
.q .qn{font-weight:700;color:#185FA5}
.q .ans{display:inline-block;background:#4f8cff;color:#fff;padding:2px 10px;border-radius:12px;font-size:13px;font-weight:700;margin:4px 0}
.q .why{background:#f6f8fa;border-radius:6px;padding:8px 12px;font-size:13px;margin:8px 0}
.q .cards{font-size:12px;color:#57606a}
.wrong{font-size:12.5px;color:#a11;margin:2px 0}
.wrong b{color:#a11}
.take{background:#f0f4ff;border-radius:8px;padding:10px 14px;font-size:13px;margin:6px 0}
.gap{background:#1a1a1a;color:#e5e7eb;border-radius:8px;padding:8px 14px;margin-top:8px;font-size:14px}
.note{background:#f0f4ff;border-radius:8px;padding:8px 14px;margin-top:6px;font-size:13px}
blockquote{border-left:4px solid #4f8cff;margin:10px 0;padding:8px 14px;background:#f6f8fa;color:#444;font-size:13.5px}
code{background:#f0f2f5;padding:1px 5px;border-radius:4px;font-size:12.5px}
/* 便利贴内部分支标签（2026-09-02：点卡→选「本题运用/知识原理」分支，纯CSS无JS） */
.tabr{display:none}
.tablabel{cursor:pointer;display:inline-block;padding:4px 14px;border-radius:14px;background:#eef1f4;color:#57606a;font-size:12.5px;margin:10px 8px 0 0;user-select:none}
input.ca:checked ~ label.la,input.cb:checked ~ label.lb{background:#4f8cff;color:#fff;font-weight:700}
.pane{display:none;padding:10px 2px 0}
input.ca:checked ~ .pane-a,input.cb:checked ~ .pane-b{display:block}
/* 便利贴卡片（2026-09-02：依据卡点开看内容，贴纸上墙样式） */
.cnote{background:linear-gradient(#fffbe6,#fff7cc);border:1px solid #e8d98a;border-radius:4px;box-shadow:2px 3px 8px rgba(0,0,0,.10);margin:10px 0;transform:rotate(-.4deg);position:relative;font-size:12.5px}
.cnote::before{content:"";position:absolute;top:-9px;left:50%;width:70px;height:18px;margin-left:-35px;background:rgba(255,230,120,.75);border:1px solid rgba(200,170,60,.35);transform:rotate(-2deg)}
.cnote>summary{cursor:pointer;list-style:none;padding:10px 14px;font-weight:700;color:#7a5c00;user-select:none}
.cnote>summary::-webkit-details-marker{display:none}
.cnote>summary::after{content:"▸ 点开看卡";float:right;color:#b08d00;font-weight:400;font-size:11.5px}
.cnote[open]>summary::after{content:"▾ 收起"}
.cnote .cnote-body{padding:0 14px 12px;color:#4a3f00;line-height:1.7}
.cnote .cnote-h{display:block;font-weight:700;margin:8px 0 2px;color:#6b5200}
.cnote .cnote-q{border-left:3px solid #e0c95e;padding-left:8px;margin:4px 0;color:#7a5c00}
"""

def esc(s):
    return H.escape(str(s))

CARDS_DIR = BASE.parent / 'references' / 'cards'

def _inline(t: str) -> str:
    t = esc(t)
    t = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', t)
    t = re.sub(r'`([^`]+)`', r'<code>\1</code>', t)
    return t

def md_to_html(md: str) -> str:
    out = []
    for ln in md.splitlines():
        t = ln.strip()
        if not t:
            continue
        if re.fullmatch(r'[\-:|\s]+', t):
            continue
        m = re.match(r'^(#{1,4})\s+(.*)', t)
        if m:
            out.append(f'<span class="cnote-h">{_inline(m.group(2))}</span>')
        elif t.startswith('>'):
            out.append(f'<div class="cnote-q">{_inline(t.lstrip("> "))}</div>')
        elif t.startswith(('- ', '* ')):
            out.append('• ' + _inline(t[2:]) + '<br>')
        elif t.startswith('|'):
            out.append(f'<span style="font-size:11.5px">{_inline(t)}</span><br>')
        else:
            out.append(_inline(t) + '<br>')
    return '\n'.join(out)

def strip_coords(md: str):
    """剥离训练材料内部坐标（用户看不到那些材料）：PRACTICE NN、讲义 pNN、书内 NN、《英文篇名》、QNN 题号、case-N 案例号。"""
    md = re.sub(r'[（(][^（）()]*?(?:PRACTICE\s*\d+|讲义\s*p\d+|书内\s*\d{2,3}|case-\d+)[^（）()]*[）)]', '', md, flags=re.I)
    md = re.sub(r'（讲义\s*p\d+[^）]*）|（书内\s*\d{2,3}[^）]*）', '', md)
    md = re.sub(r'PRACTICE\s*\d+\s*《[^》]*》[：:]?\s*', '', md, flags=re.I)
    md = re.sub(r'PRACTICE\s*\d+[：:.\s]*', '', md, flags=re.I)
    md = re.sub(r'讲义\s*p\d+\s*(原话)?[：:]?\s*', '', md)
    md = re.sub(r'书内\s*[\d.]+(-[\d.]+)?[：:]?\s*', '', md)
    md = re.sub(r'（?见?\s*B042\s*§[\d.]+\s*）?', lambda m: '', md) if False else md
    md = re.sub(r'《[A-Za-z][^》]{2,40}》', '原文', md)
    md = re.sub(r'(?<![A-Za-z0-9])Q\d{1,3}(?![0-9])', '', md)
    md = re.sub(r'（case-\d+\s*）|（见\s*case-\d+）', '', md)
    md = re.sub(r'\s{2,}', ' ', md)
    md = re.sub(r' ([，。；：、])', r'\1', md)
    return md

def strip_source(md: str):
    """便利贴显示时切掉「来源与版本」段 + 内部坐标（2026-09-02）。"""
    cut = md.find('来源与版本')
    if cut != -1:
        md = md[:cut]
    md = strip_coords(md)
    return md.rstrip() + '\n'

def _card_title(path):
    """读卡文件首行标题，去掉编号前缀。"""
    try:
        for ln in path.read_text(encoding='utf-8').splitlines():
            if ln.startswith('# '):
                t = ln[2:].strip()
                import re as _re
                return _re.sub(r'^[AB]?\d{3}\s*', '', t)
    except Exception:
        pass
    return ''

def resolve_card(label: str):
    """按卡名定位卡文件：B048 / A003 编号优先，其次主题名模糊匹配。"""
    m = re.match(r'^\s*([ABR])(\d{1,3})', label)
    dirs = {'A': 'A-analysis', 'B': 'B-skills', 'R': 'REVIEW'}
    if m:
        d = CARDS_DIR / dirs[m.group(1)]
        if d.exists():
            for f in sorted(d.glob(m.group(2).zfill(3) + '-*.md')):
                return f
    for sub in ('B-skills', 'A-analysis'):
        d = CARDS_DIR / sub
        if d.exists():
            for f in sorted(d.glob('*.md')):
                if f.stem in label or label in f.stem:
                    return f
    return None

def _paragraph_blocks(data: dict):
    """把交付 JSON 里的段落数据**归一化**成 5 件套列表。

    容忍的写法（三个零记忆冷启动实测各自造了不同的，全部兼容）：
      A. passage.items = [{"en","zh","function","summary","relation"}, …]
      B. passage.paragraphs + 平行数组 functions / translations / summaries / relations
      C. 顶层或 passage 内 paragraph_notes = [{"trans","function","summary","relation"}, …]（按序号合并）
         ⚠️ function 是**声明字段之一**，不是额外可选项（第九轮 N2 修：代码早就读它，文档漏写 →
            照文档字面写会静默丢掉段旨；门禁 fixture 因「比合同多给一个字段」而一直绿着，掩盖了这个缺口）
    字段别名：zh/trans/translation 视为译文；function/func/段旨 视为段旨；
             summary/段意概括 视为段意；relation/段间关系 视为段间关系。
    """
    ps = data.get("passage", {}) or {}
    items = ps.get("items") or []
    paras = ps.get("paragraphs") or []
    n = max(len(paras), len(items))
    if n == 0:
        return []

    def par(key, *aliases):
        v = ps.get(key) or []
        return v if isinstance(v, list) else []

    funcs = par("functions") or par("funcs")
    zh    = par("translations") or par("trans") or par("zh")
    summ  = par("summaries") or par("summary")
    rel   = par("relations") or par("relation")
    # paragraph_notes：顶层或 passage 内，两种都收
    notes = data.get("paragraph_notes") or ps.get("paragraph_notes") or []

    def pick(seq, i, *keys):
        if i < len(seq):
            it = seq[i]
            if isinstance(it, dict):
                for k in keys:
                    if it.get(k):
                        return it[k]
            elif it:
                return it
        return ""

    blocks = []
    for i in range(n):
        it = items[i] if i < len(items) and isinstance(items[i], dict) else {}
        note = notes[i] if i < len(notes) and isinstance(notes[i], dict) else {}
        blocks.append({
            "en":       it.get("en") or it.get("text") or (paras[i] if i < len(paras) else ""),
            "zh":       it.get("zh") or it.get("trans") or note.get("trans") or pick(zh, i, "zh", "trans") or "",
            # function 也要读 note（第八轮 M3）：注释里写法 C 只写了 paragraph_notes，
            # 若这里不读 note["function"]，照写法 C 字面写的 agent 会**静默丢掉段旨**
            "function": it.get("function") or it.get("func") or note.get("function") or note.get("func") or pick(funcs, i, "function", "func", "段旨") or "",
            "summary":  it.get("summary") or note.get("summary") or pick(summ, i, "summary", "段意概括") or "",
            "relation": it.get("relation") or note.get("relation") or pick(rel, i, "relation", "段间关系") or "",
        })
    return blocks


def _para_html(b: dict) -> str:
    """单个段落块：原文 / 译文 / 段旨 badge / 段意概括 / 段间关系"""
    out = ['<div style="margin:12px 0;border:1px solid #d0d7de;border-radius:8px;overflow:hidden">']
    badge = f'📌 段旨 · {esc(b["function"])}' if b["function"] else ''
    out.append(f'<div class="p-func">{badge}</div>')
    out.append(f'<div style="padding:10px 12px;font-size:14px;line-height:1.9">{esc(b["en"])}</div>')
    if b["zh"]:
        out.append(f'<div class="p-zh">{esc(b["zh"])}</div>')
    if b["summary"]:
        out.append(f'<div class="p-sum"><b>段意概括</b>：{esc(b["summary"])}</div>')
    if b["relation"]:
        out.append(f'<div class="p-rel"><b>段间关系</b>：{esc(b["relation"])}</div>')
    out.append('</div>')
    return "".join(out)


# 复盘前缀标签（第十一轮 L3-2）——与反模式条幅同一套「声明式 + 中性兜底」做法
REVIEW_LABELS = {
    "错题": "错题归因：",        # 使用者提交了错选项 / 错因
    "要点": "本题要点：",        # 无错题，只是复盘要点
    "__neutral__": "归因：",     # **未声明 → 中性文案**，脚本不替使用者假定「这是错题」
}


def build(data: dict) -> str:
    AP_INDEX = aps.load_index(aps.index_path(ROOT))
    missing_gap = []             # 逐题收集「缺口/可迁移原则两项皆空」的题号（见收尾告警）
    missing_func = []            # 逐段收集「段旨缺失」的段号（第十二轮 P4：与 gap 告警口径对齐）
    out = ['<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">',
           '<meta name="viewport" content="width=device-width,initial-scale=1.0">',
           f'<title>{esc(data.get("title","阅读分析"))}</title>',
           f'<style>{CSS}{aps.CSS}</style></head><body>']
    # 标题
    out.append(f'<h1>📖 {esc(data.get("title","阅读分析"))}</h1>')
    if data.get("passage_source"):
        out.append(f'<div class="meta">来源：{esc(data["passage_source"])}</div>')
    # 文本层分析
    s = data.get("summary", {})
    if s:
        out.append('<h2>一、文本层分析</h2>')
        if s.get("theme"):
            out.append(f'<p><b>主题：</b>{esc(s["theme"])}</p>')
        if s.get("flow"):
            out.append(f'<div class="flow">🧭 <b>对象流动链：</b>{esc(s["flow"])}</div>')
        if s.get("backbone"):
            out.append(f'<p><b>主干/枝干：</b>{esc(s["backbone"])}</p>')
        if s.get("level_map"):
            out.append(f'<p><b>信息层级：</b>{esc(s["level_map"])}</p>')
        if s.get("register"):
            out.append(f'<p><b>语域/文体：</b>{esc(s["register"])}</p>')
    # 段落层（**5 件套**：英文原文 / 中文译文 / 段旨 badge / 段意概括 / 段间关系）
    # 契约容忍多种写法——三个零记忆冷启动实测里，agent 各自发明了不同结构
    # （塞进 functions 字符串 / 加 paragraph_notes / 直接自拼 HTML），故这里统一归一化。
    para_blocks = _paragraph_blocks(data)
    if para_blocks:
        out.append('<h2>二、原文结构与功能</h2>')
        for bi, blk in enumerate(para_blocks, 1):
            if not blk.get("function"):
                missing_func.append(bi)
            out.append(_para_html(blk))
    # 逐题
    qs = data.get("questions", [])
    if qs:
        out.append(f'<h2>三、逐题分析（{len(qs)} 题）</h2>')
        for i, q in enumerate(qs):
            out.append(f'<div class="q"><div class="qn">第 {i+1} 题</div>')
            out.append(f'<p>{esc(q.get("q",""))}</p>')
            out.append(f'<span class="ans">答案：{esc(q.get("answer",""))}</span>')
            out.append(f'<div class="why">💡 {esc(q.get("why",""))}</div>')
            cards = [c.get("id","") if isinstance(c, dict) else c for c in q.get("cards", [])]
            uses = {u.get("id",""): u.get("use","") for u in q.get("card_uses", []) if isinstance(u, dict)}
            if cards:
                out.append('<div class="cards">📌 依据卡（点开看内容）：</div>')
                for ci, cid in enumerate(cards):
                    uid = f'q{i}-{ci}'
                    use = uses.get(cid, "")
                    cname = ""
                    f = resolve_card(cid)
                    if f:
                        ct = cname or _card_title(f)
                        label_txt = f'{cid} {ct}' if ct else cid
                        body = md_to_html(strip_source(f.read_text(encoding='utf-8')))
                        if use:
                            out.append(f'<details class="cnote"><summary>📌 {esc(label_txt)}</summary><div class="cnote-body">'
                                       f'<input class="tabr ca" type="radio" name="{uid}" id="{uid}a" checked>'
                                       f'<label class="tablabel la" for="{uid}a">🎯 本题运用</label>'
                                       f'<input class="tabr cb" type="radio" name="{uid}" id="{uid}b">'
                                       f'<label class="tablabel lb" for="{uid}b">📖 知识原理</label>'
                                       f'<div class="pane pane-a">{esc(use)}</div>'
                                       f'<div class="pane pane-b">{body}</div>'
                                       f'</div></details>')
                        else:
                            out.append(f'<details class="cnote"><summary>📌 {esc(label_txt)}</summary><div class="cnote-body">{body}</div></details>')
                    else:
                        out.append(f'<div class="cnote" style="padding:8px 14px">📌 {esc(cid)}（未找到卡文件）</div>')
            apq = q.get("anti_patterns") or []
            if apq:
                out.append(aps.hint(apq, AP_INDEX))
            for w in q.get("wrong_options", []):
                out.append(f'<div class="wrong">✗ {esc(w.get("opt",""))} — {esc(w.get("reason",""))}</div>')
            # 缺口栏 + 可迁移原则（**逐题必填**，第十一轮 L3-1）
            #
            # 为什么在这里：SKILL.md 写着「▮缺口栏 + 🎯可迁移原则（逐题必填）」，
            #   且明说「缺口栏是最值钱的产出」——但这条原先**只做在案例脚本里**，
            #   通用交付管线压根不承载 → 走通用管线的交付，缺口只能折进 why，机器不可校验。
            #   这是**同一个洞的第二次**（上一次是反模式层只做在案例脚本里，第六轮冷启动抓到）。
            # 取值顺序照「两种读者」原则：agent 写的中文键也认。
            gap = (q.get("gap") or q.get("缺口") or "").strip()
            transfer = (q.get("transfer") or q.get("可迁移原则") or q.get("transferable") or "").strip()
            if gap or transfer:
                # 缺口「无则写 无」是规范用词，空值渲染成「无」而不是空行
                out.append(f'<div class="gap">▮缺口：{esc(gap or "无")}</div>')
                if transfer:
                    out.append(f'<div class="note">🎯 可迁移原则：{esc(transfer)}</div>')
            else:
                missing_gap.append(i + 1)
            out.append('</div>')
    # 反模式层（**条件触发**：不命中则不输出，普通解析不多一个元素）
    ap_ids, ap_notes, ap_src = aps.resolve(data, AP_INDEX)
    ap_html = aps.layer(ap_ids, AP_INDEX, ap_notes, source=ap_src)
    if ap_html:
        # ⚠️ 必须带自己的标题 + 编号（第十二轮 L4 实测发现）：
        #   复盘编号在反模式层出现时会顺延到「五」（第八轮定），这本身对；
        #   但当时**只让了编号、没给这一层加标题** → 学生看到的是「一、二、三、五」，**跳号**。
        #   L4 实测（零记忆 agent 真做一套题）当场撞见：页面里找不到「四」。
        #   修法：层自带标题，编号链条完整。
        out.append('<h2>四、反模式层：这次暴露的问题</h2>')
        out.append(ap_html)
    # 复盘（编号随反模式层是否出现而顺延）
    r = data.get("review", {})
    if r:
        out.append('<h2>%s、复盘</h2>' % ('五' if ap_html else '四'))
        if r.get("error_pattern"):
            # 复盘前缀随**场景**变化（第十一轮 L3-2）——与反模式条幅同一套做法：
            #   声明了就用声明的标签；未声明用**中性文案**，脚本不替使用者假定「这是错题」。
            # 由来：L3 反例输入没有错题，输出里却写死「**错题归因**：」——前缀声称有错题，
            #   而本次没有。这与第六轮修过的「条幅误归因」是同一类病（硬编码文案 + 场景会变），
            #   **当时只修了条幅那一处，复盘前缀漏了**。
            label = REVIEW_LABELS.get((r.get("kind") or r.get("scenario") or "").strip(),
                                      REVIEW_LABELS["__neutral__"])
            out.append(f'<p><b>{label}</b>{esc(r["error_pattern"])}</p>')
        if r.get("takeaway"):
            out.append('<div class="take">🎯 <b>可迁移原则：</b><br>' + esc(r["takeaway"]).replace('\n', '<br>') + '</div>')
    # 追问提示条（每次交付必带）
    out.append('<div style="margin-top:28px;background:#f0f4ff;border:1px solid #d0e2ff;border-radius:10px;padding:12px 16px;font-size:13px;color:#1f2328">💬 <b>看不懂的尽管问。</b>以上任何术语、原理、判断依据，都可以拿去追问 AI——比如"这段怎么概括出来的""这个干扰项怎么构造的"。不懂就问，问到底都行。</div>')
    # 评分提示（2026-09-02：每次交付必带，放最后）
    out.append('<div style="margin-top:12px;background:#fff8e6;border:1px solid #f0dfa8;border-radius:10px;padding:12px 16px;font-size:13px;color:#1f2328">⭐ <b>给这次解析打个分。</b>一共 5 颗星，你觉得值几颗？直接回复 AI「X 星」就行——不满意的地方也欢迎说，说了才能改。</div>')
    out.append('</body></html>')
    if missing_gap:
        # 不静默：规范说这两项逐题必填，缺了要让**跑管线的人**看见
        # （但不往学生看的页面上塞占位符——交付物保持干净，合规性由门禁与告警守）
        print('[warn] 第 %s 题未提供「缺口 / 可迁移原则」——规范为逐题必填，'
              '请补 questions[].gap 与 questions[].transfer' % missing_gap, file=sys.stderr)
    if missing_func:
        # 第十二轮 P4：与上面那条**口径对齐**——「必填项缺字段」两类都要吭声。
        # 原先只有 gap 会告警，段旨缺了静默丢（写法 C 少给 function → 4/5，无一字提示）。
        print('[warn] 第 %s 段未提供「段旨（function）」——规范为该字段必填，'
              '请补 paragraph_notes[].function（或 functions[].段旨）' % missing_func, file=sys.stderr)
    return '\n'.join(out)

def main():
    if len(sys.argv) < 2:
        print('用法: python analysis_to_html.py <分析结果.json> [-o 输出.html]')
        return 1
    src = pathlib.Path(sys.argv[1])
    data = json.loads(src.read_text(encoding='utf-8'))
    out = BASE / '..' / 'dist' / (src.stem + '.html')
    if '-o' in sys.argv:
        out = pathlib.Path(sys.argv[sys.argv.index('-o') + 1])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(data), encoding='utf-8')
    print(f'[OK] 已生成: {out} ({out.stat().st_size/1024:.1f} KB)')
    return 0

if __name__ == '__main__':
    sys.exit(main())
