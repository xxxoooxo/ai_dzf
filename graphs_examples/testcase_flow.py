from __future__ import annotations

import json
import hashlib
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from file_rag.core.llms import get_default_model
from tools import build_pdf_message_updates, save_test_cases_to_excel


_MODEL = get_default_model()
_LOGGER = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PDF_EXTRACT_DIR = _REPO_ROOT / "storage" / "pdf_extracted"
_TESTCASE_OUTPUT_DIR = _REPO_ROOT / "storage" / "test_cases"

_DOC_ID_EXTRACT_RE = re.compile(r"\bDOC_ID\s*:\s*([0-9a-fA-F]{64})\b")
_DOC_ID_KV_RE = re.compile(r"\bdoc_id\s*=\s*([0-9a-fA-F]{64})\b", re.IGNORECASE)
_HEX64_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_MD_SEP_RE = re.compile(r"^:?-{3,}:?$")
_NUMBERED_HEADING_RE = re.compile(r"^(?:#+)\s+(\d+(?:\.\d+){1,6})\s+(.+?)\s*$")
_MD_ANY_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_SUBSECTION_HEADING_RE = re.compile(
    r"^(功能入口|入口|变更内容|配置变更|新增配置项|配置项|校验规则|规则|后端接口|接口|方法|流程|流程图|原型|交互|字段|备注|附录|参考)$"
)
_PATH_KV_RE = re.compile(r"(?:路径|功能入口|入口路径|页面入口|功能路径|导航路径|菜单路径)\s*[:：]\s*(.+)")
_ARROW_PATH_RE = re.compile(r"^[^|]{2,120}?\s*->\s*[^|]{2,120}?$")


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _extract_text_from_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            text = block.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text)
        return "\n".join(parts)
    return _stringify(content)


def _extract_all_text(messages: list[Any]) -> str:
    chunks: list[str] = []
    for msg in messages or []:
        chunks.append(_extract_text_from_content(getattr(msg, "content", None)))
    return "\n".join([c for c in chunks if c.strip()])


def _extract_doc_id_from_messages(messages: list[Any]) -> str | None:
    text = _extract_all_text(messages)
    m = _DOC_ID_EXTRACT_RE.search(text) or _DOC_ID_KV_RE.search(text)
    if m:
        return m.group(1).lower()
    return None


