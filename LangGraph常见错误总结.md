# LangGraph 开发常见错误总结（实战版）

## 文档说明
本文档总结了在开发测试用例生成工作流时**实际遇到**的错误及解决方案，适用于面试准备和实际开发参考。

## 面试速讲（3-5 分钟讲清楚）

### 你在做什么（30 秒）
- 用 LangGraph 把“需求文档/PDF → 解析 → 生成测试用例 → 评审迭代 → 落 Excel”编排成**可控、可复现、有状态**的工作流。
- 本项目落地的三个工程化抓手：
  1) **多模态降级**：`image_url/file` block 不能直接喂给纯文本模型，必须先转成文本（否则 400）。
  2) **状态驱动迭代**：评审不通过就回路修订，但必须有**轮次上限**避免死循环。
  3) **大输出落盘/截断**：长时间 stream + Markdown 渲染容易把前端拖死，需要截断回显与落盘。

### LangGraph 核心抽象（1 分钟）
- **Graph**：node + edge，本质是“可观测的状态机/有向图”。
- **State**：工作流数据容器（多个字段/Channel 的集合）。节点只返回 **dict（partial update）**，由引擎合并进 state。
- **Reducer/合并策略**：同一字段如何合并（覆盖/追加/自定义）。`MessagesState.messages` 默认用 `add_messages`：按 `message.id` 合并，id 相同覆盖，否则追加。
- **条件边**：根据 state 决定下一跳；返回值必须能在映射表中命中，否则 `KeyError`。
- **Tool 调用链**：模型产出 `tool_calls` → ToolNode/Agent 执行工具 → 产出 ToolMessage → 图继续推进。

### 排查顺序（1 分钟）
1) **图编译期**（启动即挂）：schema/type hints/导入路径 → 先看 `StateGraph(...)`、类型声明与导入。  
2) **运行期状态更新**：`InvalidUpdateError`/`KeyError` → 先看节点返回 dict、字段类型、条件边映射是否全覆盖。  
3) **模型/网关 400**：`unknown variant image_url/file`、`Empty input messages` → 先看 messages content 格式与预处理。  
4) **性能/卡死**：长文本流式 + Markdown 解析 → 做截断/节流/降级渲染 + 工具结果阈值保护。

### 面试官必追问 Checklist（背这几个就够）
- 你怎么解释 “State / Channel / Reducer” 以及 `add_messages` 的合并规则？
- 节点为什么必须返回 dict？返回 None 会怎样？
- 条件边为什么会 KeyError？怎么保证映射覆盖？
- ToolNode 与 `create_agent` 的区别？为什么 `invoke` 必须传 `{"messages": [...]}`？
- 多模态 block 为什么会 400？你把它放在哪里做降级（before_model vs 图节点）？
- 如何避免无限循环？如何做断点续跑/落盘？

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

## 9. 多模态 block 透传导致 400（image_url / file）✅ 实战遇到

### 错误现象
```
openai.BadRequestError: Error code: 400 - {
  'error': {
    'message': '... unknown variant `image_url`, expected `text` ...'
  }
}
```

### 原因
- 文本模型/部分网关只接受 `{"type":"text"}`（或纯字符串）消息内容
- 前端上传图片/PDF 时，`messages[*].content` 往往是 block list：
  - 图片：`{"type":"image_url","image_url":{"url":"data:image/png;base64,..."} }`
  - PDF：`{"type":"file","source_type":"base64","mime_type":"application/pdf","data":"..."}`
- 如果把这些 block 原样透传给 deepseek 等文本模型，就会在服务端反序列化时报 400

### 解决方案（推荐：豆包多模态 -> deepseek 推理）
**目标：deepseek 只看“文本”，图片/流程图先被豆包转成文本再合并。**

1) 在 `before_model` 中间件做统一预处理：把 PDF `file(base64)` 替换成可读文本
2) 检测 PDF 是否包含图片/流程图等视觉内容：有则调用豆包做多模态转文本，再合并到 PDF 文本抽取结果
3) 最终把合并后的**字符串 content** 交给 deepseek（避免 `image_url/file` block 进入请求体）

### 关键代码（本项目落地）
`src/file_rag/main.py`
```python
@before_model
def log_before_model(state: AgentState, _runtime: Runtime) -> dict[str, Any] | None:
    updated_messages = build_pdf_message_updates(state.get("messages", []))
    return {"messages": updated_messages} if updated_messages else None
```

