import os
from langchain.chat_models import init_chat_model
from langchain_openai import ChatOpenAI

os.environ["DEEPSEEK_API_KEY"] = "sk-cc45c76aaec442289ff4ff737c79ed53"

def get_default_model():
    return init_chat_model("deepseek:deepseek-chat")

def get_doubao_seed_model():
    return ChatOpenAI(model="doubao-seed-1-6-251015",
                      api_key="b024e922-a42a-46b6-b12b-8e17d28feb2f",
                      base_url="https://ark.cn-beijing.volces.com/api/v3")
