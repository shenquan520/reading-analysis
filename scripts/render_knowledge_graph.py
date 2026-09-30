# -*- coding: utf-8 -*-
"""
知识网络渲染器（KNOWLEDGE-GRAPH-PLAN.md 落地）
- 资料层不动：references/cards/ 各卡照旧
- 呈现层：dist/knowledge-graph.html —— 点一个知识点，聚合出它在各板块的关联内容
- 映射数据：references/KNOWLEDGE-GRAPH.md（同步生成，供审校）
- 渐进增强：术语用 <details>，无 JS 也能全部展开阅读
用法：python scripts/render_knowledge_graph.py
"""
import io, sys, os, re, html

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARD = os.path.join(ROOT, 'references', 'cards')
OUT_HTML = os.path.join(ROOT, 'dist', 'knowledge-graph.html')
OUT_MD = os.path.join(ROOT, 'references', 'KNOWLEDGE-GRAPH.md')

# ---------- 知识点映射数据（提案后经审校；区块数量由知识库实际关联决定） ----------
# 术语三元组：(术语, 定义一句话, 实例一个, 出处卡号)
KP = [
 dict(id='binglie', name='并列', terms=[
   ('概括关联', '维度', '概括并列的钥匙——找到并列各项共同的上位概念，维度找到了，概括句就有了','「他学习成绩非常好，品质也极好」→ 上位维度：他很好（学习、品质）','B001'),
   ('概括关联', '累加法', '无主次的并列：各项内容相加，用并列短语把复句压成单句','朱自清《春》三句分写春的三个特点 → 「赞美春天新、美、力」','B021①'),
   ('概括关联', '对比反衬抓正面', '正反对举的并列：侧重在正面，抓正面即可概括','「不是不能做，而是不想做」→ 抓「不想做」','B021①'),
 ]),
 dict(id='zhuanzhe', name='转折', terms=[
   ('本体·深挖', '拐角', '转折的定义是语义方向拐角——「重心在后」只是常见效果，不是定义','「北京人爱瞧热闹，但是不爱管闲事」→ 方向在「不爱管闲事」拐','B019'),
   ('概括关联', '反转陷阱', '转折后的否定词/程度词是重心一部分，丢了意思完全反转','「生活并没有什么改变」概括成「生活有了改变」= 反向错','B021三点六'),
   ('论证关联', '让步-反驳形状', '作者摆反方：先详述对方理由再两层驳——让步≠立场，转折词后才是','although 详述对方观点后 but 引出的才是作者立场','B053'),
 ]),
 dict(id='yinguo', name='因果', terms=[
   ('概括关联', '因果看探寻方向', '一般（现象引起现象）重在果、舍因留果；但由浅入深探本质时原因是对本质的阐述、反而是主要的——权重由主旨定，具体分析（经纠错修订）','草枯萎→踩着柔软（看果）；艾青「我对这土地爱得深沉」是本质原因（看因）','B021③'),
   ('概括关联', '转因为果', '议论文里表层写因、深层是果：论据是「因」，论点是「果」——丢论据留论点（此为一般情况，权重仍回主旨）','全文用数据论证「早起有益」→ 主旨是「早起有益」不是数据本身','B021③'),
   ('论证关联', '相关≠因果', '「A 与 B 相关」推不出「A 导致 B」——巧合/方向反转/第三变量/多因复杂','研究说"喝咖啡的人心脏好"≠咖啡让心脏好（可能健康的人本爱喝）','B051'),
 ]),
 dict(id='dijin', name='递进', terms=[
   ('概括关联', '一般递进', '前后都肯定、无主次——概括时可用句子压缩法变递进为并列','「坐满了人，而且连通道上都站满了人」→ 「观众席和通道上都是人」','B021④'),
   ('概括关联', '衬托递进', '前分句否定、是后分句的衬托——有主次，保主舍次丢衬托','「大人尚且受不了，何况小孩子？」→ 「这么热的天，小孩受不了」','B021④'),
 ]),
 dict(id='zongfen', name='总分', terms=[
   ('概括关联', '摘总说', '总分概括最轻松——找到总说/总结句就找到概括句','段首总起句或段尾总结句直接摘录','B021⑤'),
   ('概括关联', '覆盖度原理', '总说不一定覆盖全部分说——「对不上很正常」（批注）','总说只覆盖两个分说项时，第三个分说要另行概括再综合进去','B021三点五'),
 ]),
 dict(id='cihui', name='词汇衔接', terms=[
   ('本体·深挖', '反义并列≠等权', '生与死、上与下：词义上对等对称=并列；但文中地位可不对称——聊A彻底必须聊对立面B，突出的却可能是A（衬托逻辑），权重回主旨','反义对照段主旨题答案落在被衬托的一方','B011'),
   ('题型关联', '词汇复现', '正确选项与前后文有词汇呼应：原词/同义/近义/上义/概括词','文中 organ→body parts 的上下义呼应就是定位线索','B011'),
   ('本体·深挖', '搭配共现', '搭配是看不见的衔接——两个词习惯性共现，拆开就假','laugh…joke / candle…cake 这类固定共现','B012'),
   ('题型关联', '反义三类型', '相反（有程度）/互补（非此即彼）/关系对立（相互依存）——not old ≠ young','推断题里 not old 只推出 not young 不成立，可能是 middle-aged','B072'),
 ]),
 dict(id='zhicheng', name='指称与指代', terms=[
   ('题型关联', '指代消歧', 'it/this/that/the 靠参照他物解释——做题往前后找它指的东西','this 出现时，它的内容通常在前一句','B013'),
   ('本体·深挖', '语义优先', '代词消歧先看语义搭配再套语法位置（Halliday 7.3.2，已采纳）','主位-述位框架只是辅助，语义通不通说了算','B013'),
 ]),
 dict(id='lianjie', name='逻辑连接', terms=[
   ('本体·深挖', '连接四类', 'Halliday 骨架：增补/转折/因果/时间——先定大类再查细节（中文对照用邢福义三分）','furthermore 归增补（递进功能上就是增补——经裁定）','B015'),
   ('论证关联', '语境效果三情况', '每个新句子对前文只做三件事之一：推出新含意/证实旧假设/推翻旧假设','例证段=证实，转折段=推翻，因果段=推新','B074'),
   ('本体·深挖', '无标连接', '没有连接词时靠语义关系直接判断——标志只是路标不是本质','两句间没 but，但方向拐了就是转折','B026'),
 ]),
 dict(id='gaikuo', name='概括与保主舍次', terms=[
   ('本体·深挖', '保主舍次', '概括=决策：能取能舍——保留对主旨表现力度大的，舍弃次要','记叙文抓主要人物主要事件，次要人物一笔带过','B021'),
   ('本体·深挖', '奥卡姆剃刀', '如无必要勿增实体——概括完检查有没有多余的词','概括句里出现两个都在说"重要"的词就删一个','A013'),
   ('本体·深挖', '丢包袱', '概括的核心比喻：丢掉非概括性语言（具体/形象/含蓄/反面/侧面）','比喻句"将只手撑天空"→ 丢形象留抽象「力量大」','A004'),
   ('概括关联', '正反两面', '「不是X而是Y」类：丢反面留正面，反面只是铺垫','「不能仅止于温饱，更应该有精神追求」→ 抓精神追求','B009'),
 ]),
 dict(id='zhuzhi', name='主旨题', terms=[
   ('本体·深挖', '论点句骨架', '中心论点/分论点是文章骨架，其他内容是围着骨架长的肉','议论文先找 thesis 再看各段功能','B002'),
   ('题型关联', '宏观扫描五问', 'What/Why/How/When/Where 五问先扫一遍全文结构','首段末+末段+各段首句串读=30 秒主旨预判','B040'),
   ('题型关联', '叙述五段', '叙事文骨架： abstract/direction/complicating action/evaluation/resolution（Labov）','故事题按 情景-问题-解决-评估 四步切','B034'),
   ('题型关联', '末段陷阱', '主旨不总在末段——问题型议论文主旨=问题反面/解决方案','全文批 # 现象、末段给建议 → 主旨是建议不是批判','B036'),
 ]),
 dict(id='lunzheng', name='论证', terms=[
   ('题型关联', '虚拟语气=反事实', 'could/would have done...if...had done = 与事实相反的假设，事实恰是其否定；把虚拟当已发生必错（六级高频招）','could have increased if...had been addressed → 事实是没解决、没增长','B075'),
   ('题型关联', '必要性缩圈', '功能题两步法第一步：先不看目标部分，看 X→[?]→Y 结构反推该位置必须承担什么功能（删掉行不行）——缩圈后再用部分本身的物质属性定夺','前讲数据铺垫后讲例证 → 中间那段应是让步转折立论','A031'),
   ('题型关联', '模态越界', '文章说 may 选项说 must=把可能性升格成必然性=错（模态只有必然→可能单向可推）；some→all、suggest→prove 同族','「可能延缓」说成「必然治愈」','A034'),
   ('题型关联', '主客观串门', '作者观点≠客观事实：观点事实化（认为→被证明）/事实观点化（数据→夸张）都是串门；态度题答观点细节题答事实','「作者认为有益」说成「被证明有益」','A035'),
   ('题型关联', '概括颗粒度', '中文概括题按评分颗粒度拆条：主谓短句逐点、分别/各→主体分条、措施成效配对、折射题两层都写','对策题每点一短句=满分结构','B084'),
   ('本体·深挖', '分类讨论', '分类=把不确定转化为确定的过程（数学分类讨论思想）：每类情况都掌握=被分类者被完全掌握；分类项之间=并列关系','问「整体如何」的题，单一类别冒充整体=以偏概全','A033'),
   ('题型关联', '跨类嫁接', '把 A 类性质安到 B 类头上=最高频陷阱；「运动时宜鼻呼吸」说成「宜鼻呼吸」=抹掉限定变绝对化','口呼吸者认知差 → 选项说成所有人认知差','A033'),
   ('本体·深挖', '理由支撑结论', '论证=拿出一组理由给结论撑腰——主旨=结论，其余段落=前提','therefore/thus 引出的句子是结论句','A023'),
   ('题型关联', '让步≠立场', 'it is true that/admittedly 是作者主动摆的表面反例，先破后立','admittedly X, but Y → 立场在 Y','B053'),
   ('题型关联', '谬误识别', '人身攻击/假二难/稻草人/偷换概念等 8 项=干扰项原型库','选项攻击"提出者"而非"论证"= 人身攻击谬误','B054'),
   ('题型关联', '定义三规则', '词义不明先明确：具体且前后一致；种属+种差','争议词先看作者怎么定义它再做题','B059'),
 ]),
 dict(id='yanei', name='言外之意（语用）', terms=[
   ('题型关联', '等级含意', '说 some/often/possible 就在暗示不是 all/always/certain','文中 some students → 不等于 all students，推断题别越级','B075'),
   ('题型关联', '前提触发语', 'trigger 词一出现，作者免费送你一个默认成立的事实','stopped smoking → 他以前抽烟（不用明说）','B076'),
   ('题型关联', '间接言语行为', 'Can you...? 不是问能力是提请求——先定字面用意再推间接用意','Could you pass the salt? = 请求','B077'),
   ('题型关联', '选项位置判别', '干扰项最爱用原文词伪装——八类错法定稿：因果链位置/段功能/方向/所属对象/范围限定/判断归属/话题切分/热点vs推荐','genetic diversity 是结果不是主张；separate→transform 名词对动词反','B083'),
   ('题型关联', '话语标记定态度', 'actually/anyway/after all/still 标记说话人真实态度的转折点','actually 之后才是说话人真意','B070'),
 ]),
 dict(id='ciyi', name='词义与语境', terms=[
   ('本体·深挖', '词本无意，意由境生', '词在文章里的含义受语境影响——猜词先查语境三要素再验主题','struck 在不同句里可以是"打击/打动/罢工"','B037'),
   ('题型关联', '三查一极性', '动作先后、发出者/承受者、动作状态，再查态度极性，最后代入主题','猜划线词先问谁对谁做、在什么之前之后','B037'),
   ('本体·深挖', '七种意义', '利奇七类：概念/内涵/社会/情感/反映/搭配/主题意义——词义不止词典义','generous 的社会意义来自使用场合，不只在释义里','A025'),
   ('本体·深挖', '语义五维', '主体·动作·承受者·情感色彩·程度——原创分析轴','说"几乎全完了"：程度维「几乎」是考点','A024'),
 ]),
 dict(id='liubai', name='空白与读者（伊瑟尔）', terms=[
   ('题型关联', '空白与召唤结构', '文本是结构化的指示，意义靠读者自己"串线"填充','句间断开处=考点定位器——命题人专挑空白出题','A026'),
   ('本体·深挖', '因果留白', '原创提炼：作者故意不写因果链，读者自己推——R2 细则','文中只给"雨后学校停课"，自己补"因为积水"','R2'),
   ('本体·深挖', '游移视点', '读者位置在记忆与期待的交叉点：过去影响现在、现在也改变过去','读到结尾回头改写对开头的理解','A028'),
   ('题型关联', '元认知', '观察代替准则：高级阅读是看着自己正在被文本引导','发现"我刚才以为作者是支持，其实是在反讽"','A029'),
 ]),
 dict(id='sanwei', name='三维框架', terms=[
   ('本体·深挖', '三维框架', '原创提炼：分析立场分三维——作者维（预判读者卡壳处）/文本维（多视点互证互限）/读者维（自己推）','态度题立场属于作者维度，人物的话≠作者态度','A030'),
   ('本体·深挖', '暗隐的作者', '作者从不在文中露面，但预判读者会在哪里惯性接受、故意设纠偏点','叙述者自夸时，作者可能正等着你怀疑他','A030'),
 ]),
 dict(id='xuanclotian', name='选词填空（CET）', terms=[
   ('题型关联', '槽位过滤', '选词填空第一过滤器：语法槽位定词性——并列定词性/被动定pp/介词后动名词/主语单数定三单；词库先按词性分堆','「and strategic」→ 形容词位 → complex（26题实战）','B081'),
   ('题型关联', '反义互补秒空', '并列对照位的反义互补：succeed in...and where they __ → struggle','34 题 succeed/struggle 一对秒定','B072'),
   ('概括关联', '固定搭配锁死', 'build a reputation 这类搭配直接锁空，不用二筛','30 题 for __ a good reputation → building','B012'),
 ]),
 dict(id='changpian', name='长篇匹配（CET）', terms=[
   ('题型关联', '三步定位', '题干扫关键词 → 原文找同义替换锚点 → 身份词对齐到人；同义替换占一半（marketable=commercially feasible）','43 题 marketable → D 段 commercially feasible','B082'),
   ('题型关联', '复现是本命', '10 题里 9 题靠复现链：原词/同义/数字；不考主旨分析，别拿主旨题打法套它','36 题 training/support 原词复现 → H 段','B011'),
   ('题型关联', '身份词对齐', '题干给身份不给名：回原文找具体人——judge→Cleaver，officer→Kampfner','38 题 judge → L 段 Naomi Cleaver','B013'),
 ]),
]

