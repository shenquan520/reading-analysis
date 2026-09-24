#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cross_round_check.py — 跨轮回归核验（每轮必跑）

## 这个脚本解决什么问题

单轮审计看不见「**改动互相踩踏**」：第 N 轮修好的东西，可能在 N+1、N+2 轮大改同一批文件时被碰回去。
实测依据（本项目真实案例）：
  · 第七轮加了「施事判定」清掉 8 条误报 → **把中文话题句 5/5 全杀**（第八轮才发现）
  · 第八轮把 fixture 的字段从 passage 层挪进 note 层 → **契约缺口照旧被掩盖**（第九轮才发现）
  · 第五轮报告当时没被处理 → 那 9 条样本**一直没入库**，直到第九轮翻目录才发现

所以：**查的不是「当初修没修」，而是「后面若干轮有没有碰回去」。**

## 怎么用

    python scripts/cross_round_check.py                 # 自动定位 skill 根（脚本的上级目录）
    python scripts/cross_round_check.py --skill-root <路径>
    python scripts/cross_round_check.py --json          # 机器可读输出

退出码 0 = 全关；1 = 有回归（**别提交**）。

## 维护纪律（重要）

**追加式**：每轮复验发现的新判据，加进 `CHECKS` 列表并注明轮次与来源，**永不删除**。
与 `ap_cases.py` 同一套纪律——它是「判据的回归集」，ap_cases 是「样本的回归集」。
"""
import argparse
import glob
import importlib.util
import io
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT = os.path.dirname(HERE)


def _load_ap(root):
    spec = importlib.util.spec_from_file_location("ap", os.path.join(root, "scripts", "anti_patterns.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _load_cases(root):
    sys.path.insert(0, os.path.join(root, "scripts"))
    import ap_cases
    return ap_cases


SKIP = "SKIP"   # 三态：True 通过 / False 失败 / SKIP 条件不成立（**不算通过**，如实报「没查」）


def build_checks(root, export):
    """返回 [(轮次, 名称, 返回 (ok, detail) 的函数)]

    ok 三态：True / False / SKIP。
    ⚠️ SKIP ≠ 通过：本包没有对照版时，「两版一致」这类检查**根本没法判**，
       如实报「没查」而不是默认绿——静默绿着就是假防护（与审计工具 G35 同一立场）。
    """
    ap = _load_ap(root)
    idx = ap.load_index()
    has_export = os.path.isdir(export)

    def read(rel, base):
        p = os.path.join(base, rel)
        return io.open(p, encoding="utf-8").read() if os.path.isfile(p) else None

    # ---------- 第三轮：账本回声口径 ----------
    def r3_no_echo_in_ledger():
        """账本不许回引被清理的具体值（格式模板可以）"""
        if not has_export:
            return SKIP, "本包无对照版本（export 目录不存在）→ 未查"
        t = read("CHANGELOG.md", export)
        if t is None:
            return SKIP, "该包无 CHANGELOG.md → 未查"
        hits = re.findall(r"材料[①②③④⑤]|\bQ\d{1,3}\b|PRACTICE\s*\d+", t)
        return (not hits), (f"命中 {hits[:3]}" if hits else "0 处")

    # ---------- 第五轮：9 条真实自述（当时 4/9） ----------
    def r5_self_reports():
        cases = _load_cases(root).ROUND5_SELF
        miss = [t for t in cases if not ap.match(t, idx)]
        return (not miss), (f"{len(cases) - len(miss)}/{len(cases)}" + (f" 漏 {miss[:2]}" if miss else ""))

    # ---------- 第七轮：评价文章不该被当成认错 ----------
    def r7_eval_not_self_report():
        cases = _load_cases(root).NEUTRAL_EVAL
        bad = [t for t in cases if ap.match(t, idx)]
        return (not bad), (f"{len(cases) - len(bad)}/{len(cases)}" + (f" 误 {bad[:2]}" if bad else ""))

    # ---------- 第八轮：中文话题句不得被施事判定误杀 ----------
    def r8_topic_fronted_survives():
        cases = _load_cases(root).SELF_TOPIC_FIRST
        miss = [t for t in cases if not ap.match(t, idx)]
        return (not miss), (f"{len(cases) - len(miss)}/{len(cases)}" + (f" 漏 {miss[:2]}" if miss else ""))

    # ---------- 第五轮 N1 / 第八轮 M3：AP-12 症状不得静默消失 ----------
    def r5_ap12_symptom_present():
        """数据侧有值 + 解析器能合并多行子项（治根因，不只是治数据）"""
        if not str(idx.get("AP-12", {}).get("symptom", "")).strip():
            return False, "AP-12 症状为空（数据侧）"
        demo = ("### AP-99 多行测试\n- **匹配关键词**：测试词\n- **症状**：\n  - 子行A\n"
                "- **为什么错**：x\n- **怎么防**：y\n- **挂卡**：A003\n")
        import tempfile
        tf = os.path.join(tempfile.gettempdir(), "ap_cross_round_demo.md")
        io.open(tf, "w", encoding="utf-8").write(demo)
        sy = ap.load_index(tf).get("AP-99", {}).get("symptom", "")
        return ("子行A" in sy), f"多行子项合并为 {sy!r}"

    # ---------- 第九轮 N2 / 第八轮 M3：契约文档必须声明代码读取的字段 ----------
    def r9_contract_declares_function():
        """写法 C 的 docstring 声明键集必须含代码实际读取的 function"""
        t = read("scripts/analysis_to_html.py", root)
        if t is None:
            return False, "找不到渲染管线"
        m = re.search(r"C\.\s*[^\n]*paragraph_notes\s*=\s*\[\{([^}]*)\}", t)
        if not m:
            return False, "docstring 里找不到写法 C 的字段清单"
        declared = {x.strip().strip('"') for x in m.group(1).split(",") if x.strip()}
        ok = "function" in declared
        return ok, f"声明 {sorted(declared)}"

    # ---------- 跨轮固定项：两版一致 ----------
    def r12_evidence_not_stale():
        """证据文件不早于最后一次提交（第十二轮 P1）

        案件：`复验输出-第十一轮整改` 于 00:04:53 生成，之后 00:05:27 又提交了账本改期；
        而文件头写着「本文件为推送后重跑」——**门禁块贴的是修复前的输出，结论行是修复后的**。
        只读门禁块的人以为被卡住，只读结论行的人以为全绿。**这比数字错更坏：它毁的是证据链。**

        判据：`dist/` 里最新一份「复验输出-*.txt」的 mtime **必须 >= 仓库最后一次提交时刻**；
        早于 → 快照不是最终状态，必须用 `python scripts/make_evidence.py` 整份重跑。

        ⚠️ 没有证据文件 / 不是 git 仓库 → **SKIP**（如实报「未查」，不默认绿）——
        第三方拿到的包本来就没有 dist/，那是正常情况，但「正常」不等于「查过了」。
        """
        dist = os.path.join(root, "dist")
        if not os.path.isdir(dist):
            return SKIP, "本包无 dist/ → 未查"
        files = [p for p in glob.glob(os.path.join(dist, "复验输出-*.txt"))]
        if not files:
            return SKIP, "本包无「复验输出-*.txt」（第三方包属正常）→ 未查"
        newest = max(files, key=os.path.getmtime)
        # 提交历史取**有 .git 的那一份**：本地工作区通常不是 git 仓库（只有开源包是），
        # 所以不能只看 root —— 否则这道门禁在本地永远 SKIP＝空转（第一次写就踩到了）。
        git_dir = export if os.path.isdir(os.path.join(export, ".git")) else root
        r = subprocess.run(["git", "-C", git_dir, "log", "-1", "--format=%ct"],
                           capture_output=True, text=True)
        if r.returncode != 0 or not r.stdout.strip().isdigit():
            return SKIP, "找不到 git 仓库（本地与开源包都不是）→ 未查"
        head_t = int(r.stdout.strip())
        ev_t = int(os.path.getmtime(newest))
        name = os.path.basename(newest)
        if ev_t >= head_t:
            return True, f"最新证据 {name} 晚于（或等于）最后一次提交 ✅"
        lag = head_t - ev_t
        return False, (f"❌ 最新证据 {name} 早于最后一次提交 {lag // 60}m{lag % 60}s —— "
                       f"快照不是最终状态，请重跑 `python scripts/make_evidence.py`")

    def r13_gap_ledger():
        """缺口台账闭环（第十二轮，评审 L4 交付件时立）

        案件：`case-208`（09-06）提的缺口，**19 天后的 `case-209`（09-25）又提了一遍**，中间无人跟。
        审核方原话：「缺口这个最值钱的产出没有闭环……不记台账，它 19 天后也会变成同一条回头账。」

        规格里写着「▮缺口 = 最值钱的产出」，但它过去只是**散落在 case 文件里的一段话**。
        本轮建了 `references/缺口台账.md`：每条约定的状态（待立卡/已立卡/已增强/暂不新建/驳回）。

        判据：**每个声明缺口的 case 都必须在台账里有行**，且状态列不许留白。
        台账不随包发布（引用内部案例内容）→ 第三方包里**如实报 SKIP**，不默认绿。
        """
        gl = os.path.join(root, "scripts", "gap_ledger.py")
        ledger = os.path.join(root, "references", "缺口台账.md")
        if not os.path.isfile(ledger):
            return SKIP, "本包无 缺口台账.md（本地工作区专有）→ 未查"
        if not os.path.isfile(gl):
            return SKIP, "本包无 scripts/gap_ledger.py（本地专用工具）→ 未查"
        spec = importlib.util.spec_from_file_location("gap_ledger_cr", gl)
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        except SystemExit:
            pass
        gaps = mod.extract_gaps(root)
        problems, rows = mod.check(root, gaps)
        n_case = len(set(g[0] for g in gaps))
        if problems:
            return False, f"❌ 台账 {len(rows)} 行 / 声明缺口的 case {n_case} 个：{problems[:2]}"
        return True, f"台账 {len(rows)} 行，覆盖声明缺口的 {n_case} 个 case，状态列无留白 ✅"

    def two_versions_identical():
        if not has_export:
            return SKIP, "本包无对照版本 → 未查（该检查只在本包 + 开源包成对时才有意义）"
        rels = ["scripts/anti_patterns.py", "scripts/ap_cases.py", "scripts/verify_anti_patterns.py",
                "scripts/analysis_to_html.py", "references/ANTI-PATTERNS.md"]
        bad = []
        for rel in rels:
            a, b = read(rel, root), read(rel, export)
            if a is None or b is None:
                bad.append(rel + "(缺)")
            elif a != b:
                bad.append(rel)
        return (not bad), ("一致" if not bad else f"不一致/缺失：{bad}")

    # ---------- 跨轮固定项：开源包零内部标记（标记清单来自包外配置） ----------
    def export_has_no_internal_markers():
        """标记清单从包外读（--config / SKILL_AUDIT_CONFIG / SKILL_AUDIT_MARKERS）。

        读不到 → **不算通过，算「没查」**（与审计工具 G35 同一立场：静默绿着是假防护）。
        """
        markers, src = _load_markers(export if has_export else root, root)
        if not markers:
            return False, "未找到标记清单 → 本次未查（不是通过）。请配包外配置"
        # 跳过目录与审计工具保持一致（**也从配置读**，否则又是一份会走样的清单）：
        # 实测踩到过：只跳 .git/__pycache__/dist/node_modules 时，扫到了 `.audit_history/` 里的
        # 审计快照（含本机路径）→ 报出 3 处假阳性。那些快照是 gitignored、从不发布的本地历史。
        skip = set(_load_skip_dirs(export if has_export else root))
        hits = []
        for dp, dirs, files in os.walk(export):
            dirs[:] = [d for d in dirs if d not in skip]
            for fn in files:
                fp = os.path.join(dp, fn)
                try:
                    t = io.open(fp, encoding="utf-8", errors="ignore").read()
                except Exception:
                    continue
                for mk in markers:
                    if mk in t:
                        hits.append(f"{os.path.relpath(fp, export)}:{mk}")
        return (not hits), (f"{len(markers)} 个标记来自 {src}，0 命中" if not hits else f"{len(hits)} 处：{hits[:3]}")

    def r11_required_fields_carried():
        """规范标「必填」的项，通用管线必须真承载（缺口栏 / 可迁移原则）

        为什么进跨轮核验：**这个洞发生过两次**——
          第一次：反模式层只做在案例脚本里，通用管线没接（第六轮 L3 抓到）
          第二次：缺口栏 + 可迁移原则同样只做在案例脚本里（第十一轮 L3 抓到）
        同一个「案例脚本有、通用管线没有」的结构问题复发，说明它需要一条**每轮都跑**的检查，
        而不是等下一次 L3 冷启动再发现。
        口径：**元素级**（数 class="gap" 元素），不 grep 关键字——CSS 里也有同名 class。
        """
        fp = os.path.join(root, "scripts", "analysis_to_html.py")
        if not os.path.isfile(fp):
            return False, "找不到渲染管线"
        spec = importlib.util.spec_from_file_location("a2h_cr", fp)
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        except SystemExit:
            pass
        d = {"title": "cr", "summary": {}, "passage": {}, "review": {},
             "questions": [{"q": "q1", "answer": "B", "why": "w", "cards": [],
                            "gap": "待立卡", "transfer": "迁移到同类题"}]}
        html = mod.build(d)
        n_gap = len(re.findall(r'<div class="gap">', html))
        n_note = len(re.findall(r'<div class="note">', html))
        return (n_gap == 1 and n_note == 1), f"gap 元素={n_gap} note 元素={n_note}"

    CHECKS = [
        ("R11", "必填项承载力：缺口栏+可迁移原则", r11_required_fields_carried),
        ("R12", "证据文件不早于最后一次提交", r12_evidence_not_stale),
        ("R13", "缺口台账闭环（最值钱产出的状态）", r13_gap_ledger),
        ("R3", "账本无具体值回声", r3_no_echo_in_ledger),
        ("R5", "9 条真实自述全命中（当时 4/9）", r5_self_reports),
        ("R5", "AP-12 症状不静默消失（含解析器多行合并）", r5_ap12_symptom_present),
        ("R7", "评价文章不被误当成认错", r7_eval_not_self_report),
        ("R8", "中文话题句不被误杀", r8_topic_fronted_survives),
        ("R9", "契约 docstring 声明 function", r9_contract_declares_function),
        ("跨轮", "两版关键文件逐字节一致", two_versions_identical),
        ("跨轮", "开源包零内部标记（清单取自包外）", export_has_no_internal_markers),
    ]
    return CHECKS


def _load_skip_dirs(base):
    """跳过目录读配置（与审计工具同源）；读不到给一份保守默认。"""
    for p in (os.path.join(base, "_audit.json"),
              os.path.expanduser("~/.workbuddy/skills-config/reading-analysis.audit.json")):
        if os.path.isfile(p):
            try:
                cfg = json.load(io.open(p, encoding="utf-8"))
            except Exception:
                continue
            sd = [str(x) for x in (cfg.get("skip_dirs") or []) if str(x).strip()]
            if sd:
                return sd
    return [".git", "__pycache__", "dist", "node_modules", ".audit_history"]


def _load_markers(export, root):
    """与 skill_audit.py / sync_export.py 保持同一优先级：env → 包外 → 包内（兼容）。"""
    cands = []
    env = (os.environ.get("SKILL_AUDIT_CONFIG") or "").strip()
    if env:
        cands.append(("SKILL_AUDIT_CONFIG", env))
    envm = (os.environ.get("SKILL_AUDIT_MARKERS") or "").strip()
    if envm:
        ms = [x.strip() for x in re.split(r"[,\n]", envm) if x.strip()]
        if ms:
            return ms, "SKILL_AUDIT_MARKERS"
    here = os.path.expanduser("~")
    cands += [
        ("包外默认", os.path.join(here, ".workbuddy", "skills-config", "reading-analysis.audit.json")),
        ("包内（旧位置）", os.path.join(export, "_audit.json")),
        ("包内本地（旧位置）", os.path.join(root, "_audit.json")),
    ]
    for label, p in cands:
        if p and os.path.isfile(p):
            try:
                cfg = json.load(io.open(p, encoding="utf-8"))
            except Exception:
                continue
            ms = [str(m) for m in (cfg.get("internal_markers") or []) if str(m).strip()]
            if ms:
                return ms, label
    return [], None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skill-root", default=DEFAULT_ROOT)
    ap.add_argument("--export", default=None)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    root = os.path.abspath(a.skill_root)
    export = os.path.abspath(a.export) if a.export else os.path.join(root, "github-export")

    checks = build_checks(root, export)
    rows, failed = [], 0
    for tag, name, fn in checks:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"异常 {type(e).__name__}: {e}"
        if ok is False:
            failed += 1
        rows.append({"round": tag, "name": name, "ok": ok, "detail": detail})

    allok = (failed == 0)
    if a.json:
        print(json.dumps({"ok": allok, "checks": rows}, ensure_ascii=False, indent=2))
    else:
        print("跨轮回归核验（查「后面若干轮有没有把早先的修复碰回去」）")
        print(f"skill 根：{root}")
        print("=" * 86)
        icon = {True: "✅", False: "❌", SKIP: "⏭️"}
        for r in rows:
            print(f"  {icon[r['ok']]} [{r['round']:>2}] {r['name']:34} {r['detail']}")
        print("=" * 86)
        npass = sum(1 for r in rows if r["ok"] is True)
        nskip = sum(1 for r in rows if r["ok"] == SKIP)
        print(f"共 {len(rows)} 项：通过 {npass} / 失败 {failed} / 跳过 {nskip}"
              + ("（跳过＝条件不成立，**不算通过**）" if nskip else ""))
        print("结论：", "🟢 跨轮遗留全部关闭" if allok else "🔴 出现跨轮回归，禁止发布")
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
