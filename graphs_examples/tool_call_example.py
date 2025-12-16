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


def write_excel_node(state: TestCaseState):
    """使用 agent 智能解析并保存测试用例到Excel"""
    from langchain_core.messages import HumanMessage
    import hashlib
    import os

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
    else:
        mode_instruction = "追加写入（保留旧数据，添加新用例）"

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









