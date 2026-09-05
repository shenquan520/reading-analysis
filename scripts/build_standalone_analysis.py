# -*- coding: utf-8 -*-
import io, re

BASE = r"E:/阅读分析/github-export/references/cards"

def md2html(md):
    out, lines = [], md.split("\n")
    i = 0
    while i < len(lines):
        ln = lines[i]
        s = ln.strip()
        if not s:
            i += 1; continue
        if s.startswith("```"):
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                out.append('<div class="k-code">%s</div>' % esc(lines[i])); i += 1
            i += 1; continue
        if s == "---":
            out.append("<hr>"); i += 1; continue
        m = re.match(r"^(#{1,4})\s+(.*)$", s)
        if m:
            lv = len(m.group(1)); cls = "k-h%d" % min(lv + 1, 4)
            out.append('<div class="%s">%s</div>' % (cls, inline(m.group(2)))); i += 1; continue
        if s.startswith(">"):
            buf = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip().lstrip(">").strip()); i += 1
            out.append('<div class="k-quote">%s</div>' % inline(" ".join(buf))); continue
        if s.startswith("|"):
            buf = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                row = lines[i].strip().strip("|")
                cells = [c.strip() for c in row.split("|")]
                if not all(re.match(r"^:?-+:?$", c) for c in cells if c):
                    buf.append(" ｜ ".join(c for c in cells if c))
                i += 1
            out.append('<div class="k-tbl">%s</div>' % "<br>".join(inline(b) for b in buf)); continue
        if re.match(r"^([-*•]|\d+\.)\s+", s):
            buf = []
            while i < len(lines) and re.match(r"^([-*•]|\d+\.)\s+", lines[i].strip()):
                buf.append(lines[i].strip()); i += 1
            out.append('<div class="k-li">%s</div>' % "<br>".join(inline(b) for b in buf)); continue
        buf = []
        while i < len(lines) and lines[i].strip() and not lines[i].strip().startswith(("#", ">", "|", "-", "```")) and not lines[i].strip() == "---":
            buf.append(lines[i].strip()); i += 1
        out.append('<p class="k-p">%s</p>' % inline(" ".join(buf)))
    return "\n".join(out)

def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def inline(t):
    t = esc(t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"`([^`]+)`", r'<code>\1</code>', t)
    return t

def card_html(path):
    return md2html(io.open(path, encoding="utf-8").read())

CARDS = {
 "B034": BASE + "/B-skills/034-macro-structure.md",
 "B042": BASE + "/B-skills/042-research-conclusion-first.md",
 "A003": BASE + "/A-analysis/003-information-level.md",
 "B083": BASE + "/B-skills/083-option-position-judgment.md",
 "B016": BASE + "/B-skills/016-sentence-functions.md",
 "B037": BASE + "/B-skills/037-phrase-in-context-triple-check.md",
 "B011": BASE + "/B-skills/011-reiteration.md",
 "A024": BASE + "/A-analysis/024-semantic-five-dimensions.md",
 "B036": BASE + "/B-skills/036-last-paragraph-mainidea.md",
 "B048": BASE + "/B-skills/048-topic-sentence.md",
}

def sticky(idx, title, use):
    cid = "n%d" % idx
    name = title.split(" ")[0]
    return ('<details class="cnote"><summary>📌 %s</summary><div class="cnote-body">'
            '<input class="tabr ca" type="radio" name="%s" id="%sa" checked>'
            '<label class="tablabel" for="%sa">🎯 本题运用</label>'
            '<input class="tabr cb" type="radio" name="%s" id="%sb">'
            '<label class="tablabel" for="%sb">📖 知识原理（原卡全文）</label>'
            '<div class="pane pane-a">%s</div>'
            '<div class="pane pane-b k-md">%s</div></div></details>'
            ) % (esc(title), cid, cid, cid, cid, cid, cid, inline(use), card_html(CARDS[name]))

