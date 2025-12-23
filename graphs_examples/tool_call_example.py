from langchain.agents import create_agent

from file_rag.core.llms import get_default_model
from langchain.tools import tool
from langchain_core.messages import SystemMessage, AIMessage
from langgraph.constants import END
from langgraph.graph import MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from tools import save_test_cases_to_excel


class TestCaseState(MessagesState):
    review_count: int
    prd_hash: str  # 用于标识当前 PRD


model = get_default_model()


# Define tools
@tool
def multiply(a: int, b: int) -> int:
    """Multiply `a` and `b`.

    Args:
        a: First int
        b: Second int
    """
    return a * b


@tool
def add(a: int, b: int) -> int:
    """Adds `a` and `b`.

    Args:
        a: First int
        b: Second int
    """
    return a + b


@tool
def divide(a: int, b: int) -> float:
    """Divide `a` and `b`.

    Args:
        a: First int
        b: Second int
    """
    return a / b


tools = [add, multiply,divide]
tool_node = ToolNode(tools)


def _stringify_content(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _extract_all_text(messages) -> str:
    chunks: list[str] = []
    for msg in messages or []:
        content = getattr(msg, "content", None)
        if isinstance(content, str):
            chunks.append(content)
            continue
        if isinstance(content, list):
            # block content: try text field, else stringify block
            for b in content:
                if isinstance(b, dict) and isinstance(b.get("text"), str):
                    chunks.append(b["text"])
                else:
                    chunks.append(_stringify_content(b))
            continue
        chunks.append(_stringify_content(content))
    return "\n".join(chunks)


def _strip_md(value: str) -> str:
    s = (value or "").strip()
    if s.startswith("**") and s.endswith("**") and len(s) >= 4:
        s = s[2:-2].strip()
    return s


def _parse_test_cases_from_markdown(text: str) -> list[dict]:
    """
    解析 Markdown 表格里的测试用例行：
    | **TC-XXX** | **标题** <br>1... | 预期... | P0 | 测试类型 |

    只做必要的健壮性处理：不依赖 LLM，保证可重复。
    """
    import re

    rows: list[dict] = []
    if not text:
        return rows

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not (line.startswith("|") and "TC-" in line):
            continue

        parts = [p.strip() for p in line.strip("|").split("|")]
        if len(parts) < 3:
            continue

        case_id = _strip_md(parts[0])
        if not case_id.startswith("TC-"):
            continue

        title_and_steps = parts[1]
        segs = [s.strip() for s in title_and_steps.split("<br>") if s.strip()]
        title = _strip_md(segs[0]) if segs else _strip_md(title_and_steps)
        steps = "\n".join(segs[1:]) if len(segs) > 1 else ""
        steps = re.sub(r"<br\s*/?>", "\n", steps)

        expected = re.sub(r"<br\s*/?>", "\n", parts[2]).strip()
        expected = _strip_md(expected)

        priority = _strip_md(parts[3]) if len(parts) >= 4 else ""
        test_type = _strip_md(parts[4]) if len(parts) >= 5 else ""

        rows.append(
            {
                "用例ID": case_id,
                "用例标题": title,
                "测试步骤": steps,
                "预期结果": expected,
                "优先级": priority,
                "测试类型": test_type,
            }
        )

    return rows


def write_excel_node(state: TestCaseState):
    """保存评审后的结果到 Excel（测试用例 + 评审记录）"""
    from langchain_core.messages import HumanMessage
    import hashlib
    import os
    from datetime import datetime

    # 计算当前 PRD 的 hash（用第一条消息作为 PRD 标识）
    first_message = state["messages"][0].content if state["messages"] else ""
    if isinstance(first_message, list):
        first_message = str(first_message)
    current_prd_hash = hashlib.md5(first_message.encode()).hexdigest()

    # 判断是否是新 PRD
    is_new_prd = state.get("prd_hash") != current_prd_hash
    file_path = "test_cases.xlsx"

    # 检查文件是否存在
    file_exists = os.path.exists(file_path)

    # 决定写入模式
    if is_new_prd or not file_exists:
        mode_instruction = "覆盖写入（清空旧数据）"
        mode = "overwrite"
    else:
        mode_instruction = "追加写入（保留旧数据，添加新用例）"
        mode = "append"

    # 1) 优先走确定性解析：从消息文本中解析 Markdown 测试用例表格
    all_text = _extract_all_text(state.get("messages", []))
    parsed_cases = _parse_test_cases_from_markdown(all_text)
    review_text = _stringify_content(state.get("messages", [])[-1].content) if state.get("messages") else ""

    if parsed_cases:
        save_result = save_test_cases_to_excel(
            parsed_cases, file_path=file_path, sheet_name="测试用例", mode=mode
        )
        save_test_cases_to_excel(
            [
                {
                    "PRD_HASH": current_prd_hash,
                    "评审轮次": state.get("review_count", 0),
                    "写入模式": mode_instruction,
                    "评审内容": review_text,
                    "生成时间": datetime.now().isoformat(timespec="seconds"),
                }
            ],
            file_path=file_path,
            sheet_name="评审记录",
            mode="append",
        )
        return {
            "messages": [AIMessage(content=save_result)],
            "prd_hash": current_prd_hash,
        }

    agent = create_agent(
        model=model,
        tools=[save_test_cases_to_excel],
        system_prompt=f"You are a helpful assistant. 请仔细提取文档中的【所有】测试用例，不要遗漏任何一条。将所有测试用例保存到 test_cases.xlsx 文件中（{mode_instruction}）。"
    )

    # 添加明确的保存指令
    messages = state["messages"] + [
        HumanMessage(content=f"请将上述【所有】测试用例完整保存到 test_cases.xlsx 文件中（{mode_instruction}），不要遗漏")
    ]

    result = agent.invoke({"messages": messages})

    # result 是字典，包含 messages 字段
    if isinstance(result, dict) and "messages" in result:
        return {"messages": result["messages"], "prd_hash": current_prd_hash}
    return {"messages": [AIMessage(content="保存完成")], "prd_hash": current_prd_hash}

def call_llm_node(state: TestCaseState):
    """编写测试用例节点"""
    model_with_tools = model.bind_tools(tools)
    result = model_with_tools.invoke(state["messages"])
    return {"messages": [result]}


def review_test_case_node(state: TestCaseState):
    """测试用例评审节点"""
    review_prompt = SystemMessage(content="""你是测试用例评审专家，请评审上述测试用例，检查：
1. 用例ID是否规范
2. 测试步骤是否清晰完整
3. 预期结果是否明确
4. 是否有遗漏的边界场景
给出评审意见和改进建议。""")
    messages = [review_prompt] + state["messages"]
    result = model.invoke(messages)
    return {"messages": [result], "review_count": state.get("review_count", 0) + 1}


def condition_edge(state: TestCaseState):
    """条件边：判断评审结果"""
    last_message = state["messages"][-1]

    # 检查是否有 tool_calls
    if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
        return "write_case"

    content = last_message.content
    review_count = state.get("review_count", 0)

    if "通过" in content:
        return "write_excel"
    elif review_count >= 3:
        return "write_excel"
    else:
        return "write_case"  # 修复：返回 write_case 而不是 review_case



# 构建图
graph = StateGraph(TestCaseState)
graph.add_node("write_case", call_llm_node)
graph.add_node("review_case", review_test_case_node)
graph.add_node("write_excel", write_excel_node)
graph.add_node("tool_node", tool_node)

graph.set_entry_point("write_case")
graph.add_edge("write_case", "tool_node")
graph.add_edge("tool_node", "review_case")
graph.add_conditional_edges("review_case", condition_edge, {
    "write_excel": "write_excel",
    "write_case": "write_case",
    END: END
})

app = graph.compile()