# ---------- 从卡文件取「一句话」 ----------
def card_oneliner(citation):
    m = re.match(r'([ABR])(\d{1,3})', citation)
    if not m: return ''
    letter = {'A':'A-analysis','B':'B-skills','R':'REVIEW'}[m.group(1)]
    num = m.group(2)
    d = os.path.join(CARD, letter)
    if not os.path.isdir(d): return ''
    # ⚠️ 两类命名：A/B 系是 `001-*.md`（三位数字补零），
    #    **R 系是 `R1-*.md`**（2026-09-30 修）。
    #    旧写法一律 `startswith(num)` 且正则写死 `\d{3}` → R 系卡既匹配不上正则、
    #    也 glob 不到文件，**在这个生成器里恒取不到「一句话」**。
    #    这与「R 系卡在交付件里取不到」是**同一个月内第三次同类缺陷**：
    #    凡是「按编号找卡」的地方，都默认了 A/B 的命名法。
    prefix = (num + '-') if m.group(1) == 'R' else (num.zfill(3) + '-')
    files = [f for f in sorted(os.listdir(d))
             if f.startswith(prefix) and f.endswith('.md')]
    if not files: return ''
    t = open(os.path.join(d, files[0]), encoding='utf-8').read()
    m2 = re.search(r'^>\s*\*\*一句话\*\*[:：]\s*(.+)$', t, re.M)
    return (m2.group(1).strip() if m2 else '')