`src/tools.py`
```python
# 1) 扫描 PDF：是否有嵌入图片/矢量流程图（决定是否启用豆包多模态）
has_images, render_pages, _, _ = _scan_pdf_visual_content(...)

# 2) 文本抽取 +（可选）图片/页面渲染 -> 豆包转文本 -> 合并后喂给 deepseek
md = _extract_pdf_markdown(..., user_requested_images=..., doc_id=..., persisted_pdf_path=...)
```

### 调参建议（防止“转圈太久/上下文爆炸”）
- `PDF_IMAGES_MODE=auto|always|never`
- `PDF_IMAGE_MAX_PAGES / PDF_IMAGE_MAX_IMAGES / PDF_IMAGE_MAX_SECONDS / PDF_IMAGE_MAX_BYTES`
- `PDF_CONTEXT_MAX_PAGES / PDF_CONTEXT_MAX_CHARS`
- `PDF_ANALYZE_BATCH_SIZE / PDF_ANALYZE_BATCH_MAX_CHARS`：`pdf_analyze_doc` 对纯文本分片做批量增量笔记（减少 deepseek 调用次数；`PDF_ANALYZE_BATCH_SIZE=1` 可回退到逐片调用）

---

## 10. 前端长时间流式输出导致页面卡死/弹“请等待” ✅ 实战遇到

### 现象
- Chrome 页面无响应、卡死，出现“页面无响应/请等待”提示
- 后端无报错，但前端渲染越来越慢（尤其是长时间 stream、大段 Markdown、工具结果含大 JSON/base64 时）

### 原因
- 流式过程中每个 token 都触发一次 React 渲染
- 渲染链路包含 `react-markdown` / GFM / KaTeX / 代码高亮等高开销解析
- 工具结果里对大文本做正则扫描/JSON.stringify/JSON.parse（例如提取图片 URL、base64）会阻塞主线程

### 解决方案（本项目落地）
1) 渲染节流：将流式文本更新节流到每帧（`requestAnimationFrame`），避免 per-token 触发渲染风暴  
2) 大文本降级：流式或超大内容不走 Markdown，改用 `<pre>` 纯文本渲染，并按阈值只显示最后 N 个字符（保证 UI 持续可交互）  
3) 结果解析限流：对工具结果的图片提取/JSON 解析加长度阈值与快速特征判断，超出阈值直接跳过自动扫描（避免正则“扫全场”）

### 关键代码（本项目落地）
- `ui/src/hooks/useRafThrottledValue.tsx`：逐帧节流 hook
- `ui/src/components/thread/messages/ai.tsx`：流式/大文本降级渲染 + 截断提示
- `ui/src/components/thread/markdown-text.tsx`：Markdown 安全阀（超阈值降级 `<pre>`）
- `ui/src/components/thread/messages/tool-calls-new.tsx`：工具结果解析/图片提取阈值保护

### 调参建议
- `MAX_STREAMING_RENDER_CHARS / MAX_MARKDOWN_RENDER_CHARS / MAX_PLAINTEXT_RENDER_CHARS`
- `MAX_AUTO_IMAGE_SCAN_CHARS / MAX_LONG_BASE64_SCAN_CHARS / MAX_JSON_PARSE_CHARS`

## 核心概念总结

### 1) State / Channel / Reducer（合并语义是核心）
- **State ≠ 普通 dict**：它是多个 channel 的集合；节点返回的是 **partial update**，由引擎按字段合并。
- **messages 合并策略（`add_messages`）**：
  - 新消息（新 id）→ 追加；同 id → 覆盖更新。
  - 这解释了两个高频点：
    1) 为什么节点常写 `return {"messages": [result]}`（追加一条消息）；
    2) 为什么预处理场景要“更新原消息”而不是无限追加（否则上下文爆炸、重复解析）。
- 本项目对应关键代码：
  - `src/tools.py`：`build_pdf_message_updates(...)`（生成“更新原消息”的 update）
  - `src/file_rag/main.py`：`@before_model log_before_model(...)`（在调用模型前统一做消息替换）

### 2) 节点合约（面试最爱问）
- 节点签名：`def node(state) -> dict`（或 async）。
- **必须返回 dict**：返回 None/非 dict → `InvalidUpdateError: Expected dict, got ...`。
- 只返回需要更新的字段（KISS）：例如只更新 `messages` 或 `review_count`，不要把整个 state 复制一遍。

