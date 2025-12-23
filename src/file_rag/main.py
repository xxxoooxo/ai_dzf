"""
该模块保持“最小职责”：

- 只负责组装 LangChain agent（`agent` / `image_agent`）；
- 在 `before_model` 中间件里调用 `src/tools.py` 的 PDF 预处理工具，把前端上传的 PDF（base64）
  转成可读文本后再喂给模型；

PDF 解析/分片/多模态图片识别等“工具逻辑”统一放在 `src/tools.py`，避免 main.py 变成“大杂烩”。
"""

import os
from typing import Any

from langchain.agents import AgentState, create_agent
from langchain.agents.middleware import before_model
from langgraph.runtime import Runtime

from file_rag.core.llms import get_default_model, get_doubao_seed_model
from tools import build_pdf_message_updates, pdf_analyze_doc, pdf_read_report


_PDF_TOOL_PROMPT: str = (
    "你是一个严谨的PDF分析助手。\n"
    "当【用户】明确要求“分析/总结/解读/继续解析 PDF”，并且用户消息里出现“DOC_ID:”或“PDF已落盘”时：\n"
    "1) 必须先调用工具 pdf_analyze_doc(doc_id, question) 做逐片完整阅读（doc_id 就是 DOC_ID 后面的哈希字符串）；\n"
    "2) 再基于工具输出回答用户问题；\n"
    "3) 不要自己猜测PDF内容。\n"
    "\n"
    "当用户说“继续/接着/继续解析”且上下文里已有 DOC_ID: ... 时：\n"
    "1) 继续调用 pdf_analyze_doc(doc_id, question)，它会从断点续跑，不会从头开始（除非用户明确说“从头/重来/reset”）。\n"
    "\n"
    "当用户说“把完整内容输出给我/不要总结/我要全文/先给全文再总结”时：\n"
    "1) 不要把 answer.md 一次性全塞到单条回复（可能卡住/截断）；\n"
    "2) 优先使用工具 pdf_read_report(DOC_ID, kind='answer') 分段输出全文；\n"
    "3) 用户后续只要再次说“输出内容”（不需要带 offset），工具会自动从上次位置续读直到结束。\n"
    "\n"
    "当用户只说“输出内容”或“继续”但没有给 DOC_ID 时：\n"
    "1) 先尝试从上下文里找最近一次出现的“DOC_ID: <hash>”；\n"
    "2) 如果仍找不到，则调用 pdf_read_report(doc_id='auto', kind='answer') 自动选择最近落盘的报告并输出。\n"
    "\n"
    "输出规则（很重要）：\n"
    "1) 调用 pdf_read_report(...) 后，把工具返回的正文内容原样输出；\n"
    "2) 不要额外添加“输出完毕/已完成/字数统计/提示语”等任何说明文字（用户只想看到正文）。\n"
    "\n"
    "重要：如果工具返回“已断点保存”，直接把该结果回复给用户并停止；不要在同一轮里再次调用工具。\n"
)

def _pick_image_agent_model():
    """选择 image_agent 的“对话模型”。

    说明：
    - image_agent 的主要用途是“处理带 PDF 的对话”，其中 PDF 图片多模态解析发生在 tools.py 中；
      因此 image_agent 本身不必须使用 doubao。
    - 当 doubao 触发 429（SetLimitExceeded / Safe Experience Mode）时，整个 run 会失败，前端看起来像卡住。
      为了保证系统可用性，默认使用 deepseek 作为 image_agent 的对话模型。

    可选：如果你确认 doubao 可用，并且希望 image_agent 也用 doubao，对齐多模态生态：
    - 设置环境变量：IMAGE_AGENT_MODEL=doubao
    """
    choice = (os.environ.get("IMAGE_AGENT_MODEL", "deepseek") or "deepseek").lower().strip()
    if choice in {"doubao", "doubao-seed", "ark"}:
        return get_doubao_seed_model()
    return get_default_model()


@before_model
def log_before_model(state: AgentState, _runtime: Runtime) -> dict[str, Any] | None:
    """在调用模型前，把 messages 里的 PDF base64 附件替换为文本。

为什么只返回 updated_messages 而不是返回整个 messages？
- LangGraph 的 messages 合并策略（add_messages）会按 message.id 合并：
  - 返回的消息 id 与已有消息相同：覆盖（更新）
  - 返回新 id：追加
- 我们只更新“含 PDF 的那几条消息”，不改其它消息（KISS / 最小改动）。
    """

    updated_messages = build_pdf_message_updates(state.get("messages", []))
    return {"messages": updated_messages} if updated_messages else None


image_agent = create_agent(
    model=_pick_image_agent_model(),
    tools=[pdf_analyze_doc, pdf_read_report],
    middleware=[log_before_model],
    system_prompt=_PDF_TOOL_PROMPT,
)

agent = create_agent(
    model=get_default_model(),
    tools=[pdf_analyze_doc, pdf_read_report],
    middleware=[log_before_model],
    system_prompt=_PDF_TOOL_PROMPT,
)