def block_oneliner(citation):
    """带章节号的引用（如 B021③）——回整卡一句话"""
    return card_oneliner(citation)

# ---------- 卡库全量扫描 + 自动兜底（2026-09-30 立）----------
#
# —— 为什么加这一段 ——
# 图谱的 62 条关系是**人工写在 `KP` 里的**（「提案后经审校」）。
# 于是每加一张卡都得**记得**回来手工补一条 —— 而人不会一直记得：
# 实测停留在 **42/127 = 33%**，B085 / B086 / A036 / R1~R5 全都没进。
# **覆盖率的衰减是静默的**：没报错、没红叉，只是那张卡从此不在图谱里。
#
# 这就是「机制取代自律」该上场的地方：**图谱不该依赖人记得更新**。
# 做法是**自动兜底** —— 扫描卡库，凡是没被 `KP` 引用的卡，
# 自动收进文末的「待归类」区（按系列分组、附上卡的「一句话」）。
# 效果有三：
#   ① **覆盖率恒为 100%**，不会再静默漏卡；
#   ② 没归类的卡**看得见**了 —— 那份清单本身就是待办；
#   ③ 归类仍是人工判断（该归到「并列」还是「因果」，机器猜不准），
#      但**「漏了」不再需要靠人发现**。
#      即：人只负责「判断」，不负责「记得」。