### 3) 条件边（路由必须可穷举）
- 条件边只做“判定”，不要做副作用（否则调试困难、不可复现）。
- 返回值必须在 `add_conditional_edges(..., {mapping})` 中全覆盖，否则 `KeyError`。
- 有回路必设“终止条件/最大轮次”，避免死循环（评审-修订类工作流尤甚）。

### 4) Tool 调用链（两套模式要分清）
- **ToolNode**：读取 `AIMessage.tool_calls`，执行工具并生成 `ToolMessage`，适合“显式工具编排”。
- **create_agent**：Agent 是 Runnable；输入通常是 dict（最常见：`{"messages": [...]}`）。
- 典型坑：`agent.invoke(state["messages"])` 会报 `Expected dict, got list`，因为 Runnable 的 input schema 是映射而非裸 list。

### 5) 多模态消息（content 可能是 list[block]）
- content 既可能是 `str`，也可能是 `[{type:'text'|'image_url'|'file', ...}]`。
- 纯文本模型/网关可能只接受 text/str：`image_url/file` block 原样透传必 400。
- 推荐做法：统一在 `before_model` 或图入口节点做“降级成字符串”，并按预算控制长度。

### 6) 输出与性能（工程化必答）
- 长报告要落盘 + 截断回显（避免前端 stream 渲染风暴）。
- UI 侧做逐帧节流与大文本降级渲染（`<pre>`），工具结果解析加阈值保护。

---

## 本仓库关键代码索引（面试前建议过一遍）
- 图入口与路由：`graphs_examples/document_call.py`
  - `detect_file_type_node`：同时识别 `route`（image/file/chat）与 `intent`（testcase/chat）
  - `route_edge`：图片优先，其次 testcase 工作流，否则走普通对话
- 用例工作流节点：`graphs_examples/testcase_flow.py`
  - `preprocess_pdf_node`：调用 `build_pdf_message_updates` 做多模态降级
  - `prepare_case_context_node`：从 `storage/pdf_extracted/<DOC_ID>/notes.md` 取上下文（兜底取最近 doc）
  - `write_case_node / review_case_node / revise_case_node / condition_edge / write_excel_node`
- Excel 工具与 PDF 预处理：`src/tools.py`
  - `save_test_cases_to_excel`：openpyxl 落盘（支持 overwrite/append）
  - `build_pdf_message_updates`：把 `file(base64)` PDF 变成纯文本并注入 `DOC_ID`
- PDF Agent 预处理入口：`src/file_rag/main.py`
  - `@before_model log_before_model(...)`：调用 `build_pdf_message_updates`，保证模型只吃文本

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

## 9. 路由优先级错误：图片请求吞掉测试用例工作流 ✅ 实际遇到

### 错误现象
- 用户上传多张流程图/原型截图，并明确要求“生成测试用例/写入 Excel”
- 实际却被路由到 `image_chat`，导致**未触发**“生成 → 评审 → 写 Excel”链路（日志里看不到评审/落盘）

### 根因
条件边优先判断 `route == "image"`，导致 **intent=testcase** 被“图片优先”短路：
```python
if route == "image":
    return "image"
if intent == "testcase":
    return "testcase"
```

### 解决方案
让“测试用例意图”优先级高于“图片对话”：
```python
if intent == "testcase":
    return "testcase"
if route == "image":
    return "image"
```

### 面试要点
- 路由是“业务语义优先”还是“媒体类型优先”，必须在设计时说清楚，并用条件边体现
- 典型反例：把图片当作“对话形态”优先，导致“明确业务意图”无法触发工作流

---

## 10. 图片块只做占位符：流程图关键分支信息丢失 ✅ 实际遇到

### 错误现象
- 用例生成阶段拿不到流程图里的分支条件/异常路径/校验规则
- 输出的测试用例出现“功能点遗漏/分支覆盖不足”

### 根因
多模态预处理仅把图片替换成占位符文本（未做 image→text）：
```python
if block_type in {"image_url", "image"}:
    text_chunks.append("[图片已上传：...]")  # ❌ 信息丢失
```

### 解决方案（本仓库落地）
- 给 `build_pdf_message_updates(...)` 增加 `force_image_vision=True`：
  - 测试用例工作流入口强制开启图片/流程图解析
  - 普通对话默认不解析图片，避免无谓开销
- 输出“可检索、可追溯、可用于生成用例”的结构化 Markdown（摘要 + 全量文字 + 分支清单）

关键点（示意）：
```python
updated = build_pdf_message_updates(messages, force_image_vision=True)  # ✅ testcase_flow 强制解析图片
```

