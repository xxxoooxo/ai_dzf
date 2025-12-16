# LangGraph 开发常见错误总结（实战版）

## 文档说明
本文档总结了在开发测试用例生成工作流时**实际遇到**的错误及解决方案，适用于面试准备和实际开发参考。

---

## 1. State 类型不匹配错误 ✅ 实际遇到

### 错误现象
```python
graph = StateGraph(MessagesState)  # 使用 MessagesState
def condition_edge(state: TestCaseState):
    review_count = state.get("review_count", 0)  # ❌ MessagesState 没有此字段
```

### 解决方案
```python
# 1. 扩展 State 类
class TestCaseState(MessagesState):
    review_count: int
    prd_hash: str  # 标识当前 PRD

# 2. 图使用扩展后的 State
graph = StateGraph(TestCaseState)  # ✅ 使用扩展后的类型
```

### 面试要点
- 自定义字段必须在 State 定义中声明
- 保持图定义和节点函数的 State 类型一致

---

## 2. 节点返回值格式错误 ✅ 实际遇到

### 错误现象
```python
def call_llm_node(state: MessagesState):
    result = model.invoke(state["messages"])
    return {"messages": result}  # ❌ 应该是列表
```

### 解决方案
```python
def call_llm_node(state: MessagesState):
    result = model.invoke(state["messages"])
    return {"messages": [result]}  # ✅ 包装成列表
```

---

## 3. 节点函数缺少返回值 ✅ 实际遇到

### 错误现象
```
InvalidUpdateError: Expected dict, got None
```

### 原因
节点函数没有返回值

### 解决方案
```python
# ❌ 错误：没有返回值
def write_excel_node(state):
    agent.invoke(state["messages"])  # 没有 return

# ✅ 正确：返回更新的状态
def write_excel_node(state):
    result = agent.invoke({"messages": state["messages"]})
    return {"messages": result["messages"]}
```

---

## 4. Agent invoke 参数格式错误 ✅ 实际遇到

### 错误现象
```
Expected dict, got list
```

### 原因
`langchain.agents.create_agent` 期望 `{"messages": list}` 格式

### 解决方案
```python
# ❌ 错误
agent.invoke(state["messages"])

# ✅ 正确
agent.invoke({"messages": state["messages"]})
```

---

## 5. 条件边返回值映射错误 ✅ 实际遇到

### 错误现象
```
KeyError: 'review_case'
```

### 原因
条件边返回的节点名称在映射中不存在

### 解决方案
```python
def condition_edge(state: TestCaseState):
    if "通过" in state["messages"][-1].content:
        return "write_excel"
    else:
        return "write_case"  # ✅ 必须在映射中存在

graph.add_conditional_edges("review_case", condition_edge, {
    "write_excel": "write_excel",
    "write_case": "write_case",  # ✅ 映射必须包含所有可能的返回值
    END: END
})
```

---

## 6. Empty input messages 错误 ✅ 实际遇到

### 错误现象
```
Error code: 400 - {'error': {'message': 'Empty input messages'}}
```

### 原因
传给 LLM 的消息列表为空或格式异常

### 解决方案
```python
def write_excel_node(state: TestCaseState):
    # 处理 content 可能是列表的情况
    content = state["messages"][-1].content
    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, dict) and item.get('type') == 'text':
                text_parts.append(item.get('text', ''))
        content = ''.join(text_parts)

    # 检查内容是否为空
    if not content or not content.strip():
        return {"messages": [AIMessage(content="没有内容")]}

    # 使用处理后的内容
    agent.invoke({"messages": [HumanMessage(content=content)]})
```

---

## 7. 消息内容是列表格式 ✅ 实际遇到

### 错误现象
```python
content = [{'type': 'text', 'text': '实际内容...'}]
```

### 原因
某些 LLM 返回的 content 是列表格式而不是字符串

### 解决方案
```python
def extract_text_content(content):
    """提取文本内容"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, dict) and item.get('type') == 'text':
                text_parts.append(item.get('text', ''))
        return ''.join(text_parts)
    return ""
```
```

---

## 8. 实现追加写入功能（业务场景）✅ 实际需求

### 需求场景
- 同一个 PRD：追加写入测试用例
- 新的 PRD：覆盖写入测试用例

### 实现方案
```python
import hashlib
import os