def all_cards():
    """扫描卡库 → {卡号: 文件路径}。A/B 认 `001-*.md`，R 认 `R1-*.md`。"""
    out = {}
    for sub, pre in (('A-analysis', 'A'), ('B-skills', 'B'), ('REVIEW', 'R')):
        d = os.path.join(CARD, sub)
        if not os.path.isdir(d): continue
        for f in sorted(os.listdir(d)):
            if not f.endswith('.md'): continue
            if pre == 'R':
                # ⚠️ R 系文件名已含前缀（`R1-what.md`），**不能再拼一次** pre，
                #    否则卡号会变成 `RR1`、且 card_oneliner 也就匹配不上 → 取不到「一句话」。
                m = re.match(r'^(R\d)-', f)
                if m:
                    out[m.group(1)] = os.path.join(d, f)
                continue
            m = re.match(r'^(\d{3})-', f)
            if m:
                out[pre + m.group(1)] = os.path.join(d, f)
    return out

def cited_card_ids():
    """KP 引用到的卡号集合（去掉 B021③ 这类章节后缀）。"""
    s = set()
    for kp in KP:
        for item in kp['terms']:
            m = re.match(r'([ABR]\d{1,3})', str(item[4]))
            if m: s.add(m.group(1))
    return s

def card_title(path):
    """取卡文件首行的标题（去掉编号前缀）。"""
    try:
        for ln in open(path, encoding='utf-8').read().splitlines():
            if ln.startswith('# '):
                return re.sub(r'^[ABR]?\d{1,3}\s*', '', ln[2:].strip())
    except Exception:
        pass
    return ''