### 面试要点
- 多模态解析要“可控”：必须有预算/限流/降级（例如 max_images / max_bytes / 429 熔断）
- “占位符”只适合 UI 展示，不适合需求推导与测试用例生成

---

## 11. 缺少可观测性：无法确认评审/落盘节点是否执行 ✅ 实际遇到

### 错误现象
- 跑完一次请求后，只看到模型输出；无法从服务日志确认是否执行了 `review_case` / `write_excel`
- 排障时只能“猜测是不是没走到工作流/是不是解析失败”

### 解决方案
- 在关键节点加最小必要的 INFO 日志：入口预处理、评审轮次、写入路径与用例数量
- 日志要“结构化 + 可定位”，不要打印大段内容（避免污染 log / 影响性能）

示意（本仓库落地）：
```python
_LOGGER.info("testcase_flow.review_case: round=%s doc_id=%s", round, doc_id)
_LOGGER.info("testcase_flow.write_excel: cases=%s path=%s", len(cases), file_path)
```

### 面试要点
- LangGraph 是状态机：排障首先看“走了哪条边、执行了哪个节点、state 更新了什么”
- 可观测性是工程化必答题：没有日志就没有可复现性

---

## 12. 用例过于笼统：只写“展示弹窗”导致漏洞百出 ✅ 实际遇到

### 错误现象
- 用例只写“点击按钮 → 展示弹窗”就结束，没有校验弹窗标题/字段/文案/金额规则/按钮状态
- PRD/原型存在“后台配置导致 UI 不同”（例如金额总和展示 vs 分开展示），但用例未拆分两种模式覆盖

### 根因
- 生成 prompt 没有把“可验证性”落实到**硬性规则**；评审也缺少“质量门禁”，容易被模型一句“通过”放行
- 对配置差异/分支覆盖缺少确定性约束，导致漏测

### 解决方案（本仓库落地）
1) **生成阶段强约束**：弹窗必须写清标题/字段/按钮/文案/金额规则；配置差异必须拆分用例覆盖  
2) **评审阶段质量门禁**：对“泛化预期/未覆盖配置差异/关联内容缺失”等直接判 `不通过`，强制进入修订回路  

关键代码（示意）：
```python
# graphs_examples/testcase_flow.py
ok, problems, add_suggestions = _quality_gate(cases, prd_context=prd_context)
if not ok:
    return AIMessage(content="- 评审结论：不通过 ...")  # ✅ 强制修订
```

### 面试要点
- “测试用例可执行/可验证”必须在工程上落地为门禁，而不是靠模型自觉
- 配置差异/流程分支属于典型漏测点：必须“每个分支路径至少 1 条用例”+“不同配置值拆分用例”

---

## 13. PRD 功能点/入口路径覆盖依赖模型输出：漏掉“拼拼生活卡/大转盘”等 ✅ 实际遇到

### 错误现象
- PRD 明确存在多个功能点/入口路径（例如：`CMS -> 营销互动 -> 拼拼生活卡（新）`、`CMS -> 拼拼互动游戏 -> 大转盘`、`拼拼小程序 -> 大转盘 -> 获得更多抽奖机会`），但生成的用例表只覆盖局部功能点。
- 评审回路迭代多轮后仍有遗漏，最终写入 Excel 的用例文件也出现“漏功能入口/漏分支”。

### 根因
- 功能点/路径提取过度依赖某一种文档结构（例如仅依赖 `###` 标题），导致 PRD 中的路径信息被漏采集。
- 将“PRD 全量覆盖”作为 LLM 输出表格的硬性要求：当路径数量较多时，LLM 很难在单次表格里稳定写全，导致评审回路反复。
- 写入 Excel 节点缺少“确定性补齐”：即使评审发现缺失，也无法保证最终落盘文件覆盖所有入口路径。

### 解决方案（本仓库落地）
1) **PRD 功能点/入口路径清单确定性提取**：合并 `notes.md + answer.md + chunks.jsonl` 三源文本，支持多种路径格式（`路径/功能入口: ...` + 多级 `A -> B -> C` 兜底），并按 path 归一化去重。
2) **评审门禁职责收敛**：评审节点聚焦“可执行性/可验证性”（缺少关联内容、步骤/预期过短、弹窗预期泛化等作为硬问题）；“覆盖缺失”作为可自动补齐项进入漏测建议，不再把评审回路卡死在“写全所有路径”上。
3) **写入节点自动补齐（最终文件兜底）**：写入 Excel 前对缺失入口路径生成 `TC-AUTO-*` 基线用例；对“金额总和/分开展示”差异与流程分支清单也做自动补齐；在 `评审记录` Sheet 落盘自动补齐数量，保证结果可追溯。
4) **多模态强制解析兜底**：测试用例工作流入口可绕过 `PDF_IMAGES_MODE=never`，避免流程图/原型图关键分支信息丢失。