# ===== 便签定义 =====
S = []
S.append(("B034 宏观结构：问题解决四段", "本篇是标准的「问题解决型」四段落地：P1 情景（植物竞争现象＋研究空白）→ P2 问题/方法（怎么验证化学探测）→ P3/P4 解决（双向实验结果）→ P5 评估（结论＋农业应用）。认出骨架后，35 题主旨直接去「评估段」收结论，32 题装置作用去「方法段」找依据——细节自动归位。"))
S.append(("B042 研究结论优先法", "本篇结论句在 P5「can chemically detect their competitors, and adjust their own growing strategies accordingly」——动手做题前先把它抓在手里：四道题全部变成「验证题」。33 题猜词、34 题细节，都对答案方向做了一次「回结论校验」，防止定位对了、理解歪了。"))
S.append(("A003 信息层级", "P3/P4 两段在层级图上是同层并列、方向相反（慢株加速↔快株减速），它们共同支撑的上层是 P5 结论句。35 题干扰项 A 只罩「防御」一端——层级上够不到主旨层，这就是「以偏概全」的结构成因。"))
S.append(("B083 干扰项位置判别（十类 + 三位置判定法）", "Q32 四个选项踩了两类的坑：B「防虫」把 VOCs 信号的效果安到通道头上＝类1 因果链位置错（下游效果冒充装置功能）；D 与实验事实相反（遮阴已被排除）；A 无中生有。三位置判定法：通道站在「方法位」，凡说成「结果位」的选项位置错即错。Q34 又用了它的方向类与程度偷换；Q35 用了类5 范围缩小（A 只取防御一端冒充主旨）。"))
S.append(("B016 句子功能清单（装置句＝方法位）", "「The only connection...was through one-way air channels」这句在段落里的功能是陈述实验方法——方法句回答「怎么保证实验干净」，不回答「实验发现了什么」。B「防虫」实际是 P1 现象层的功能（VOCs 信号防虫），把现象层功能安到方法句头上，就是功能错位。"))
S.append(("B042 研究结论优先法（回结论校验）", "选完 C 回结论校验一遍：结论说植物「探测邻居并调整生长策略」——装置的作用必须服务于这个实验目的，「调节实验条件」让探测可测，方向吻合；若选 B「防虫」，结论里的「调整生长策略」就没了实验依据。结论在手，选项方向立刻可验。"))
S.append(("B037 画线词/短语猜测三查 + 态度极性", "俚语题永远不按字面猜——「shift」字面是移动，答案却是加速。正确姿势：放弃词义，改收语境证据——条件句给出后果（不加速就淘汰），前文给出实际行为（长快了 20%），两条证据线夹逼出「加速」。D「watch out」的迷惑性在于只涵盖「意识到风险」半截，漏了行动。"))
S.append(("B011 词汇复现", "「get a shift on」的证据链就是一条复现链：grew more quickly → 20% more biomass → speed up——同一个语义（加速）在段内三次复现（原词、数据、选项同义改写）。圈出空位前后的实词，顺复现链走，答案自己浮出来。注意复现是线索不是证据：最终确认仍靠条件句逻辑。Q34 的正确项 A 也是替换链：defensive measures → self-protection。"))
S.append(("A024 语义分析多维（程度维）", "Q33：D「watch out」败在动作维——原文的动作是「改变生长方式」（有行动），watch out 只有「警觉」（无行动）。Q34：把原文「cut their growth rates notably」按维度拆——主体＝快株，动作＝降低，对象＝生长速度，程度＝notably（显著但不归零）；选项 B 的 stop 在程度维上是「归零」，程度维对不上即错。原文句和选项句各拆一遍维度表，哪维对不上，哪维就是命题人动手脚的地方。"))
S.append(("B036 末段主旨验（主旨回收站）", "P5 是收束段：in other words 引出的总结句在回收全文主题。「detect competitors and adjust strategies」——正确项 C 是这句的同义改写，且覆盖面罩住 P3/P4 双向结果。A 只罩防御一端，B 答非所问，D 无中生有——三个干扰项概括度都不够主旨级。"))
S.append(("B048 主题句与段落主旨（串联法验主旨）", "串联法反向验证：P1「植物间存在竞争信号」→ P2「实验隔离变量」→ P3/P4「双向调整」→ P5「化学探测＋策略调整」——串起来正是 C「plants keep spying on the competition」。B「为什么生长速率不同」串不起来：速率差异是现象不是线索主线，说明 B 不是主旨。"))

stick_html = {}
names = [t for t, _ in S]
for i, (title, use) in enumerate(S):
    stick_html[title.split(" ")[0]] = sticky(i, title, use)