def unclassified():
    """未进 KP 的卡：[(卡号, 标题, 一句话), ...]，按系列+编号排序。"""
    cards = all_cards()
    cited = cited_card_ids()
    rows = []
    for cid in sorted(set(cards) - cited,
                      key=lambda c: (c[0], int(re.sub(r'\D', '', c) or 0))):
        p = cards[cid]
        rows.append((cid, card_title(p), card_oneliner(cid)))
    return rows

# ---------- 生成 HTML ----------
CSS = '''
:root{--bg:#ffffff;--fg:#1f2328;--mut:#656d76;--line:#d8dee4;--acc:#0969da;--accbg:#ddf4ff;--tagbg:#f6f8fa;}
*{box-sizing:border-box}body{margin:0;font-family:"Segoe UI","Microsoft YaHei",sans-serif;background:var(--bg);color:var(--fg);line-height:1.75}
.wrap{display:flex;max-width:1200px;margin:0 auto}
nav{width:230px;flex:none;position:sticky;top:0;align-self:flex-start;height:100vh;overflow-y:auto;padding:20px 12px;border-right:1px solid var(--line)}
nav h3{font-size:13px;color:var(--mut);margin:14px 8px 4px}
nav a{display:block;padding:6px 10px;border-radius:8px;color:var(--fg);text-decoration:none;font-size:14px}
nav a:hover{background:var(--accbg)}
main{flex:1;min-width:0;padding:28px 34px 80px}
h1{font-size:24px;margin:0 0 6px}p.sub{color:var(--mut);font-size:14px;margin:0 0 24px}
.kp{margin:0 0 44px;padding-top:8px}
.kp>h2{font-size:20px;margin:0 0 4px;padding-bottom:6px;border-bottom:2px solid var(--acc)}
.block{margin:14px 0;background:var(--tagbg);border-left:4px solid var(--acc);border-radius:0 10px 10px 0;padding:10px 16px}
.block h4{margin:2px 0 6px;font-size:13px;color:var(--acc);letter-spacing:1px}
.block .oneliner{font-size:14.5px}
.term{margin:8px 0}
.term summary{cursor:pointer;font-weight:600;background:var(--accbg);display:inline-block;padding:3px 12px;border-radius:14px;font-size:14px}
.term summary::marker{color:var(--acc)}
.term .exp{border:1px solid var(--line);border-radius:10px;padding:10px 16px;margin-top:6px;font-size:14.5px;background:#fff}
.term .exp .lbl{color:var(--acc);font-weight:600}
.term .exp .src{color:var(--mut);font-size:12.5px;margin-top:4px}
@media(max-width:760px){nav{display:none}main{padding:18px 16px 60px}.wrap{display:block}}
'''
JS = '<script>/* 渐进增强：当前无 JS 依赖，details 原生可用 */</script>'