### 面试要点
- “覆盖完整性”不要完全交给 LLM；应有确定性提取 + 写入前兜底补齐，保证最终产物稳定。
- 评审节点应可判定、可复现、可解释：硬门禁尽量用确定性规则，而不是让 LLM 自评“通过/不通过”。

---

## 完整工作流骨架（本仓库实际落地版本）

### 入口路由（detect → testcase_flow）
`graphs_examples/document_call.py`
```python
graph.add_conditional_edges(
    "detect",
    route_edge,
    {
        "image": "image_chat",
        "file": "file_chat",
        "chat": "chat",
        "testcase": "preprocess_pdf",  # ✅ 触发“生成用例/评审/写Excel”工作流
    },
)
```

### 用例工作流（生成 → 评审 → 修订 → 写入 Excel）
`graphs_examples/document_call.py`
```python
graph.add_edge("preprocess_pdf", "prepare_case_context")
graph.add_edge("prepare_case_context", "write_case")
graph.add_edge("write_case", "review_case")
graph.add_conditional_edges(
    "review_case",
    testcase_condition_edge,  # ✅ 通过/不通过 + 轮次上限
    {"write_excel": "write_excel", "revise_case": "revise_case"},
)
graph.add_edge("revise_case", "review_case")
```

### 写 Excel 的“确定性落盘”要点（避免把解析交给 LLM）
`graphs_examples/testcase_flow.py`
```python
cases = _parse_test_cases_from_markdown(latest_table_text)  # ✅ 解析 Markdown 表格
save_test_cases_to_excel(cases, file_path=..., sheet_name="测试用例", mode="overwrite")
save_test_cases_to_excel([review_row], file_path=..., sheet_name="评审记录", mode="append")
```

---

## 高频追问 Q&A（面试官常问）

### Q1：为什么节点必须返回 dict？
A：LangGraph 节点输出是 **state 的 partial update**。引擎需要一个 `dict` 来合并到各 channel；返回 None/非 dict 会触发 `InvalidUpdateError`，因为引擎无法推断要更新哪些字段。

### Q2：`MessagesState.messages` 的合并语义是什么？
A：默认用 `add_messages` reducer：按 `message.id` 合并；id 相同覆盖更新，否则追加。这个语义既支持“对话累积”，也支持“原消息被预处理更新”（例如把 PDF block 替换成文本）。

### Q3：ToolNode 和 `create_agent` 有什么区别？
A：ToolNode 是图里的节点实现：执行 `AIMessage.tool_calls` 并产出 `ToolMessage`；`create_agent` 是 Runnable/Agent：包含提示词与工具选择策略，输入通常是 dict（例如 `{"messages": [...]}`）。

### Q4：为什么会出现 `unknown variant image_url/file` 的 400？怎么修？
A：因为某些网关/文本模型只接受 text/str；前端多模态会把 content 变成 block list（`image_url`/`file`）。修法是把多模态统一“降级成字符串”，放在 `before_model` 或图入口节点做最稳。

### Q5：评审-修订回路如何保证终止？
A：引入 state 字段（如 `review_count`）做上限；条件边里“通过 → 写入/结束；不通过 → 修订；超过 N 轮 → 强制落盘并提示风险”。

### Q6：前端为什么会卡死？你怎么验证修复有效？
A：流式 per-token 触发渲染 + Markdown 解析/高亮导致渲染风暴，工具大结果解析阻塞主线程。验证用 Performance/React Profiler 看渲染频率、主线程占用与掉帧情况；修复思路是节流（rAF）、大文本降级 `<pre>`、工具结果解析阈值保护。