# ===== 段落原文 + 译文 + 段旨 + 概括 =====
PARAS = [
("P1", "背景 + 研究空白 + 提出实验",
 "植物学家早已知道植物能通过名为挥发性有机化合物（VOCs）的化学物质进行交流。当植物遭受虫害时，它们释放的 VOCs 成分会发生变化。此前的研究表明，这会驱使附近的植物提升自身防御，以备自己随后遭到攻击。但尚未被探索的问题是：健康的植物是否也会探测邻居释放的 VOCs。于是生态学家 Velemir Ninkovic 决定做一个实验。",
 "植物间已知有 VOCs「报警」交流，但健康植株是否也互相探测 VOCs 仍是空白——生态学家 Ninkovic 决定实验验证。"),
("P2", "实验设计（方法位）",
 "Ninkovic 博士和同事种植了三种生长速度不同的大麦——一种快、一种慢、一种中等。植株被放进彼此相邻的种植容器中，但没有任何遮蔽邻居的途径。植株之间唯一的连接，是连通种植容器的单向空气通道。研究人员借此把空气从一个容器吹向下一个，并在 25 天里监测其对植株的影响。",
 "三种速率的大麦相邻而植，唯一联系是单向空气通道——排除遮阴等干扰，只留「空气」这一个可控变量。"),
("P3", "结果①：慢株加速（避遮阴）",
 "结果相当惊人。慢生长大麦暴露在快生长邻居容器的空气中时长得更快，比放在慢生长植株旁边时多产出 20% 的生物量。Ninkovic 博士认为，这是因为慢生长植株探测到了邻居释放的化合物，并意识到——至少在野外——如果不赶紧加速生长，它们将有被遮蔽淘汰的风险。",
 "慢生长大麦闻到快生长邻居的空气后加速生长（生物量 +20%），机制：不加速就会被遮蔽淘汰。"),
("P4", "结果②：快株反向（减速增防）",
 "快生长植株暴露在慢生长邻居容器的空气中时，反应正好相反。由于不必那么急着争夺阳光，它们显著降低了生长速度。当慢生长组把资源转向生长时，快生长组得以把更多资源花在耗费资源的防御措施上。",
 "快生长大麦闻到慢生长邻居的空气后反而减速生长，把省下的资源转投防御措施——与 P3 构成反向对照。"),
("P5", "结论 + 农业应用",
 "换句话说，大麦能够通过化学方式探测自己的竞争者，并相应调整自身的生长策略。农民已经在试验用 VOCs 提高产量。Ninkovic 博士的结果表明，VOCs 可以在预期虫害来临时刺激防御性化合物的产生，或在风险较低时加速生长。",
 "大麦能化学探测竞争者并调整生长策略；这一发现有望用 VOCs 调控农作物的防御与生长。"),
]

EN = {
"P1": "Botanists have known that plants can communicate via chemicals known as volatile organic compounds (VOCs). When plants are attacked by pests, the composition of the VOCs they release changes. Previous work has shown that this drives nearby plants to raise their own defences in anticipation of being attacked in turn. What has gone unexplored is whether plants detect VOCs released by their neighbours when they are healthy. So ecologist Velemir Ninkovic decided to run an experiment.",
"P2": "Dr. Ninkovic and his colleagues planted three varieties of barley that grow at different rates — one quick, one slow, and one middling. The plants were put in growing containers next to one another, but with no way for them to shade their neighbours. The only connection that the plants had to one another was through one-way air channels that connected their growing containers. These allowed the researchers to blow air from one container to the next, and to monitor the effect that this had on the plants over 25 days.",
"P3": "The results were striking. The slow-growing barley grew more quickly when it was exposed to air from the containers of its fast-growing cousins, producing 20% more biomass than when it was placed next to slower-growing plants. This, Dr. Ninkovic believes, is because the slow-growing plants were detecting the compounds released by their neighbours and realising that, in the wild at least, they would be at risk of getting shaded out if they did not get a shift on.",
"P4": "Fast-growing plants exposed to air from the containers of their slow-growing cousins reacted in the opposite way. With less need to race for the sun, they cut their growth rates notably. While the slow growers were switching resources towards growth, the speedsters were able to spend more of theirs on resource-intensive defensive measures.",
"P5": "Barley, in other words, can chemically detect their competitors, and adjust their own growing strategies accordingly. Farmers are already experimenting with using VOCs to boost productivity. Dr. Ninkovic's results suggest VOCs could be used to stimulate protective compounds when pests are expected, or to accelerate growth when risk is low.",
}