def build():
    cards_total = len(all_cards())
    cite = cited_card_ids()
    unc = unclassified()
    parts = ['<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">',
             '<meta name="viewport" content="width=device-width,initial-scale=1">',
             '<title>知识网络 · 阅读分析</title><style>' + CSS + '</style></head><body>']
    nav = ['<div class="wrap"><nav><h3>知识网络</h3>']
    body = ['<main><h1>知识网络</h1><p class="sub">点一个知识点 → 聚合它在各板块的关联内容；点术语 → 看一句话定义 + 一个实例。'
            '资料层 = references/cards/ 共 %d 张卡，其中 <b>%d 张已归类</b>、%d 张在文末「待归类」。'
            '</p>' % (cards_total, cards_total - len(unc), len(unc))]
    for kp in KP:
        anchor = 'kp-' + kp['id']
        nav.append('<a href="#%s">%s</a>' % (anchor, html.escape(kp['name'])))
        body.append('<section class="kp" id="%s"><h2>%s</h2>' % (anchor, html.escape(kp['name'])))
        # 本体块（取第一个 term 的主卡作本体卡引用）
        main_card = kp['terms'][0][3] if kp['terms'] else ''
        body.append('<div class="block"><h4>① 本体</h4><div class="oneliner">%s<br><span style="color:var(--mut);font-size:12.5px">出处卡：%s</span></div></div>'
                    % (html.escape(card_oneliner(main_card) or '见对应卡'), html.escape(main_card)))
        # 其余术语 = 各板块关联（概括/论证/题型/语用——按实际关联呈现，区块数量由知识库决定）
        blocks = {}
        for blk, term, dfn, ex, src in kp['terms']:
            blocks.setdefault(blk, []).append((term, dfn, ex, src))
        n = 2
        for blk, items in blocks.items():
            body.append('<div class="block"><h4>%s %s</h4>' % ('②③④⑤⑥⑦'[n-2] if n<=7 else '·', html.escape(blk)))
            for term, dfn, ex, src in items:
                body.append('<details class="term"><summary>%s</summary><div class="exp">'
                            '<div><span class="lbl">是什么：</span>%s</div>'
                            '<div><span class="lbl">实例：</span>%s</div>'
                            '<div class="src">出处卡：%s</div></div></details>'
                            % (html.escape(term), html.escape(dfn), html.escape(ex), html.escape(src)))
            body.append('</div>')
            n += 1
        body.append('</section>')
    # —— 自动兜底区：没进 KP 的卡（生成，不是人写的）——
    nav.append('<h3>待归类</h3>')
    nav.append('<a href="#kp-tobesorted">待归类（%d）</a>' % len(unc))
    body.append('<section class="kp" id="kp-tobesorted"><h2>待归类（%d 张）</h2>' % len(unc))
    body.append('<div class="block"><h4>这一区是自动生成的</h4>'
                '<div class="oneliner">凡是没被上面任一知识点引用的卡，都会落到这里 —— '
                '<b>所以图谱永远不会漏卡</b>。这份清单本身就是待办：'
                '挑一张、判断它该归到哪个知识点下面（该归「并列」还是「因果」，机器猜不准），'
                '然后把它加进生成脚本的 <code>KP</code> 列表。'
                '清单清空时，说明归类工作做完了。</div></div>')
    groups = {}
    for cid, title, one in unc:
        groups.setdefault(cid[0], []).append((cid, title, one))
    for pre, label in (('A', 'A 系 · 分析基础'), ('B', 'B 系 · 方法技巧'), ('R', 'R 系 · 复盘')):
        if pre not in groups: continue
        body.append('<div class="block"><h4>%s（%d）</h4>' % (html.escape(label), len(groups[pre])))
        for cid, title, one in groups[pre]:
            body.append('<details class="term"><summary>%s %s</summary><div class="exp">'
                        '<div><span class="lbl">一句话：</span>%s</div></div></details>'
                        % (html.escape(cid), html.escape(title or ''),
                           html.escape(one or '（这张卡没写「一句话」）')))
        body.append('</div>')
    body.append('</section>')
    nav.append('</nav>')
    body.append('</main></div>' + JS + '</body></html>')
    html_text = ''.join(parts) + ''.join(nav) + ''.join(body)
    os.makedirs(os.path.dirname(OUT_HTML), exist_ok=True)
    open(OUT_HTML, 'w', encoding='utf-8').write(html_text)
    print('[OK] %s (%d KB, %d 个知识点)' % (OUT_HTML, os.path.getsize(OUT_HTML)//1024, len(KP)))
    print('[覆盖率] 卡库 %d 张：已归类 %d / 待归类 %d' % (cards_total, cards_total - len(unc), len(unc)))
    # 同步生成映射表 MD（供审校）
    md = ['# 知识网络映射表（呈现层 → 资料层）', '',
          '> 由 scripts/render_knowledge_graph.py 同步生成。区块数量由知识库实际关联决定。',
          '> 文末「待归类」区**自动生成**：没被引用的卡会自己落进去，所以本表不会漏卡。',
          '> （收口检查会核「本表提到的卡号 == 卡库实际卡号」——手删一行、或加了卡没重跑，都会被它抓到。）', '']
    for kp in KP:
        md.append('## %s' % kp['name'])
        md.append('- 本体：%s' % kp['terms'][0][3])
        for blk, term, dfn, ex, src in kp['terms']:
            md.append('- 【%s】**%s**：%s（例：%s）→ %s' % (blk, term, dfn, ex, src))
        md.append('')
    md.append('## 待归类（自动生成 · %d 张）' % len(unc))
    md.append('')
    md.append('> 没被上面任一知识点引用的卡自动列在这里 —— **图谱因此不会漏卡**。')
    md.append('> 这份清单就是待办：挑一张、判断该归到哪个知识点下，再加进生成脚本的 `KP`。')
    md.append('> （这里只列卡号与标题，省体积；每张的「一句话」见 HTML 版同名区块。）')
    md.append('')
    for pre, label in (('A', 'A 系'), ('B', 'B 系'), ('R', 'R 系')):
        if pre not in groups: continue
        md.append('### %s（%d）' % (label, len(groups[pre])))
        for cid, title, one in groups[pre]:
            md.append('- **%s** %s' % (cid, title or ''))
        md.append('')
    open(OUT_MD, 'w', encoding='utf-8').write(chr(10).join(md))
    print('[OK] %s' % OUT_MD)

if __name__ == '__main__':
    build()
