import os
from langchain.chat_models import init_chat_model

os.environ["DEEPSEEK_API_KEY"] = "sk-cc45c76aaec442289ff4ff737c79ed53"

def get_default_model():
    return init_chat_model("deepseek:deepseek-chat")
