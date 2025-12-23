from __future__ import annotations

"""
document_call：根据用户消息里是否包含文件块，自动选择合适的对话智能体。

路由规则（优先级从高到低）：
1) PDF（mime_type == application/pdf） -> file_chat（deepseek + tools.py 的 PDF 解析链路）
2) 图片（image_url / image / 或 file + image/*） -> image_chat（豆包）
3) 其它纯文本 -> normal_chat（deepseek）

说明：
- 前端上传文件后，会把“文件内容”作为 messages[*].content 的 block list 传进来：
  - 图片通常是：{"type":"image_url","image_url":{"url":"data:image/png;base64,..."}}
  - PDF 通常是：{"type":"file","source_type":"base64","mime_type":"application/pdf","data":"..."}
- 对 PDF 来说，后续“继续解析/继续提问”可能只包含 DOC_ID 文本；因此也要用 DOC_ID 做兜底判断。
"""

import re
import sys
import logging
from pathlib import Path
from typing import Any, Literal

from langchain_core.messages import AIMessage, SystemMessage
from langgraph.constants import END
from langgraph.graph import MessagesState, StateGraph

from file_rag.core.llms import get_default_model, get_doubao_seed_model
from file_rag.main import agent as pdf_agent

_LOGGER = logging.getLogger(__name__)

# 说明：langgraph_api 以“文件路径”方式加载 graphs_examples 下的脚本时，
# sys.path 未必包含项目根目录；这里做一次兜底，确保同目录模块可导入。
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if _PROJECT_ROOT.as_posix() not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT.as_posix())

from graphs_examples.testcase_flow import (  # noqa: E402
    condition_edge as testcase_condition_edge,
    preprocess_pdf_node,
    prepare_case_context_node,
    review_case_node,
    revise_case_node,
    write_case_node,
    write_excel_node,
)


class DocumentCallState(MessagesState):
    # detect 节点会把 route 写到 state 里，用于条件边选择后续节点。
    route: Literal["image", "file", "chat"]
    # detect 节点会把 intent 写到 state 里，用于触发“测试用例工作流”。
    intent: Literal["testcase", "chat"]
    # 测试用例工作流状态字段（可选，由节点按需写入）。
    review_count: int
    prd_hash: str
    prd_context: str
    doc_id: str


# 工具 pdf_analyze_doc / pdf_read_report 会在消息中输出 “DOC_ID: <64位hex>”，用于断点续跑。
_DOC_ID_RE = re.compile(r"\bDOC_ID\s*:\s*[0-9a-fA-F]{64}\b")
# 测试用例意图识别：既支持“用例 + 动作”，也支持“测试点/场景/方案”等同义表述。
# 注意：这里仅用于路由到“测试用例工作流”，宁愿偏保守，也不要误触发。
_TESTCASE_NOUN_RE = re.compile(
    r"(测试用例|用例|测试点|测试场景|测试方案|测试计划|检查项|test\s*case|testcase|case)",
    re.IGNORECASE,
)
_TESTCASE_VERB_RE = re.compile(
    r"(生成|编写|补充|输出|整理|导出|写入|保存|落盘|覆盖|更新|完善|细化|拆分|补全)",
    re.IGNORECASE,
)
_EXCEL_INTENT_RE = re.compile(r"(导出|写入|保存).*(excel|xlsx)", re.IGNORECASE)
_REVIEW_INTENT_RE = re.compile(r"(用例评审|评审|review)", re.IGNORECASE)

# 图片对话：要求先“看见什么”，再回答问题；避免臆测。
_IMAGE_SYSTEM_PROMPT = (
    "你是一个严谨的图片分析与问答助手。\n"
    "要求：\n"
    "1) 先描述你在图片中观察到的关键信息（如文字、图表、流程、布局、异常点）；\n"
    "2) 再结合用户问题给出结论与推理；\n"
    "3) 不要臆测图片中不存在的信息；如果无法确认，请明确说明不确定与需要补充的内容。\n"
)