### Q7：面试问“怎么提高知识库（RAG/需求库）的文档质量”？
A：可以把“文档质量”拆成四个指标：**可检索（能搜到）**、**可执行（能落地）**、**可追溯（有来源）**、**可演进（能持续更新）**。常用做法：
- **缺口驱动补齐（你提到的思路）**：生成/问答前先输出“待确认问题/不确定点”，把问题归因到“缺字段/缺规则/缺入口/缺异常分支”，再把补齐后的结论回写知识库并标注来源。
- **结构化模板 + 门禁**：为每类知识（PRD、接口、流程、原型、用例）定义必填字段（入口路径、权限、字段/校验、分支、错误码、边界、示例），用 lint/CI 做“缺字段即失败”。
- **确定性抽取优先，模型只做归纳**：入口路径/分支清单/错误码/文案变更尽量用规则抽取或工具解析，LLM 负责命名/归纳/补充说明，降低“漏采集 + 幻觉”。
- **可追溯引用**：知识条目必须带“来源指针”（DOC_ID/章节/截图页码/接口链接/PRD版本/commit），并保留“原文摘录”，避免知识漂移。
- **反馈闭环**：记录检索/问答的 miss（搜不到、答不出、答错）与用户追问，把 miss 自动转成待补文档任务（按频次与影响排序）。
- **去重与术语治理**：统一命名（同义词表/别名映射）、标签体系与模块边界；把相同概念合并到单一“权威条目”，其他地方只引用。
- **可执行性校验**：对关键文档做“文档测试”（示例请求能跑、步骤能复现、字段/文案与原型一致）；把用例/脚本/断言作为文档的一部分一起维护。
- **时效性管理**：设置 owner、review 周期与过期策略（TTL）；对长期未更新但高频命中的条目做过期提醒/自动标黄。

### Q8：怎么规范 PRD 编写，让知识库更“可检索/可执行”？
A：核心是把 PRD 写成“可被抽取、可被验证”的结构化输入，避免留给后续分析太多自由度。
- **结构模板（建议强制）**：背景/目标 → 范围&非范围 → 角色&权限 → 功能清单（Feature ID）→ 入口路径（CMS/小程序/APP 等分别列）→ 主流程/状态机（分支条件显式）→ 原型&交互细节（弹窗：标题/字段/按钮/文案/关闭行为）→ 业务规则&配置项（枚举/默认值/生效范围）→ 接口&数据（请求/响应/错误码/幂等）→ 埋点&日志 → 验收标准（可测试）→ 待确认问题（owner+截止时间）→ 变更记录。
- **可检索约束**：所有入口路径用统一格式（`A -> B -> C`），关键词字段/错误码/文案“原样给出”，避免“类似/大概/可能”。
- **可执行约束**：每条规则都给触发条件与预期结果；每个配置开关都写清“值域 + 默认值 + UI 差异 + 影响范围”。
- **可追溯约束**：每个原型/流程图引用要有页码/链接/版本号；PRD 顶部必须有版本号与变更摘要。
- **门禁方式**：PRD lint（缺入口/缺分支/缺验收标准即失败）+ PR 模板 checklist（PRD/知识库/用例同时更新）。

### Q9：功能变更后，怎么保证相关功能能及时更新到知识库？
A：要同时解决“触发时机（什么时候更新）”和“更新动作（怎么更新不漏）”。推荐一套 DoD + 自动化闭环：
- **DoD（Definition of Done）**：任何功能变更合并必须同时满足：PRD 变更记录更新、知识库条目更新、回归用例/自动化/监控点同步更新；否则不允许合并。
- **责任制**：知识库条目有 owner；变更 PR 里显式写“影响的 Feature ID/入口路径/API”，并指派 owner 评审知识库更新。
- **自动触发**：CI 根据 `git diff` 自动判断是否需要更新知识库：
  - 变更了路由/页面/接口/配置枚举 → 必须同时变更对应 PRD/KB 文件；
  - 只改实现细节但不影响行为 → 允许不更新，但必须在 PR 里声明“不影响外部行为”的证据（测试/截图）。
- **自动抽取 + 覆盖校验**：从 PRD/解析产物中确定性抽取“功能点/入口路径/分支清单”，做覆盖对账；缺失则自动生成待补任务或兜底基线用例（并在 KB 中记录补齐痕迹与原因）。
- **索引与时效**：知识入库要带版本号/时间戳/来源指针；索引增量更新；对高频命中条目做过期提醒。

归纳：**结构化 PRD（可抽取） + 变更门禁（DoD/CI） + 确定性抽取与覆盖对账（不靠模型自觉） + 可追溯与时效治理（能持续演进）**。

---

**文档版本**：v2.4（实战版）
**创建日期**：2025-12-15
**最后更新**：2025-12-23
**适用场景**：LangGraph 开发、技术面试准备
**基于项目**：测试用例自动生成工作流

