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
from typing import Any, Literal

from langchain_core.messages import AIMessage, SystemMessage
from langgraph.constants import END
from langgraph.graph import MessagesState, StateGraph

from file_rag.core.llms import get_default_model, get_doubao_seed_model
from file_rag.main import agent as pdf_agent


class DocumentCallState(MessagesState):
    # detect 节点会把 route 写到 state 里，用于条件边选择后续节点。
    route: Literal["image", "file", "chat"]


# 工具 pdf_analyze_doc / pdf_read_report 会在消息中输出 “DOC_ID: <64位hex>”，用于断点续跑。
_DOC_ID_RE = re.compile(r"\bDOC_ID\s*:\s*[0-9a-fA-F]{64}\b")

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


def detect_file_type_node(state: DocumentCallState) -> dict[str, Any]:
    # 节点1：检测文件类型（写入 route）。
    route = _detect_route(state.get("messages", []))
    return {"route": route}


def route_edge(state: DocumentCallState) -> str:
    # 条件边：读取 state.route 决定下一跳。
    return state.get("route", "chat")


def image_chat_node(state: DocumentCallState) -> dict[str, Any]:
    # 节点2：图片对话（豆包）。
    messages = state.get("messages", [])
    result = _image_model.invoke([SystemMessage(content=_IMAGE_SYSTEM_PROMPT), *messages])
    return {"messages": [result]}


def file_chat_node(state: DocumentCallState) -> dict[str, Any]:
    # 节点3：文件（PDF）对话（deepseek）。
    # 关键点：PDF 里包含的图片/流程图等多模态信息，不需要这里手写解析。
    # - tools.py 会在 before_model 中把 PDF base64 附件替换成“可读文本”
    # - 并在解析 PDF 图片时，内部使用豆包把 image->text，再合并回文本喂给 deepseek
    result = pdf_agent.invoke({"messages": state.get("messages", [])})
    if isinstance(result, dict) and "messages" in result:
        return {"messages": result["messages"]}
    if isinstance(result, AIMessage):
        return {"messages": [result]}
    return {"messages": [AIMessage(content=str(result))]}


def normal_chat_node(state: DocumentCallState) -> dict[str, Any]:
    # 节点4：普通对话（deepseek）。
    messages = state.get("messages", [])
    result = _chat_model.invoke([SystemMessage(content=_CHAT_SYSTEM_PROMPT), *messages])
    return {"messages": [result]}


# 组装 LangGraph：
# detect -> (image_chat / file_chat / chat) -> END
graph = StateGraph(DocumentCallState)
graph.add_node("detect", detect_file_type_node)
graph.add_node("image_chat", image_chat_node)
graph.add_node("file_chat", file_chat_node)
graph.add_node("chat", normal_chat_node)

graph.set_entry_point("detect")
graph.add_conditional_edges(
    "detect",
    route_edge,
    {
        "image": "image_chat",
        "file": "file_chat",
        "chat": "chat",
    },
)
graph.add_edge("image_chat", END)
graph.add_edge("file_chat", END)
graph.add_edge("chat", END)

app = graph.compile()