para_html = []
for pid, badge, zh, summ in PARAS:
    para_html.append(('<div class="para"><div class="pbadge">📌 段%s · %s</div>'
        '<p class="en">%s</p><p class="zh">【译】%s</p>'
        '<p class="summ"><b>段意概括：</b>%s</p></div>')
        % (pid[1], esc(badge), esc(EN[pid]), esc(zh), esc(summ)))

# ===== 题目区 =====
def qblock(no, tagtype, qtext, ans, loc, reas, excl, cards, gap, transfer):
    cards_html = "".join(stick_html[c] for c in cards)
    return ('<div class="q"><span class="tag">%s %s</span><p><b>%s</b></p><p class="ans">✓ %s</p>'
        '<p><b>定位</b>：%s</p><p><b>推理</b>：%s</p><p><b>排除</b>：%s</p>'
        '<div class="cards">📌 依据卡 ×%d（点开看原卡全文）：）</div>'.replace('））', '）')
        % (no, esc(tagtype), esc(qtext), esc(ans), esc(loc), esc(reas), esc(excl), len(cards))
        + cards_html
        + '<div class="gap">▮缺口：%s</div><div class="note">🎯 可迁移原则：%s</div></div>'
        % (esc(gap), esc(transfer)))

Q32 = qblock("32", "细节题 · 实验装置作用",
 "32. What role did the one-way air channels play in the experiment?",
 "C. They regulated experiment conditions.",
 "P2「The only connection ... one-way air channels ... allowed the researchers to blow air from one container to the next」——抓 only（唯一连接）与 allowed the researchers（主动操控）。",
 "实验要验证「植物能探测 VOCs」，最大威胁是其他变量干扰。通道的设计意图＝人为制造唯一可控变量——只让空气通过，其他全切断，这正是「控制实验条件」。",
 "A 共享养分——通道传的是空气，无中生有；B 防虫——防虫是 VOCs 信号的作用不是通道的作用，因果链位置错；D 防遮阴——原文明确 no way to shade，遮阴已被排除。",
 ["B083", "B016", "B042"],
 "「实验装置作用题」没有专门卡——装置/方法目的类判定规则散在 B083/B016 里，值得独立成卡。",
 "一切「为什么这样设计」的题目，答案都往「控制变量 / 排除干扰」上靠。")

Q33 = qblock("33", "词义推断题",
 '33. What does "get a shift on" mean?',
 "B. Speed up.",
 "P3「...realising that ... they would be at risk of getting shaded out if they did not get a shift on」。",
 "三查＋极性——①条件句：不 get a shift on 就会被遮阴淘汰 → 反之这个动作就是避免淘汰；②前文证据：慢株实际「grew more quickly」「20% more biomass」；③态度极性：中性。三线合一＝赶紧加速。",
 "A 共享养分——无中生有；C 移开——大麦不能移动，常识＋原文双杀；D 小心——只停在「意识到危险」，漏掉后文实际的生长反应，程度不足。",
 ["B037", "B011", "A024"],
 "无（B037 三查＋B011 复现链＋A024 维度表三重覆盖）。",
 "习语题＝语境线索题换皮；选项里「只反应、无行动」的通常是干扰。")

Q34 = qblock("34", "细节题",
 "34. What happened to the fast-growing barley when exposed to air from its rivals?",
 "A. They invested more in self-protection.",
 "P4「...they cut their growth rates notably ... the speedsters were able to spend more of theirs on resource-intensive defensive measures」。",
 "慢株把资源切给「生长」，快株不用抢阳光，把资源花在「defensive measures（防御措施）」——spend more on defence＝invested more in self-protection，同义替换一步到位。",
 "B 停止生长——原文 cut growth rates（减速）不是 stop，程度偷换；C 长更快——那是慢株，张冠李戴；D 释放更多 VOCs——无中生有。",
 ["B083", "A024", "B011"],
 "无（B083 程度/方向类＋A024 程度维＋B011 替换链三重覆盖）。",
 "细节题选项里的极端词（stop / all / never）九成是程度偷换，回原文找原幅度词对表。")