# 普通对话：尽量简洁准确即可（deepseek）。
_CHAT_SYSTEM_PROMPT = "你是一个专业、简洁、准确的助手。"

# 模型选择：
# - 图片对话：豆包（多模态输入更稳定）
# - 普通对话：deepseek
_image_model = get_doubao_seed_model()
_chat_model = get_default_model()

def _compact_err(exc: Exception, max_len: int = 500) -> str:
    err = str(exc) or exc.__class__.__name__
    err = err.replace("\n", " ").strip()
    return err if len(err) <= max_len else err[:max_len] + "…"


def _iter_content_blocks(messages: list[Any]) -> list[dict[str, Any]]:
    # 从 messages 的 content(list) 中抽取所有 block(dict)，用于判断是否含图片/PDF。
    blocks: list[dict[str, Any]] = []
    for msg in messages:
        content = getattr(msg, "content", None)
        if isinstance(content, list):
            for b in content:
                if isinstance(b, dict):
                    blocks.append(b)
    return blocks


def _extract_all_text(messages: list[Any]) -> str:
    # 抽取所有可见文本（content 为 str，或 block 里的 text 字段）。
    # 用途：兜底判断 DOC_ID / “PDF已落盘”等提示文本。
    chunks: list[str] = []
    for msg in messages:
        content = getattr(msg, "content", None)
        if isinstance(content, str):
            chunks.append(content)
            continue
        if isinstance(content, list):
            for b in content:
                if isinstance(b, dict) and isinstance(b.get("text"), str):
                    chunks.append(b["text"])
    return "\n".join(chunks)


def _detect_route(messages: list[Any]) -> Literal["image", "file", "chat"]:
    # 这里是“路由核心”：根据文件类型决定走哪个 agent。
    blocks = _iter_content_blocks(messages)

    # 1) 优先识别 PDF：前端会把 pdf 作为 file(base64) block 传入。
    has_pdf = any(
        (b.get("type") == "file" and (b.get("mime_type") or "") == "application/pdf")
        for b in blocks
    )
    if has_pdf:
        return "file"

    # 2) 识别图片：支持 image_url / image，以及 legacy 的 file + image/*。
    has_image = any(
        b.get("type") in {"image_url", "image"}
        or (b.get("type") == "file" and str(b.get("mime_type") or "").startswith("image/"))
        for b in blocks
    )
    if has_image:
        return "image"

    # 3) 兜底：如果文本里已经出现 DOC_ID 或 “PDF已落盘”，说明用户在追问 PDF，也继续走 file_chat。
    text = _extract_all_text(messages)
    if "PDF已落盘" in text or _DOC_ID_RE.search(text):
        return "file"

    return "chat"


def _detect_intent(messages: list[Any]) -> Literal["testcase", "chat"]:
    # 仅基于“最后一条用户输入”判断意图，避免误用 PDF 正文内容触发。
    text = _extract_all_text(messages[-1:]) if messages else ""
    if not text.strip():
        return "chat"
    if _EXCEL_INTENT_RE.search(text) or _REVIEW_INTENT_RE.search(text):
        return "testcase"
    if _TESTCASE_NOUN_RE.search(text) and (_TESTCASE_VERB_RE.search(text) or "测试" in text):
        return "testcase"
    return "chat"


def detect_file_type_node(state: DocumentCallState) -> dict[str, Any]:
    # 节点1：检测文件类型（写入 route）。
    messages = state.get("messages", [])
    route = _detect_route(messages)
    intent = _detect_intent(messages)
    last_user_len = len((_extract_all_text(messages[-1:]) if messages else "").strip())
    _LOGGER.info("document_call.detect: route=%s intent=%s last_user_len=%s", route, intent, last_user_len)
    return {"route": route, "intent": intent}


def route_edge(state: DocumentCallState) -> str:
    # 条件边：读取 state.route 决定下一跳。
    route = state.get("route", "chat")
    intent = state.get("intent", "chat")

    # 测试用例工作流：支持 PDF / 纯文本两种输入。
    if intent == "testcase":
        if route == "image":
            _LOGGER.info("document_call.route_edge: image + testcase_intent -> testcase_flow")
        return "testcase"

    # 普通图片对话：仅在“非测试用例意图”下生效。
    if route == "image":
        return "image"

    return route