class TestCaseState(MessagesState):
    review_count: int
    prd_hash: str  # 标识当前 PRD

def write_excel_node(state: TestCaseState):
    # 计算当前 PRD 的 hash
    first_message = state["messages"][0].content
    current_prd_hash = hashlib.md5(str(first_message).encode()).hexdigest()

    # 判断是否是新 PRD
    is_new_prd = state.get("prd_hash") != current_prd_hash
    file_exists = os.path.exists("test_cases.xlsx")

    # 决定写入模式
    if is_new_prd or not file_exists:
        mode = "覆盖写入"
    else:
        mode = "追加写入"

    # 在 system_prompt 中指定模式
    agent = create_agent(
        model=model,
        tools=[save_test_cases_to_excel],
        system_prompt=f"请仔细提取文档中的【所有】测试用例，不要遗漏。将所有测试用例保存到 test_cases.xlsx（{mode}）"
    )

    result = agent.invoke({"messages": state["messages"]})

    # 更新 prd_hash
    return {
        "messages": result["messages"],
        "prd_hash": current_prd_hash
    }
```

### 面试要点
- 使用 hash 标识不同的输入文档
- 通过 State 字段保持状态
- 在 system_prompt 中控制业务逻辑

---

## 核心概念总结

### State 管理
- State 是工作流的数据容器
- 节点返回的字典会更新 State
- 使用 `Annotated[list, add_messages]` 实现消息追加

### 节点类型
- 普通函数节点：`def my_node(state): return {...}`
- ToolNode：自动执行工具调用
- 条件边：根据 State 决定下一步

### 消息流转
- HumanMessage：用户输入
- AIMessage：LLM 回复（可能包含 tool_calls）
- ToolMessage：工具执行结果
- SystemMessage：系统提示

### 最佳实践
1. 统一使用自定义 State 类型
2. 节点返回值格式与 State 定义一致
3. 节点函数必须有返回值
4. 条件边返回值必须在映射中存在
5. 处理 content 可能是列表的情况
6. 在 system_prompt 中明确指令（如"提取所有用例"）

---

## 完整工作流示例

```python
from langchain.agents import create_agent
from file_rag.core.llms import get_default_model
from langchain_core.messages import SystemMessage, AIMessage
from langgraph.constants import END
from langgraph.graph import MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from tools import save_test_cases_to_excel


class TestCaseState(MessagesState):
    review_count: int
    prd_hash: str


model = get_default_model()
tools = [add, multiply, divide]
tool_node = ToolNode(tools)


def call_llm_node(state: TestCaseState):
    """编写测试用例节点"""
    model_with_tools = model.bind_tools(tools)
    result = model_with_tools.invoke(state["messages"])
    return {"messages": [result]}


def review_test_case_node(state: TestCaseState):
    """测试用例评审节点"""
    review_prompt = SystemMessage(content="你是测试用例评审专家...")
    messages = [review_prompt] + state["messages"]
    result = model.invoke(messages)
    return {"messages": [result], "review_count": state.get("review_count", 0) + 1}


def write_excel_node(state: TestCaseState):
    """保存测试用例到Excel"""
    agent = create_agent(model=model, tools=[save_test_cases_to_excel])
    result = agent.invoke({"messages": state["messages"]})
    return {"messages": result["messages"]}


def condition_edge(state: TestCaseState):
    """条件边：判断评审结果"""
    last_message = state["messages"][-1]
    if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
        return "write_case"

    content = last_message.content
    review_count = state.get("review_count", 0)

    if "通过" in content:
        return "write_excel"
    elif review_count >= 3:
        return "write_excel"
    else:
        return "write_case"


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
```

---

**文档版本**：v2.0（实战版）
**创建日期**：2025-12-15
**最后更新**：2025-12-15
**适用场景**：LangGraph 开发、技术面试准备
**基于项目**：测试用例自动生成工作流