Q35 = qblock("35", "主旨题",
 "35. What is the text mainly about?",
 "C. How plants keep spying on the competition.",
 "P5 总结句「Barley, in other words, can chemically detect their competitors, and adjust their own growing strategies accordingly」——「in other words」是作者亲口标记「以下是全文压缩」。",
 "主旨＝作者结论。detect competitors＝spying on the competition 的学术版与通俗版；C 覆盖 P3/P4 双向结果和 P5 应用——覆盖面最大。",
 "A 只覆盖防御一端，以偏概全；B 问错问题——文章不讲速率差异的原因，讲如何据此调整；D 不同地点种植——无中生有。",
 ["B036", "B048", "B083"],
 "无（B036 末段回收＋B048 串联法＋B083 范围类三重覆盖）。",
 "主旨题正确项＝「同义替换＋覆盖面最大」双条件；单段细节冒充主旨是最高频陷阱。")

CSS = """
body{font-family:system-ui,sans-serif;max-width:760px;margin:0 auto;padding:16px;line-height:1.75;color:#1a1a1a;background:#faf7f2}
h1{font-size:22px}h2{font-size:18px;border-left:4px solid #f97316;padding-left:8px;margin-top:30px}
.q{background:#fff;border-radius:10px;padding:14px 18px;margin:14px 0;box-shadow:0 2px 10px rgba(249,115,22,.08)}
.tag{background:#f97316;color:#fff;border-radius:6px;padding:2px 8px;font-size:13px}
.ans{color:#c2410c;font-weight:bold}
.en{font-style:italic;color:#374151;background:#f3f4f6;border-radius:6px;padding:6px 10px;display:block;margin:6px 0}
.zh{background:#ecfdf5;border-radius:6px;padding:8px 12px;margin:8px 0;font-size:14.5px}
.para{background:#fff;border-radius:10px;padding:12px 16px;margin:12px 0;box-shadow:0 2px 10px rgba(16,185,129,.07)}
.pbadge{display:inline-block;background:#10b981;color:#fff;border-radius:6px;padding:2px 10px;font-size:13px;margin-bottom:6px}
.summ{background:#fde7d2;border-radius:8px;padding:8px 12px;margin-top:8px;font-size:14px}
.flow{background:#fff;border-radius:10px;padding:12px 18px;margin:10px 0;box-shadow:0 2px 10px rgba(249,115,22,.07);font-size:14.5px}
.flow b{color:#c2410c}
.note{background:#fde7d2;border-radius:8px;padding:10px 14px;margin-top:10px;font-size:14px}
.gap{background:#1a1a1a;color:#e5e7eb;border-radius:8px;padding:8px 14px;margin-top:8px;font-size:14px}
.sec{border-top:1px dashed #d1a37a;margin-top:20px;padding-top:8px;font-size:13px;color:#9ca3af}
.cards{font-size:12px;color:#57606a}
.tabr{display:none}
.tablabel{cursor:pointer;display:inline-block;padding:4px 14px;border-radius:14px;background:#eef1f4;color:#57606a;font-size:12.5px;margin:10px 8px 0 0;user-select:none}
.pane{display:none;padding:10px 2px 0}
input.ca:checked ~ .pane-a,input.cb:checked ~ .pane-b{display:block}
.cnote{background:linear-gradient(#fffbe6,#fff7cc);border:1px solid #e8d98a;border-radius:4px;box-shadow:2px 3px 8px rgba(0,0,0,.10);margin:10px 0;transform:rotate(-.4deg);position:relative;font-size:12.5px}
.cnote::before{content:"";position:absolute;top:-9px;left:50%;width:70px;height:18px;margin-left:-35px;background:rgba(255,230,120,.75);border:1px solid rgba(200,170,60,.35);transform:rotate(-2deg)}
.cnote>summary{cursor:pointer;list-style:none;padding:10px 14px;font-weight:700;color:#7a5c00;user-select:none}
.cnote>summary::-webkit-details-marker{display:none}
.cnote>summary::after{content:"▸ 点开看卡";float:right;color:#b08d00;font-weight:400;font-size:11.5px}
.cnote[open]>summary::after{content:"▾ 收起"}
.cnote .cnote-body{padding:0 14px 12px;color:#4a3f00;line-height:1.7}
.k-md{max-height:460px;overflow-y:auto;font-size:12px;line-height:1.65}
.k-md .k-h2{font-weight:bold;font-size:13.5px;margin:10px 0 4px;color:#6b3a00;border-bottom:1px solid #e8d98a;padding-bottom:2px}
.k-md .k-h3{font-weight:bold;font-size:12.5px;margin:8px 0 3px;color:#7a5c00}
.k-md .k-h4,.k-md .k-h5{font-weight:bold;font-size:12px;margin:6px 0 2px;color:#7a5c00}
.k-md .k-quote{border-left:3px solid #e0c95e;background:#fffdf0;padding:5px 8px;margin:5px 0;border-radius:0 4px 4px 0}
.k-md .k-tbl{background:#fffdf0;border:1px dashed #d9c76a;border-radius:4px;padding:5px 8px;margin:5px 0;font-size:11.5px}
.k-md .k-li{margin:4px 0}
.k-md .k-p{margin:4px 0}
.k-md code{background:#f3ecd2;border-radius:3px;padding:0 3px;font-size:11px}
.k-md hr{border:none;border-top:1px dashed #d9c76a}
.k-md b{color:#5b4a00}
"""