def image_chat_node(state: DocumentCallState) -> dict[str, Any]:
    # 节点2：图片对话（豆包）。
    messages = state.get("messages", [])
    try:
        result = _image_model.invoke([SystemMessage(content=_IMAGE_SYSTEM_PROMPT), *messages])
        return {"messages": [result]}
    except Exception as exc:
        return {
            "messages": [
                AIMessage(
                    content=(
                        "[图片对话失败："
                        f"{_compact_err(exc)}]\n"
                        "提示：请确认所选模型/网关支持多模态输入（image_url/image），或更换为支持图片的模型。"
                    )
                )
            ]
        }


def file_chat_node(state: DocumentCallState) -> dict[str, Any]:
    # 节点3：文件（PDF）对话（deepseek）。
    # 关键点：PDF 里包含的图片/流程图等多模态信息，不需要这里手写解析。
    # - tools.py 会在 before_model 中把 PDF base64 附件替换成“可读文本”
    # - 并在解析 PDF 图片时，内部使用豆包把 image->text，再合并回文本喂给 deepseek
    try:
        result = pdf_agent.invoke({"messages": state.get("messages", [])})
    except Exception as exc:
        return {
            "messages": [
                AIMessage(
                    content=(
                        "[PDF 对话失败："
                        f"{_compact_err(exc)}]\n"
                        "提示：若消息里同时包含图片块（image_url/image），已在 PDF 预处理阶段做文本化降级；"
                        "如仍失败，请检查模型是否仅支持纯文本 messages。"
                    )
                )
            ]
        }
    if isinstance(result, dict) and "messages" in result:
        return {"messages": result["messages"]}
    if isinstance(result, AIMessage):
        return {"messages": [result]}
    return {"messages": [AIMessage(content=str(result))]}


def normal_chat_node(state: DocumentCallState) -> dict[str, Any]:
    # 节点4：普通对话（deepseek）。
    messages = state.get("messages", [])
    try:
        result = _chat_model.invoke([SystemMessage(content=_CHAT_SYSTEM_PROMPT), *messages])
        return {"messages": [result]}
    except Exception as exc:
        return {
            "messages": [
                AIMessage(content=f"[对话失败：{_compact_err(exc)}]")
            ]
        }


# 组装 LangGraph：
# detect -> (image_chat / file_chat / chat / testcase_flow) -> END
graph = StateGraph(DocumentCallState)
graph.add_node("detect", detect_file_type_node)
graph.add_node("image_chat", image_chat_node)
graph.add_node("file_chat", file_chat_node)
graph.add_node("chat", normal_chat_node)

# 测试用例工作流节点（生成 -> 评审 -> 修订 -> 写入Excel）
graph.add_node("preprocess_pdf", preprocess_pdf_node)
graph.add_node("prepare_case_context", prepare_case_context_node)
graph.add_node("write_case", write_case_node)
graph.add_node("review_case", review_case_node)
graph.add_node("revise_case", revise_case_node)
graph.add_node("write_excel", write_excel_node)

graph.set_entry_point("detect")
graph.add_conditional_edges(
    "detect",
    route_edge,
    {
        "image": "image_chat",
        "file": "file_chat",
        "chat": "chat",
        "testcase": "preprocess_pdf",
    },
)
graph.add_edge("image_chat", END)
graph.add_edge("file_chat", END)
graph.add_edge("chat", END)

graph.add_edge("preprocess_pdf", "prepare_case_context")
graph.add_edge("prepare_case_context", "write_case")
graph.add_edge("write_case", "review_case")
graph.add_conditional_edges(
    "review_case",
    testcase_condition_edge,
    {
        "write_excel": "write_excel",
        "revise_case": "revise_case",
    },
)
graph.add_edge("revise_case", "review_case")
graph.add_edge("write_excel", END)

app = graph.compile()
