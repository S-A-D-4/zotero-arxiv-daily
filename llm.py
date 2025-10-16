from llama_cpp import Llama
from openai import OpenAI
from loguru import logger
from time import sleep

GLOBAL_LLM = None

class LLM:
    def __init__(self, api_key: str = None, base_url: str = None, model: str = None,lang: str = "English"):
        if api_key:
            self.llm = OpenAI(api_key=api_key, base_url=base_url)
        else:
            self.llm = Llama.from_pretrained(
                repo_id="Qwen/Qwen2.5-3B-Instruct-GGUF",
                filename="qwen2.5-3b-instruct-q4_k_m.gguf",
                n_ctx=5_000,
                n_threads=4,
                verbose=False,
            )
        self.model = model
        self.lang = lang

    def generate(self, messages: list[dict]) -> str:
        if isinstance(self.llm, OpenAI):
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response = self.llm.chat.completions.create(messages=messages, temperature=0, model=self.model)
                    break
                except Exception as e:
                    logger.error(f"Attempt {attempt + 1} failed: {e}")
                    if attempt == max_retries - 1:
                        raise
                    sleep(3)
            return response.choices[0].message.content
        else:
            response = self.llm.create_chat_completion(messages=messages,temperature=0)
            return response["choices"][0]["message"]["content"]

    def classify_paper_type(self, title: str, abstract: str, content: str = None) -> str:
        """专门用于论文类型分类的方法

        Args:
            title: 论文标题
            abstract: 论文摘要
            content: 论文完整内容（可选）

        Returns:
            str: "solution" 或 "exploratory" 或 "unknown"
        """
        try:
            # 准备分类用的内容
            content_for_classification = abstract
            if content:
                # 限制内容长度以避免token过多
                limited_content = content[:2000]
                content_for_classification = f"{abstract}\n\n{limited_content}"

            # 构建分类提示词
            classification_prompt = f"""请分析以下论文并将其分类为两种类型之一：

论文标题：{title}
论文摘要：{abstract}

请判断这篇论文主要属于哪种类型：
1. 解决方案型：提出新方法、算法、框架或技术解决方案
2. 探究型：进行实验分析、数据探索、现象研究或理论验证

请只回答一个词：solution 或 exploratory"""

            result = self.generate([
                {
                    "role": "system",
                    "content": "你是一个专业的论文分类助手，需要准确判断论文类型。"
                },
                {"role": "user", "content": classification_prompt}
            ])

            # 解析结果
            result = result.strip().lower()
            if "solution" in result:
                return "solution"
            elif "exploratory" in result:
                return "exploratory"
            else:
                logger.warning(f"LLM classification returned unexpected result: {result}")
                return "unknown"

        except Exception as e:
            logger.error(f"Error in LLM paper classification: {e}")
            return "unknown"

def set_global_llm(api_key: str = None, base_url: str = None, model: str = None, lang: str = "English"):
    global GLOBAL_LLM
    GLOBAL_LLM = LLM(api_key=api_key, base_url=base_url, model=model, lang=lang)

def get_llm() -> LLM:
    if GLOBAL_LLM is None:
        logger.info("No global LLM found, creating a default one. Use `set_global_llm` to set a custom one.")
        set_global_llm()
    return GLOBAL_LLM