def _pick_latest_doc_id() -> str | None:
    base = _PDF_EXTRACT_DIR
    if not base.exists():
        return None

    best_doc_id: str | None = None
    best_ts: float = -1.0

    for child in base.iterdir():
        if not child.is_dir():
            continue
        name = child.name
        if not _HEX64_RE.fullmatch(name):
            continue
        candidates = [
            child / "answer.md",
            child / "notes.md",
            child / "chunks.jsonl",
            child / "meta.json",
            child / "analysis_state.json",
            child / "report_read_state.json",
        ]
        ts = -1.0
        for p in candidates:
            if p.exists():
                try:
                    ts = max(ts, p.stat().st_mtime)
                except Exception:
                    continue
        if ts > best_ts:
            best_ts = ts
            best_doc_id = name

    return best_doc_id


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _clamp_text(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return text
    t = text or ""
    if len(t) <= max_chars:
        return t
    head_len = int(max_chars * 0.6)
    tail_len = max_chars - head_len
    return (
        t[:head_len].rstrip()
        + "\n\n...(中间省略，已做截断以适配上下文长度)...\n\n"
        + t[-tail_len:].lstrip()
    )


def _load_prd_context(doc_id: str, *, max_chars: int = 70000) -> str:
    out_dir = _PDF_EXTRACT_DIR / doc_id
    notes_path = out_dir / "notes.md"
    answer_path = out_dir / "answer.md"

    text = ""
    if notes_path.exists():
        text = _read_text(notes_path)
    elif answer_path.exists():
        text = _read_text(answer_path)

    return _clamp_text(text, max_chars=max_chars)


def _load_prd_raw_text(doc_id: str, *, max_chars: int = 500000) -> str:
    """读取落盘的 notes/answer 原文（用于提取功能点/路径清单）。"""
    out_dir = _PDF_EXTRACT_DIR / doc_id
    candidates = [out_dir / "notes.md", out_dir / "answer.md"]
    for p in candidates:
        if not p.exists():
            continue
        text = _read_text(p)
        if max_chars > 0 and len(text) > max_chars:
            return text[:max_chars]
        return text
    return ""


def _load_prd_raw_text_from_chunks(doc_id: str, *, max_chars: int = 500000) -> str:
    """读取落盘 chunks.jsonl 拼接的原文（用于“尽量不漏”的功能点/路径/分支提取）。"""
    out_dir = _PDF_EXTRACT_DIR / doc_id
    chunks_path = out_dir / "chunks.jsonl"
    if not chunks_path.exists():
        return ""

    collected: list[str] = []
    total = 0
    try:
        with chunks_path.open("r", encoding="utf-8") as fp:
            for line in fp:
                if max_chars > 0 and total >= max_chars:
                    break
                raw = line.strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                except Exception:
                    continue
                if not isinstance(obj, dict):
                    continue
                content = obj.get("content")
                if not isinstance(content, str) or not content.strip():
                    continue
                remaining = max_chars - total if max_chars > 0 else None
                text = content if remaining is None else content[:remaining]
                if not text.strip():
                    continue
                collected.append(text)
                total += len(text)
    except Exception:
        return ""

    return "\n\n".join(collected).strip()


def _strip_inline_md(line: str) -> str:
    s = (line or "").strip()
    if not s:
        return ""
    # 去掉常见 markdown 内联标记，便于做路径/变更提取
    s = s.replace("**", "").replace("`", "")
    s = re.sub(r"^[\-\*\s]+", "", s)
    return s.strip()


def _clean_path(path: str) -> str:
    p = _strip_inline_md(path)
    if not p:
        return ""
    p = re.sub(r"\s*->\s*", " -> ", p)
    p = re.sub(r"\s+", " ", p).strip()
    return p


def _normalize_for_match(text: str) -> str:
    """用于覆盖校验的归一化：去空白与 markdown 标记，避免格式差异导致误判。"""
    t = (text or "").strip()
    if not t:
        return ""
    t = t.replace("**", "").replace("`", "")
    return re.sub(r"\s+", "", t)


def _is_feature_heading(title: str, *, level: int) -> bool:
    t = (title or "").strip()
    if not t:
        return False
    if t.startswith("分片"):
        return False
    if _SUBSECTION_HEADING_RE.fullmatch(t):
        return False
    # 经验：在 notes.md 中，feature 通常是 ###；#### 多为“功能入口/变更内容”等子标题。
    # 需要兼容 answer.md 中的“#### 1.3.1 XXX”场景（已由 _NUMBERED_HEADING_RE 单独处理）。
    if level not in (2, 3):
        return False
    return True


def _normalize_heading_title(title: str) -> str:
    t = (title or "").strip().strip("：:;；。")
    if not t:
        return ""
    t = re.sub(r"^\d+(?:\.\d+){1,6}\s+", "", t).strip()
    return t.strip()


def _extract_branch_catalog(prd_text: str) -> list[str]:
    """提取流程图/状态机的“分支清单”（用于确定性覆盖门禁）。"""
    if not isinstance(prd_text, str) or not prd_text.strip():
        return []

    branches: list[str] = []
    seen: set[str] = set()

    for raw in prd_text.splitlines():
        clean = _strip_inline_md(raw)
        if not clean:
            continue
        line = clean.replace("→", "->").replace("—>", "->").strip()
        if "->" not in line:
            continue
        # 兼容多种“分支描述”形式：
        # - A -> B（条件/事件：...）
        # - A -> B (条件: ...)
        # - A -> B 条件：...
        hint = (
            re.search(r"[（(].*?(条件|事件|否则|成功|失败|是|否|判断|分支|回路|终止).*?[)）]", line)
            or re.search(r"(条件|事件|否则|成功|失败|判断|分支|回路|终止)\s*[:：]", line)
        )
        if not hint:
            continue

        line = line.rstrip("。;；")
        norm = _normalize_for_match(line)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        branches.append(line)

    return branches


def _extract_feature_catalog(prd_text: str) -> list[dict[str, Any]]:
    """从 PRD（notes/answer）中提取“功能点 + 入口路径 + 变更要点”。

    目标：把 PRD 的所有入口路径完整抽取出来，用于强制覆盖与确定性门禁。
    """
    if not isinstance(prd_text, str) or not prd_text.strip():
        return []

    items: list[dict[str, Any]] = []

    current_feature: str | None = None
    feature_buf: dict[str, dict[str, Any]] = {}

    def ensure_feature(title: str) -> dict[str, Any]:
        nonlocal feature_buf
        t = title.strip()
        if t not in feature_buf:
            feature_buf[t] = {"feature": t, "paths": [], "changes": [], "rules": []}
        return feature_buf[t]

    for raw in prd_text.splitlines():
        line = raw.rstrip()
        m_heading = _MD_ANY_HEADING_RE.match(line.strip())
        if m_heading:
            level = len(m_heading.group(1))
            title_raw = m_heading.group(2).strip()
            title = _normalize_heading_title(title_raw)

            if title.startswith("分片"):
                current_feature = None
                continue

            m_num = _NUMBERED_HEADING_RE.match(line.strip())
            if m_num:
                title = m_num.group(2).strip()
                if title:
                    current_feature = title
                    ensure_feature(title)
                continue

            if _is_feature_heading(title, level=level):
                current_feature = title
                ensure_feature(title)
            continue

        clean = _strip_inline_md(line)
        if not clean:
            continue

        # 入口路径（优先，支持多种格式，不强制 ->）
        m_path = _PATH_KV_RE.search(clean)
        if m_path:
            p = _clean_path(m_path.group(1))
            if p:
                feature = current_feature or ""
                if feature:
                    ensure_feature(feature)["paths"].append(p)
                else:
                    items.append({"feature": "", "path": p, "changes": [], "rules": []})
            continue

        # 入口路径兜底：多级“->”更像导航路径而不是文案变更（例如：首页 -> 活动 -> 大转盘）
        if "->" in clean and clean.count("->") >= 2 and _ARROW_PATH_RE.fullmatch(clean):
            p = _clean_path(clean)
            if p:
                feature = current_feature or ""
                if feature:
                    ensure_feature(feature)["paths"].append(p)
                else:
                    items.append({"feature": "", "path": p, "changes": [], "rules": []})
            continue

        # 变更文案/字段：A -> B（仅在已识别 feature 语境下记录）
        if current_feature and "->" in clean:
            left, right = [c.strip(" ：:;；。") for c in clean.split("->", 1)]
            if left and right:
                ensure_feature(current_feature)["changes"].append((left, right))
            continue

        # 规则/提示/校验类要点（仅在已识别 feature 语境下记录）
        if current_feature and re.search(r"(规则|限制|失败提示|提示|校验|新增|奖品类型|接口|方法)", clean):
            ensure_feature(current_feature)["rules"].append(clean)

    # 汇总：每个 feature + 每个 path 形成条目；无 path 但有证据（变更/规则）也保留（用于覆盖门禁）
    for feat, obj in feature_buf.items():
        paths = [str(p).strip() for p in obj.get("paths") or [] if str(p).strip()]
        changes = obj.get("changes") or []
        rules = obj.get("rules") or []
        if not paths:
            if changes or rules:
                items.append({"feature": feat, "path": "", "changes": changes, "rules": rules})
            continue
        for p in paths:
            items.append({"feature": feat, "path": p, "changes": changes, "rules": rules})

    # 二次兜底：若未提取到任何路径，则全局扫描所有“路径/功能入口”行
    if not items:
        for raw in prd_text.splitlines():
            clean = _strip_inline_md(raw)
            if not clean:
                continue
            m_path = _PATH_KV_RE.search(clean)
            if not m_path:
                continue
            p = _clean_path(m_path.group(1))
            if not p:
                continue
            items.append({"feature": "", "path": p, "changes": [], "rules": []})

    # 去重：优先按 path 去重（覆盖门禁也按 path），并合并规则/变更信息
    dedup: dict[str, dict[str, Any]] = {}
    for it in items:
        feature = str(it.get("feature") or "").strip()
        path = str(it.get("path") or "").strip()
        key = _normalize_for_match(path) if path else f"FEATURE::{_normalize_for_match(feature)}"
        if not key or key == "FEATURE::":
            continue

        if key not in dedup:
            dedup[key] = {
                "feature": feature,
                "path": path,
                "changes": list(it.get("changes") or []),
                "rules": list(it.get("rules") or []),
            }
            continue

        # 合并：feature 选更长/更具体的；changes/rules 做去重追加
        existing = dedup[key]
        if feature and (not existing.get("feature") or len(feature) > len(str(existing.get("feature") or ""))):
            existing["feature"] = feature
        if path and not existing.get("path"):
            existing["path"] = path

        ch_set = {(str(a).strip(), str(b).strip()) for a, b in (existing.get("changes") or []) if str(a).strip() and str(b).strip()}
        for pair in it.get("changes") or []:
            try:
                a, b = pair
            except Exception:
                continue
            a_s, b_s = str(a).strip(), str(b).strip()
            if not a_s or not b_s:
                continue
            if (a_s, b_s) in ch_set:
                continue
            ch_set.add((a_s, b_s))
            existing.setdefault("changes", []).append((a_s, b_s))

        rule_set = {str(r).strip() for r in (existing.get("rules") or []) if str(r).strip()}
        for r in it.get("rules") or []:
            r_s = str(r).strip()
            if not r_s or r_s in rule_set:
                continue
            rule_set.add(r_s)
            existing.setdefault("rules", []).append(r_s)

    return list(dedup.values())


def _missing_catalog_items(
    cases: list[dict[str, str]],
    catalog: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not catalog:
        return []

    normalized_rows = [_normalize_for_match(_case_text(c)) for c in cases]
    missing: list[dict[str, Any]] = []

    for item in catalog:
        path = str(item.get("path") or "").strip()
        feature = str(item.get("feature") or "").strip()
        token = path or feature
        norm = _normalize_for_match(token)
        if not norm:
            continue
        if any(norm in row for row in normalized_rows):
            continue
        missing.append(item)

    return missing


_AUTO_CASE_ID_RE = re.compile(r"^TC-AUTO-(\d{3})$")


def _next_auto_case_seq(existing_case_ids: set[str]) -> int:
    best = 0
    for cid in existing_case_ids:
        m = _AUTO_CASE_ID_RE.match(cid.strip())
        if not m:
            continue
        try:
            best = max(best, int(m.group(1)))
        except Exception:
            continue
    return best + 1


def _feature_short_name(feature: str) -> str:
    name = (feature or "").strip()
    if "（" in name:
        name = name.split("（", 1)[0].strip()
    return name or (feature or "").strip() or "功能点"


def _guess_platform_by_path(path: str) -> str:
    p = path or ""
    if "CMS" in p:
        return "后台管理"
    if "小程序" in p:
        return "小程序前端"
    return ""


def _extract_quote(text: str) -> str | None:
    for pat in (r"toast提示“([^”]+)”", r"提示“([^”]+)”", r"toast提示\"([^\"]+)\"", r"提示\"([^\"]+)\""):
        m = re.search(pat, text)
        if m:
            return m.group(1).strip()
    return None


def _generate_auto_cases(
    missing_items: list[dict[str, Any]],
    *,
    existing_case_ids: set[str],
) -> list[dict[str, str]]:
    """对缺失的功能点/路径做“确定性补齐”，保证 Excel 里不再漏功能入口。"""
    seq = _next_auto_case_seq(existing_case_ids)
    out: list[dict[str, str]] = []

    for item in missing_items:
        feature = str(item.get("feature") or "").strip()
        path = str(item.get("path") or "").strip()
        changes = item.get("changes") or []
        rules = item.get("rules") or []

        module = _feature_short_name(feature)
        platform = _guess_platform_by_path(path)
        hint_text = "\n".join(
            [
                feature,
                path,
                "\n".join([f"{a} -> {b}" for a, b in (changes or []) if str(a).strip() and str(b).strip()][:5]),
                "\n".join([str(r).strip() for r in (rules or []) if str(r).strip()][:8]),
            ]
        )
        is_modal = bool(re.search(r"(弹窗|对话框|popup|modal)", hint_text, re.IGNORECASE))

        # Case 1: 入口可达
        cid1 = f"TC-AUTO-{seq:03d}"
        seq += 1
        existing_case_ids.add(cid1)

        pre1 = "已具备访问权限"
        if platform == "后台管理":
            pre1 = "已登录 CMS，且账号具备对应菜单权限"
        elif platform == "小程序前端":
            pre1 = "已登录拼拼小程序，且网络正常"

        if is_modal:
            steps1 = (
                f"1. 按路径进入：{path or feature}\n"
                "2. 按 PRD/原型描述的操作触发弹窗/对话框\n"
                "3. 校验弹窗标题/字段/按钮/提示文案，并验证关闭/取消/确认行为可用"
            )
            exp1 = (
                "弹窗可正常展示且可关闭：标题、字段列表、按钮（确认/取消/关闭）与提示文案符合 PRD/原型；"
                f"入口路径可达：{path or feature}"
            )
        else:
            steps1 = (
                f"1. 按路径进入：{path or feature}\n"
                "2. 页面加载完成\n"
                "3. 校验页面关键区域/按钮/文案可见且可交互"
            )
            exp1 = f"页面可正常打开，无报错；入口路径可达：{path or feature}"

        out.append(
            {
                "用例ID": cid1,
                "模块": module,
                "需求点": f"{platform + ' - ' if platform else ''}入口可达",
                "前置条件": pre1,
                "测试步骤": steps1,
                "预期结果": exp1,
                "优先级": "P0",
                "测试类型": "功能测试",
                "关联内容": f"路径：{path or '无'}\n功能点：{feature or module}",
            }
        )

        # Case 2: 关键变更/规则校验（尽量用 PRD 原文要点，不写“展示即可”）
        cid2 = f"TC-AUTO-{seq:03d}"
        seq += 1
        existing_case_ids.add(cid2)

        change_lines: list[str] = []
        for ch in changes[:3]:
            try:
                old, new = ch
                change_lines.append(f"{old} -> {new}")
            except Exception:
                continue

        rule_lines = [str(r).strip() for r in rules[:4] if str(r).strip()]

        focus = ""
        expected_detail = []
        if change_lines:
            focus = "文案/字段变更校验"
            expected_detail.append("变更项：\n- " + "\n- ".join(change_lines))
            for old_new in change_lines:
                parts = old_new.split("->", 1)
                if len(parts) == 2:
                    expected_detail.append(f"页面中应出现：{parts[1].strip()}；且不应出现旧文案：{parts[0].strip()}")
        elif rule_lines:
            focus = "规则/提示校验"
            msg = _extract_quote("\n".join(rule_lines))
            if msg:
                expected_detail.append(f"触发校验失败时提示文案：{msg}")
            expected_detail.append("相关规则要点：\n- " + "\n- ".join(rule_lines))
        else:
            focus = "关键字段与交互校验"
            expected_detail.append("校验页面关键字段/按钮/文案展示与交互可用（以 PRD/原型为准）。")

        steps2 = f"1. 进入功能入口：{path or feature}\n2. 按 PRD 描述触发关键场景（配置/领取/兑换/提交等）\n3. 观察页面字段/文案/提示/规则表现"
        exp2 = "\n".join(expected_detail) if expected_detail else "按 PRD/原型要求展示正确"
        rel2_parts = [f"路径：{path or '无'}", f"功能点：{feature or module}"]
        if change_lines:
            rel2_parts.append("变更原文：\n- " + "\n- ".join(change_lines))
        if rule_lines:
            rel2_parts.append("规则原文：\n- " + "\n- ".join(rule_lines[:3]))

        out.append(
            {
                "用例ID": cid2,
                "模块": module,
                "需求点": f"{platform + ' - ' if platform else ''}{focus}",
                "前置条件": pre1,
                "测试步骤": steps2,
                "预期结果": exp2,
                "优先级": "P0",
                "测试类型": "功能测试",
                "关联内容": "\n".join(rel2_parts).strip(),
            }
        )

    return out


def _last_user_text(messages: list[Any]) -> str:
    for msg in reversed(messages or []):
        if msg.__class__.__name__ == "HumanMessage":
            return _extract_text_from_content(getattr(msg, "content", None))
    return _extract_all_text(messages[-1:]) if messages else ""


def _extract_markdown_table_block(text: str) -> str:
    """抽取包含“用例ID/测试用例ID”的 Markdown 表格块（连续的 | 行）。"""
    if not isinstance(text, str) or not text.strip():
        return ""

    lines = [ln.rstrip() for ln in text.splitlines()]
    start = -1
    for i, ln in enumerate(lines):
        s = ln.strip()
        if not s.startswith("|"):
            continue
        if "用例ID" in s or "测试用例ID" in s:
            start = i
            break
    if start < 0:
        return ""

    table_lines: list[str] = []
    for ln in lines[start:]:
        s = ln.strip()
        if not s.startswith("|"):
            break
        table_lines.append(s)
    return "\n".join(table_lines).strip()


def _strip_md(text: str) -> str:
    s = (text or "").strip()
    if s.startswith("**") and s.endswith("**") and len(s) >= 4:
        s = s[2:-2].strip()
    return s


def _split_md_row(line: str) -> list[str]:
    # 去掉首尾管道符，再按 | 分割
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    return [_strip_md(c) for c in cells]


def _is_separator_row(cells: list[str]) -> bool:
    if not cells:
        return False
    return all((not c) or _MD_SEP_RE.fullmatch(c.replace(" ", "")) for c in cells)


def _normalize_headers(headers: list[str]) -> list[str]:
    mapping = {
        "测试用例ID": "用例ID",
        "用例编号": "用例ID",
        "模块/功能": "模块",
        "功能模块": "模块",
        "需求点": "需求点",
        "关联需求": "需求点",
        "前置条件": "前置条件",
        "测试步骤": "测试步骤",
        "步骤": "测试步骤",
        "预期结果": "预期结果",
        "期望结果": "预期结果",
        "优先级": "优先级",
        "测试类型": "测试类型",
        "用例类型": "测试类型",
        "关联内容": "关联内容",
        "需求引用": "关联内容",
        "原文引用": "关联内容",
    }
    out: list[str] = []
    for h in headers:
        key = h.strip()
        out.append(mapping.get(key, key))
    return out


def _parse_test_cases_from_markdown(text: str) -> list[dict[str, str]]:
    table = _extract_markdown_table_block(text)
    if not table:
        return []

    lines = [ln.strip() for ln in table.splitlines() if ln.strip()]
    if len(lines) < 2:
        return []

    raw_headers = _split_md_row(lines[0])
    headers = _normalize_headers(raw_headers)

    rows: list[dict[str, str]] = []
    for ln in lines[1:]:
        cells = _split_md_row(ln)
        if _is_separator_row(cells):
            continue
        if not any(cells):
            continue

        # 对齐列数（允许模型少/多输出一两列，尽量不崩）
        if len(cells) < len(headers):
            cells = cells + [""] * (len(headers) - len(cells))
        if len(cells) > len(headers):
            cells = cells[: len(headers)]

        row = {h: c.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n").strip() for h, c in zip(headers, cells)}
        case_id = row.get("用例ID", "").strip()
        if not case_id:
            continue
        if not case_id.startswith("TC-"):
            # 避免把“章节标题/小标题行”误当成用例写入 Excel
            continue
        rows.append(row)

    return rows


_GENERIC_EXPECTED_RE = re.compile(
    r"(展示弹窗|弹窗展示|正常展示|显示成功|提示成功|提示失败|操作成功|操作失败|校验通过|校验失败|跳转成功)",
    re.IGNORECASE,
)
_MODAL_RE = re.compile(r"(弹窗|对话框|弹出|popup|modal)", re.IGNORECASE)
_UI_DETAIL_HINT_RE = re.compile(
    r"(标题|按钮|字段|表格|列表|文案|提示|错误码|关闭|取消|确认|金额|合计|明细|小数|格式|单位|币种)",
    re.IGNORECASE,
)
_AMOUNT_TOTAL_RE = re.compile(r"(总和|合计|汇总)", re.IGNORECASE)
_AMOUNT_SPLIT_RE = re.compile(r"(分开|分项|明细|逐项)", re.IGNORECASE)


def _case_text(row: dict[str, str]) -> str:
    return "\n".join(
        [
            row.get("用例ID", ""),
            row.get("模块", ""),
            row.get("需求点", ""),
            row.get("前置条件", ""),
            row.get("测试步骤", ""),
            row.get("预期结果", ""),
            row.get("优先级", ""),
            row.get("测试类型", ""),
            row.get("关联内容", ""),
        ]
    )


def _detect_amount_display_variants(prd_context: str) -> bool:
    """识别“金额总和/分开展示”这类配置导致的 UI 差异。命中则必须拆分用例覆盖。"""
    text = prd_context or ""
    if not text.strip():
        return False
    if not re.search(r"(金额|合计|明细)", text):
        return False
    if not re.search(r"(展示|显示|呈现|弹窗)", text):
        return False
    return bool(_AMOUNT_TOTAL_RE.search(text) and _AMOUNT_SPLIT_RE.search(text))


def _quality_gate(
    cases: list[dict[str, str]],
    *,
    prd_context: str,
    feature_catalog: list[dict[str, Any]] | None = None,
    branch_catalog: list[str] | None = None,
) -> tuple[bool, list[str], list[str]]:
    """对“可执行性/可验证性”做门禁，避免出现“展示弹窗就结束”的泛化用例。"""
    problems: list[str] = []
    add_suggestions: list[str] = []

    if not cases:
        problems.append("未解析到可评审的用例表：请严格输出 1 张 Markdown 表格且表头字段完整。")
        return False, problems, add_suggestions

    # 1) 每条用例必须具备“关联内容”（避免空泛）
    missing_refs = [c.get("用例ID", "").strip() for c in cases if not (c.get("关联内容") or "").strip()]
    if missing_refs:
        problems.append(f"以下用例缺少【关联内容】（无法追溯到 PRD）：{', '.join(missing_refs)}")

    # 2) 预期结果不可泛化（必须可验证）
    for c in cases:
        cid = (c.get("用例ID") or "").strip() or "UNKNOWN"
        steps = (c.get("测试步骤") or "").strip()
        expected = (c.get("预期结果") or "").strip()

        if len(steps) < 15:
            problems.append(f"{cid}：测试步骤过短，无法执行（至少包含关键操作与触发条件）。")

        if len(expected) < 20:
            problems.append(f"{cid}：预期结果过短，无法验证（必须写明字段/文案/布局/规则）。")

        if _GENERIC_EXPECTED_RE.search(expected) and not _UI_DETAIL_HINT_RE.search(expected):
            problems.append(f"{cid}：预期结果泛化（仅“成功/失败/展示”），缺少字段/文案/规则细节。")

        # 弹窗类：必须验证“弹窗长什么样/包含什么字段/按钮/文案”
        if _MODAL_RE.search(steps + "\n" + expected) and not _UI_DETAIL_HINT_RE.search(expected):
            problems.append(f"{cid}：涉及弹窗但未验证弹窗内容（标题/字段/按钮/提示文案/金额展示规则等）。")

    # 3) 配置差异导致 UI 不同：必须拆分用例覆盖
    if _detect_amount_display_variants(prd_context):
        has_total = any(_AMOUNT_TOTAL_RE.search(_case_text(c) or "") for c in cases)
        has_split = any(_AMOUNT_SPLIT_RE.search(_case_text(c) or "") for c in cases)
        if not (has_total and has_split):
            add_suggestions.append("【覆盖补齐】检测到金额展示存在“总和/分开展示”差异，但用例未分别覆盖两种模式（写入节点将自动补齐基线用例）。")
            add_suggestions.append("新增：后台配置金额展示模式=总和展示时，弹窗/页面字段与布局（合计行/汇总区）校验。")
            add_suggestions.append("新增：后台配置金额展示模式=分开展示时，弹窗/页面字段与布局（分项明细/逐项金额）校验。")

        has_config_precond = any(
            re.search(r"(后台|配置|展示模式|开关|枚举)", (c.get("前置条件") or ""))
            for c in cases
        )
        if not has_config_precond:
            add_suggestions.append("【可复现性】存在配置差异但前置条件未写清后台配置值（写入节点将自动补齐基线用例，但建议补齐真实配置入口与枚举值）。")

    # 4) PRD 功能点/路径必须全覆盖（优先按“入口路径”做确定性校验）
    catalog = feature_catalog or []
    missing = _missing_catalog_items(cases, catalog)
    if missing:
        preview = missing[:20]
        preview_text = "；".join(
            [
                f"{it.get('feature') or '未知功能'}（路径：{it.get('path') or '无'}）"
                for it in preview
            ]
        )
        suffix = "..." if len(missing) > len(preview) else ""
        add_suggestions.append(
            f"【覆盖补齐】PRD 功能点/入口路径未全覆盖：缺少 {len(missing)} 个（示例：{preview_text}{suffix}；写入节点将自动补齐基线用例）。"
        )
        for it in preview:
            path = str(it.get("path") or "").strip()
            feature = str(it.get("feature") or "").strip()
            if path:
                add_suggestions.append(f"新增：覆盖功能点“{feature}”，并在关联内容写入路径原文：{path}")
            else:
                add_suggestions.append(f"新增：覆盖功能点“{feature}”（未解析到路径，至少补齐入口/主流程/异常）")

    # 5) 流程图/状态机分支清单必须覆盖（每个分支至少 1 条用例）
    branches = [b.strip() for b in (branch_catalog or []) if b and b.strip()]
    if branches:
        normalized_rows = [_normalize_for_match(_case_text(c)) for c in cases]
        missing_branches: list[str] = []
        for br in branches:
            norm = _normalize_for_match(br)
            if not norm:
                continue
            if any(norm in row for row in normalized_rows):
                continue
            missing_branches.append(br)

        if missing_branches:
            preview = missing_branches[:20]
            preview_text = "；".join(preview)
            suffix = "..." if len(missing_branches) > len(preview) else ""
            add_suggestions.append(
                f"【覆盖补齐】流程/分支清单未全覆盖：缺少 {len(missing_branches)} 个分支（示例：{preview_text}{suffix}；写入节点将自动补齐基线用例）。"
            )
            for br in preview:
                add_suggestions.append(f"新增：覆盖流程分支，并在关联内容写入分支原文：{br}")

    ok = not problems
    return ok, problems, add_suggestions


def preprocess_pdf_node(state: dict[str, Any]) -> dict[str, Any]:
    """把 messages 里的 PDF/图片块更新为纯文本（落盘 + 注入 DOC_ID）。"""
    # 测试用例工作流必须“尽量不漏”：强制开启图片/流程图多模态解析，把图片内容转成可追溯文本。
    updated_messages = build_pdf_message_updates(state.get("messages", []), force_image_vision=True)
    _LOGGER.info("testcase_flow.preprocess_pdf: updated_messages=%s", len(updated_messages))
    return {"messages": updated_messages} if updated_messages else {}


def prepare_case_context_node(state: dict[str, Any]) -> dict[str, Any]:
    """提取 DOC_ID，加载已落盘的 notes/answer 作为用例生成上下文。"""
    messages = state.get("messages", [])
    doc_id = _extract_doc_id_from_messages(messages) or _pick_latest_doc_id()

    context = ""
    raw_prd_text = ""
    if doc_id:
        out_dir = _PDF_EXTRACT_DIR / doc_id
        notes_text = _read_text(out_dir / "notes.md") if (out_dir / "notes.md").exists() else ""
        answer_text = _read_text(out_dir / "answer.md") if (out_dir / "answer.md").exists() else ""
        chunks_text = _load_prd_raw_text_from_chunks(doc_id, max_chars=500000)

        if notes_text.strip():
            context = _clamp_text(notes_text, max_chars=70000)
        elif answer_text.strip():
            context = _clamp_text(answer_text, max_chars=70000)
        else:
            # 兜底：如果 notes/answer 不存在，用 chunks.jsonl 拼接的原文做上下文
            context = _clamp_text(chunks_text, max_chars=70000)

        # raw_prd_text：优先 notes + answer；缺失时用 chunks.jsonl（尽量不漏）
        raw_parts = [t for t in (notes_text, answer_text, chunks_text) if t.strip()]
        if raw_parts:
            raw_prd_text = "\n\n".join(raw_parts).strip()
        else:
            raw_prd_text = ""

    if not context.strip():
        # 兜底：直接用对话文本（例如用户粘贴 PRD 文本）
        context = _clamp_text(_extract_all_text(messages), max_chars=70000)
        raw_prd_text = context

    prd_hash = doc_id or hashlib.md5(context.encode("utf-8")).hexdigest()
    feature_catalog = _extract_feature_catalog(raw_prd_text)
    branch_catalog = _extract_branch_catalog(raw_prd_text)
    return {
        "doc_id": doc_id or "",
        "prd_hash": prd_hash,
        "prd_context": context,
        "feature_catalog": feature_catalog,
        "branch_catalog": branch_catalog,
        "review_count": 0,
    }


def write_case_node(state: dict[str, Any]) -> dict[str, Any]:
    """测试用例生成节点：强制与 PRD 上下文做关联，输出 Markdown 表格。"""
    doc_id = (state.get("doc_id") or "").strip()
    prd_context = (state.get("prd_context") or "").strip()
    feature_catalog = state.get("feature_catalog") or []
    branch_catalog = state.get("branch_catalog") or []
    question = _last_user_text(state.get("messages", []))

    variant_tips: list[str] = []
    if _detect_amount_display_variants(prd_context):
        variant_tips.append(
            "已识别“金额展示模式”存在【总和展示】与【分开展示】两种 UI 差异：\n"
            "- 必须拆成两组用例（每种模式至少 1 条），并在【前置条件】写清后台配置值（例如：金额展示模式=总和展示 / 分开展示）。\n"
            "- 两种模式的【预期结果】必须分别校验 UI 布局与字段展示差异（不能复用“展示弹窗”这种泛化描述）。"
        )

    variant_tip_text = "\n\n".join(variant_tips).strip()
    if variant_tip_text:
        variant_tip_text = "\n\n差异点强制覆盖：\n" + variant_tip_text + "\n"

    catalog_lines: list[str] = []
    for it in feature_catalog:
        feature = str(it.get("feature") or "").strip()
        path = str(it.get("path") or "").strip()
        if not feature and not path:
            continue
        if path:
            catalog_lines.append(f"- {feature or '未命名功能'}（路径：{path}）")
        else:
            catalog_lines.append(f"- {feature}")

    catalog_text = "\n".join(catalog_lines).strip()
    catalog_block = ""
    if catalog_text:
        catalog_block = (
            "\n\nPRD 功能点与入口路径清单（必须 100% 覆盖）：\n"
            f"{catalog_text}\n"
            "\n覆盖规则（硬性要求）：\n"
            "1) 清单里每一条“路径”至少覆盖 1 条用例；若同一功能存在 CMS/小程序等多个入口路径，必须分别覆盖。\n"
            "2) 每条用例的【关联内容】必须包含对应功能点的“路径”原文（用于可追溯与覆盖校验）。\n"
        )

    branch_lines = [b.strip() for b in branch_catalog if isinstance(b, str) and b.strip()]
    branch_text = "\n".join([f"- {b}" for b in branch_lines]).strip()
    branch_block = ""
    if branch_text:
        branch_block = (
            "\n\n流程/分支清单（必须 100% 覆盖）：\n"
            f"{branch_text}\n"
            "\n覆盖规则（硬性要求）：\n"
            "1) 清单里每一条分支至少覆盖 1 条用例，并在【需求点】写清触发条件。\n"
            "2) 每条分支对应的用例【关联内容】必须原样摘录该分支行（用于覆盖校验）。\n"
        )

    system = SystemMessage(
        content=(
            "你是资深测试工程师，目标是基于 PRD/需求文档生成【可直接执行】的测试用例，并能直接落 Excel。\n"
            "硬性要求：\n"
            "1) 用例必须与上下文强关联：每条用例的【关联内容】列必须摘录 PRD 中出现的页面/字段/规则关键词（原样摘录），禁止空泛。\n"
            "2) 覆盖主流程 + 异常/边界 + 权限/角色（如有）+ 数据校验（如有）+ 幂等/重复提交（如有）。\n"
            "   - 若上下文包含流程图/状态机/决策节点（例如菱形判断、条件分支、回路）：必须覆盖每个分支路径（每个分支至少 1 条用例），并在【需求点】中写清分支条件。\n"
            "3) 弹窗/对话框类用例：预期结果必须写清【弹窗标题、字段列表（含金额单位/格式/小数位）、按钮（确认/取消/关闭）与提示文案】；"
            "若同一弹窗存在多种展示样式（由后台配置/开关/模式决定），必须拆分用例分别覆盖。\n"
            "4) 禁止写无效预期：例如“展示弹窗/正常展示/操作成功/提示错误”而没有任何字段/文案/布局/规则细节。\n"
            "5) 无论用户问题是否只关注某个局部点：只要进入“测试用例工作流”，就必须覆盖 PRD 的【全部功能点与入口路径】。\n"
            "6) 步骤与预期必须可操作、可验证，避免“正常/成功/失败”这种泛化描述。\n"
            "7) 如果 PRD 缺少关键信息，先输出“待确认问题”列表（按优先级排序），再输出用例表。\n"
            f"{variant_tip_text}"
            f"{catalog_block}"
            f"{branch_block}"
            "\n"
            "输出格式（必须严格遵守）：\n"
            "A) 待确认问题（如无则写“无”）\n"
            "B) Markdown 表格（仅 1 张表）：\n"
            "| 用例ID | 模块 | 需求点 | 前置条件 | 测试步骤 | 预期结果 | 优先级 | 测试类型 | 关联内容 |\n"
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
            "约束：\n"
            "- 用例ID 统一格式：TC-<模块缩写>-<3位数字>，例如 TC-LOGIN-001。\n"
            "- 表格中【每一行】都必须是用例行：用例ID 必须以 TC- 开头；不要在表格中插入“章节标题/小标题”行。\n"
            "- 单元格内换行用 <br>，不要在任何单元格里使用竖线“|”。\n"
        )
    )

    user = HumanMessage(
        content=(
            f"用户目标/问题：\n{question}\n\n"
            f"DOC_ID：{doc_id or '无'}\n\n"
            "PRD 上下文（累计笔记/正文节选）：\n"
            "```text\n"
            f"{prd_context}\n"
            "```"
        )
    )

    result = _MODEL.invoke([system, user])
    return {"messages": [result]}


def review_case_node(state: dict[str, Any]) -> dict[str, Any]:
    """测试用例评审节点：给出通过/不通过结论与改进建议。"""
    _LOGGER.info(
        "testcase_flow.review_case: round=%s doc_id=%s",
        int(state.get("review_count", 0) or 0) + 1,
        (state.get("doc_id") or "").strip(),
    )
    messages = state.get("messages", [])
    prd_context = (state.get("prd_context") or "").strip()
    feature_catalog = state.get("feature_catalog") or []
    branch_catalog = state.get("branch_catalog") or []
    # 优先评审最近一次生成的用例表
    latest_table = ""
    for msg in reversed(messages or []):
        text = _extract_text_from_content(getattr(msg, "content", None))
        block = _extract_markdown_table_block(text)
        if block:
            latest_table = block
            break

    cases = _parse_test_cases_from_markdown(latest_table)
    ok, problems, add_suggestions = _quality_gate(
        cases,
        prd_context=prd_context,
        feature_catalog=feature_catalog,
        branch_catalog=branch_catalog,
    )
    _LOGGER.info("testcase_flow.review_case.gate: ok=%s problems=%s", ok, len(problems))
    if not ok:
        problems_text = "\n".join([f"  {i}) {p}" for i, p in enumerate(problems, start=1)]) or "  1) 无"
        add_text = "\n".join([f"  - {s}" for s in add_suggestions]) or "  - 无"
        review_msg = (
            "- 评审结论：不通过\n"
            "- 主要问题：\n"
            f"{problems_text}\n"
            "- 漏测建议（新增用例清单）：\n"
            f"{add_text}\n"
            "- 修改建议：\n"
            "  - 对所有“弹窗/对话框”类场景：预期结果必须写清【弹窗标题、字段列表、金额展示规则（合计/明细）、按钮（确认/取消/关闭）与提示文案】。\n"
            "  - 对所有“配置/开关/模式”类差异：必须按不同配置值拆分用例，前置条件写清后台配置值，并分别校验 UI 布局与字段展示。\n"
            "  - 禁止出现“展示弹窗/正常展示/操作成功”这类不可验证的预期结果。\n"
        )
        return {
            "messages": [AIMessage(content=review_msg)],
            "review_count": int(state.get("review_count", 0) or 0) + 1,
        }

    add_text = "\n".join([f"  - {s}" for s in add_suggestions]) or "  - 无"
    review_msg = (
        "- 评审结论：通过\n"
        "- 主要问题：\n"
        "  1) 无\n"
        "- 漏测建议（新增用例清单）：\n"
        f"{add_text}\n"
        "- 修改建议：\n"
        "  - 若写入节点自动补齐生成了 TC-AUTO-* 用例：建议后续按原型/接口/字段/文案把预期结果进一步细化。\n"
    )
    return {
        "messages": [AIMessage(content=review_msg)],
        "review_count": int(state.get("review_count", 0) or 0) + 1,
    }


def revise_case_node(state: dict[str, Any]) -> dict[str, Any]:
    """根据评审意见修订用例表（保持同样表头）。"""
    messages = state.get("messages", [])
    prd_context = (state.get("prd_context") or "").strip()

    review_text = _extract_text_from_content(getattr(messages[-1], "content", None)) if messages else ""

    latest_table = ""
    for msg in reversed(messages or []):
        text = _extract_text_from_content(getattr(msg, "content", None))
        block = _extract_markdown_table_block(text)
        if block:
            latest_table = block
            break

    system = SystemMessage(
        content=(
            "你是测试用例作者，请根据“评审意见”与“PRD上下文”对用例表进行修订。\n"
            "要求：\n"
            "1) 输出【完整】修订后的表格（不要只输出差异）。\n"
            "2) 保留已存在且无问题的用例ID；新增用例按模块继续编号。\n"
            "3) 用例必须与 PRD 强关联：每条用例的【关联内容】列必须摘录 PRD 中出现的具体词/规则。\n"
            "4) 必须把评审中的“漏测建议（新增用例清单）”全部落实为表格行（覆盖对应分支/异常/边界）。\n"
            "5) 对弹窗/对话框类场景：预期结果必须补齐【标题、字段/文案、金额展示规则、按钮与关闭行为】。\n"
            "6) 最终只输出：待确认问题 + 用例表（不要输出额外解释）。\n"
            "\n"
            "表头固定为：\n"
            "| 用例ID | 模块 | 需求点 | 前置条件 | 测试步骤 | 预期结果 | 优先级 | 测试类型 | 关联内容 |\n"
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
            "单元格内换行用 <br>，不要在任何单元格里使用竖线“|”。\n"
        )
    )
    user = HumanMessage(
        content=(
            "评审意见：\n"
            "```text\n"
            f"{review_text}\n"
            "```\n\n"
            "当前用例表：\n"
            "```markdown\n"
            f"{latest_table}\n"
            "```\n\n"
            "PRD 上下文（节选）：\n"
            "```text\n"
            f"{_clamp_text(prd_context, max_chars=50000)}\n"
            "```"
        )
    )
    result = _MODEL.invoke([system, user])
    return {"messages": [result]}


def condition_edge(state: dict[str, Any]) -> str:
    """评审结果路由：通过 -> 写入Excel；不通过 -> 迭代修订（最多四轮后强制落盘）。"""
    review_count = int(state.get("review_count", 0) or 0)
    last = state.get("messages", [])[-1] if state.get("messages") else None
    content = _extract_text_from_content(getattr(last, "content", None)) if last else ""

    if re.search(r"评审结论\s*[:：]\s*通过", content):
        return "write_excel"
    if review_count >= 4:
        return "write_excel"
    return "revise_case"


def write_excel_node(state: dict[str, Any]) -> dict[str, Any]:
    """写入 Excel 节点：解析 Markdown 表格并落盘。"""
    messages = state.get("messages", [])
    doc_id = (state.get("doc_id") or "").strip()
    prd_hash = (state.get("prd_hash") or "").strip()
    prd_context = (state.get("prd_context") or "").strip()
    feature_catalog = state.get("feature_catalog") or _extract_feature_catalog(prd_context)
    branch_catalog = state.get("branch_catalog") or _extract_branch_catalog(prd_context)

    latest_table_text = ""
    for msg in reversed(messages or []):
        text = _extract_text_from_content(getattr(msg, "content", None))
        if _extract_markdown_table_block(text):
            latest_table_text = text
            break

    cases = _parse_test_cases_from_markdown(latest_table_text)
    if not cases:
        return {"messages": [AIMessage(content="未解析到可写入的测试用例表格，请确认已按要求输出 Markdown 表格。")]}

    # 写入前做“功能点/路径缺失补齐”，保证 PRD 不漏功能入口
    missing_items = _missing_catalog_items(cases, feature_catalog)
    auto_added = 0
    if missing_items:
        existing_ids = {str(c.get("用例ID") or "").strip() for c in cases if str(c.get("用例ID") or "").strip()}
        auto_cases = _generate_auto_cases(missing_items, existing_case_ids=existing_ids)
        auto_added = len(auto_cases)
        cases.extend(auto_cases)
        _LOGGER.info(
            "testcase_flow.write_excel.autofill: missing_paths=%s auto_cases=%s",
            len(missing_items),
            auto_added,
        )

    existing_ids = {str(c.get("用例ID") or "").strip() for c in cases if str(c.get("用例ID") or "").strip()}
    seq = _next_auto_case_seq(existing_ids)

    # 自动补齐：金额展示“总和/分开”两种模式（若检测到差异但未覆盖）
    variant_added = 0
    if _detect_amount_display_variants(prd_context):
        has_total = any(_AMOUNT_TOTAL_RE.search(_case_text(c) or "") for c in cases)
        has_split = any(_AMOUNT_SPLIT_RE.search(_case_text(c) or "") for c in cases)
        if not has_total:
            cid = f"TC-AUTO-{seq:03d}"
            seq += 1
            existing_ids.add(cid)
            cases.append(
                {
                    "用例ID": cid,
                    "模块": "金额展示",
                    "需求点": "金额展示模式=总和展示（配置差异）",
                    "前置条件": "后台配置：金额展示模式=总和展示（合计/汇总）",
                    "测试步骤": "1. 进入对应页面/弹窗\n2. 触发金额展示场景\n3. 观察金额区域展示与布局",
                    "预期结果": "展示【合计/汇总】区域（总金额），不展示逐项明细；金额单位/格式/小数位与 PRD/原型一致。",
                    "优先级": "P0",
                    "测试类型": "功能测试",
                    "关联内容": "金额展示模式：总和/合计/汇总（配置差异用例，写入节点自动补齐）",
                }
            )
            variant_added += 1
        if not has_split:
            cid = f"TC-AUTO-{seq:03d}"
            seq += 1
            existing_ids.add(cid)
            cases.append(
                {
                    "用例ID": cid,
                    "模块": "金额展示",
                    "需求点": "金额展示模式=分开展示（配置差异）",
                    "前置条件": "后台配置：金额展示模式=分开展示（分项/明细/逐项）",
                    "测试步骤": "1. 进入对应页面/弹窗\n2. 触发金额展示场景\n3. 观察金额区域展示与布局",
                    "预期结果": "展示【分项明细/逐项金额】列表，不展示合计汇总区（或按 PRD/原型定义展示合计+明细）；金额单位/格式/小数位与 PRD/原型一致。",
                    "优先级": "P0",
                    "测试类型": "功能测试",
                    "关联内容": "金额展示模式：分开/分项/明细/逐项（配置差异用例，写入节点自动补齐）",
                }
            )
            variant_added += 1

    # 自动补齐：流程/分支清单（每个分支至少 1 条）
    branch_added = 0
    branches = [b.strip() for b in (branch_catalog or []) if isinstance(b, str) and b.strip()]
    if branches:
        normalized_rows = [_normalize_for_match(_case_text(c)) for c in cases]
        missing_branches: list[str] = []
        for br in branches:
            norm = _normalize_for_match(br)
            if not norm:
                continue
            if any(norm in row for row in normalized_rows):
                continue
            missing_branches.append(br)

        for br in missing_branches[:60]:
            cid = f"TC-AUTO-{seq:03d}"
            seq += 1
            existing_ids.add(cid)
            parts = [p.strip() for p in br.split("->", 1)]
            src = parts[0] if parts else "起点"
            dst = parts[1] if len(parts) > 1 else "终点"
            cases.append(
                {
                    "用例ID": cid,
                    "模块": "流程分支",
                    "需求点": f"流程分支覆盖：{src} -> {dst}",
                    "前置条件": "满足分支条件/事件（详见关联内容）",
                    "测试步骤": "1. 按分支条件准备数据/配置\n2. 执行触发动作进入分支\n3. 验证流程走向与页面/提示/状态变化",
                    "预期结果": f"流程按分支定义从“{src}”进入“{dst}”，条件满足/不满足时走向正确；关键提示/状态/按钮与 PRD/原型一致。",
                    "优先级": "P0",
                    "测试类型": "功能测试",
                    "关联内容": f"分支原文：{br}\n（流程分支用例，写入节点自动补齐）",
                }
            )
            branch_added += 1

    out_dir = _TESTCASE_OUTPUT_DIR / (doc_id or prd_hash[:12] or "manual")
    out_dir.mkdir(parents=True, exist_ok=True)
    file_path = out_dir / "test_cases.xlsx"
    _LOGGER.info("testcase_flow.write_excel: cases=%s path=%s", len(cases), file_path.as_posix())

    save_cases_result = save_test_cases_to_excel(
        cases,
        file_path=file_path.as_posix(),
        sheet_name="测试用例",
        mode="overwrite",
    )

    # 追加评审记录
    review_text = _extract_text_from_content(getattr(messages[-1], "content", None)) if messages else ""
    verdict = "通过" if re.search(r"评审结论\s*[:：]\s*通过", review_text) else "不通过"
    save_review_result = save_test_cases_to_excel(
        [
            {
                "DOC_ID": doc_id,
                "PRD_HASH": prd_hash,
                "评审轮次": int(state.get("review_count", 0) or 0),
                "评审结论": verdict,
                "评审内容": review_text,
                "是否自动补齐缺失功能点": "是" if missing_items else "否",
                "自动补齐缺失功能点数量": str(len(missing_items)),
                "自动新增用例条数": str(auto_added),
                "是否自动补齐金额模式差异": "是" if variant_added else "否",
                "自动新增金额模式用例条数": str(variant_added),
                "是否自动补齐流程分支": "是" if branch_added else "否",
                "自动新增流程分支用例条数": str(branch_added),
                "生成时间": datetime.now().isoformat(timespec="seconds"),
            }
        ],
        file_path=file_path.as_posix(),
        sheet_name="评审记录",
        mode="append",
    )

    missing_preview = ""
    if missing_items:
        preview = missing_items[:12]
        preview_text = "; ".join(
            [
                f"{it.get('feature') or '未知功能'}（路径：{it.get('path') or '无'}）"
                for it in preview
            ]
        )
        suffix = "..." if len(missing_items) > len(preview) else ""
        missing_preview = f"\n[自动补齐] 缺失功能点/路径 {len(missing_items)} 个：{preview_text}{suffix}\n"

    return {
        "messages": [
            AIMessage(
                content=(
                    f"{save_cases_result}\n"
                    f"{save_review_result}\n"
                    f"DOC_ID：{doc_id or '无'}\n"
                    f"PRD_HASH：{prd_hash or '无'}\n"
                    f"{missing_preview}"
                    f"文件：{file_path.as_posix()}\n"
                    "Sheet：测试用例 / 评审记录"
                )
            )
        ]
    }
