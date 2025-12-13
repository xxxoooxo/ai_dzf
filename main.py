from langchain.agents import create_agent
from llms import get_default_model
model = get_default_model()
from tools import get_weather,get_zhipu_search_mcp_tools,get_tavily_search_mcp_tools,get_chrome_mcp_tools,get_mcp_server_chart_tools

agent = create_agent(
    model=model,
    tools=[get_weather],
    system_prompt="You are a helpful assistant."
)

web_agent = create_agent(
    model=model,
    tools=get_mcp_server_chart_tools() + get_chrome_mcp_tools(),
    system_prompt="You are a helpful assistant."
)

