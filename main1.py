from langchain.agents import create_agent
from src.file_rag.core.llms import get_default_model
model = get_default_model()
from tools import (
    get_weather,
    get_chrome_mcp_tools,
    get_mcp_server_chart_tools,
    save_test_cases_to_excel,
    save_and_generate_report
)

agent = create_agent(
    model=model,
    tools=[get_weather],
    system_prompt="You are a helpful assistant."
)

# Web UI自动化测试 Agent（增强版：支持测试用例保存和报告生成）
web_agent = create_agent(
    model=model,
    tools=get_mcp_server_chart_tools() + get_chrome_mcp_tools() + [save_test_cases_to_excel, save_and_generate_report],
    system_prompt="""你是一个专业的UI自动化测试助手。你可以：
1. 使用Chrome MCP工具进行UI自动化测试（浏览器操作、元素定位、交互等）
2. 使用图表工具生成可视化数据
3. 将测试用例保存到Excel文件（使用save_test_cases_to_excel工具）
4. 生成图文并茂的测试报告并保存到指定目录（使用save_and_generate_report工具）

当执行UI自动化测试时，你应该：
- 使用Chrome工具操作浏览器执行测试
- 记录每个测试用例的详细信息（用例ID、标题、步骤、预期结果、实际结果、状态等）
- 测试完成后，将测试用例保存到Excel文件
- 同时生成包含统计图表的HTML测试报告
- 所有文件保存到用户指定的目录

测试用例格式示例：
{
    "用例ID": "TC001",
    "用例标题": "登录功能测试",
    "前置条件": "用户未登录",
    "测试步骤": "1. 打开登录页\\n2. 输入用户名密码\\n3. 点击登录",
    "预期结果": "登录成功",
    "实际结果": "登录成功",
    "优先级": "高",
    "状态": "通过"
}

你应该友好、专业地与用户交互，提供清晰的测试执行反馈。"""
)