HTML = """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>巴蜀中学月考 D 篇（大麦化学哨兵）· 开源版重跑解析</title><style>%s</style></head><body>
<h1>巴蜀中学月考 D 篇（大麦化学哨兵）· 开源版重跑解析</h1>
<p class="ans">答案：32-C / 33-B / 34-A / 35-C</p>
<p>开源版 skill 全流程：检索卡片库 → 全文层分析（语义流动/主干分支/信息层级）→ 逐段翻译+段旨+概括 → 逐题「定位→推理→排除」→ 便利贴挂卡（每题 3 张，📖页签=原卡全文嵌入）。</p>

<h2>一、全文层分析</h2>
<div class="flow"><b>语义流动链：</b>已知背景（植物靠 VOCs「报警」交流）→ 研究空白（健康植株也互相探测吗？）→ 实验设计（单向空气通道＝唯一可控变量）→ 结果①慢株加速（避遮阴）→ 结果②快株减速增防（反向对照）→ 结论（化学探测+策略调整）→ 农业应用（VOCs 调控）</div>
<div class="flow"><b>主干 / 枝干：</b>主干＝大麦能通过 VOCs 化学探测竞争者并<b>双向调整</b>生长策略；枝干＝三种速率品种、25 天监测、20%% 生物量、resource-intensive 防御措施等细节。</div>
<div class="flow"><b>信息层级：</b>P1 现象+空白（层1 起）→ P2 方法（层2 分）→ P3/P4 双向结果（层2 分，同层并列、方向相反）→ P5 结论（层1 收，权重最高＝主旨）。层级≠权重：P1 也在层1 但只是引子，权重落在 P5 结论句。</div>
<div class="flow"><b>语域 / 文体：</b>研究类说明文（现象—方法—结果—结论—应用），学术报道语域；B042 结论优先法全文适用。</div>
%s

<h2>二、原文结构与功能（原文 · 译文 · 段旨 · 概括）</h2>
%s

<h2>三、逐题解析（每题 3 卡，📖页签=原卡全文）</h2>
%s%s%s%s

<h2>词汇缺口记录</h2>
<p>volatile organic compounds (VOCs) 挥发性有机化合物｜anticipate 预料｜biomass 生物量｜get a shift on 赶紧加速（英式口语）｜speedsters 快跑者｜resource-intensive 资源密集型的</p>

<div class="sec">知识库：开源版卡片库（B85/A36/R5）｜挂卡 14 张：结构层 B034/B042/A003 ＋ Q32 B083/B016/B042 ＋ Q33 B037/B011/A024 ＋ Q34 B083/A024/B011 ＋ Q35 B036/B048/B083（B042/B083 跨处复用合并）｜📖页签=原卡 markdown 全文直读转换｜本篇缺口：实验装置作用题判定规则待立卡</div>

<div class="note">⭐ 给这次解析打个分。一共 5 颗星，你觉得值几颗？直接回复「X 星」就行——不满意的地方也欢迎说，说了才能改。</div>
<div class="note">💬 以上分析有任何不懂的地方——术语、原理、某个判断的依据——尽管问，问到底都行。想知道某段怎么概括出来的、干扰项怎么构造的，直接问。</div>
</body></html>""" % (CSS, "".join(stick_html[c] for c in ["B034", "B042", "A003"]), "".join(para_html), Q32, Q33, Q34, Q35)

out = r"C:/Users/ASUS/Desktop/巴蜀D篇解析/开源版重跑-巴蜀D篇.html"
io.open(out, "w", encoding="utf-8", newline="").write(HTML)
print("written:", len(HTML), "chars")
