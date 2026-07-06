import re
import tarfile
from contextlib import ExitStack
from enum import Enum
from functools import cached_property
from tempfile import TemporaryDirectory
from typing import Optional
from urllib.error import HTTPError

import arxiv
import requests
from loguru import logger
from requests.adapters import HTTPAdapter, Retry

from llm import get_llm


class PaperType(Enum):
    """论文类型枚举"""

    SOLUTION_TYPE = "solution"  # 解决方案型：提出新方法、算法或框架
    EXPLORATORY_TYPE = "exploratory"  # 探究型：实验分析、数据探索或理论验证
    UNKNOWN = "unknown"  # 未知类型


class ArxivPaper:
    def __init__(self, paper: arxiv.Result):
        self._paper = paper
        self.score = None
        self._paper_type = None  # 缓存论文类型

    @property
    def title(self) -> str:
        return self._paper.title

    @property
    def summary(self) -> str:
        return self._paper.summary

    @property
    def authors(self) -> list[str]:
        return self._paper.authors

    @cached_property
    def arxiv_id(self) -> str:
        return re.sub(r"v\d+$", "", self._paper.get_short_id())

    @cached_property
    def entry_id(self) -> str:
        # 移除版本号，生成不带版本的链接
        original_id = self._paper.entry_id
        # 匹配各种格式中的版本号：v1, v2, v10等
        return re.sub(r"v\d+$", "", original_id)

    @cached_property
    def paper_type(self) -> PaperType:
        """识别论文类型：解决方案型或探究型"""
        if self._paper_type is not None:
            return self._paper_type

        try:
            llm = get_llm()

            # 准备论文内容用于分类
            tex_content = None
            if self.tex and self.tex.get("all"):
                tex_content = self.tex.get("all")

            # 使用LLM专用分类方法
            classification_result = llm.classify_paper_type(
                title=self.title, abstract=self.summary, content=tex_content
            )

            # 根据分类结果设置论文类型
            if classification_result == "solution":
                self._paper_type = PaperType.SOLUTION_TYPE
                logger.info(f"Paper {self.arxiv_id} classified as SOLUTION_TYPE")
            elif classification_result == "exploratory":
                self._paper_type = PaperType.EXPLORATORY_TYPE
                logger.info(f"Paper {self.arxiv_id} classified as EXPLORATORY_TYPE")
            else:
                self._paper_type = PaperType.UNKNOWN
                logger.warning(
                    f"Paper {self.arxiv_id} classified as {classification_result}, defaulting to UNKNOWN"
                )

        except Exception as e:
            logger.error(f"Error classifying paper {self.arxiv_id}: {e}")
            self._paper_type = PaperType.UNKNOWN

        return self._paper_type

    @cached_property
    def code_url(self) -> Optional[str]:
        s = requests.Session()
        retries = Retry(total=5, backoff_factor=0.1)
        s.mount("https://", HTTPAdapter(max_retries=retries))
        try:
            paper_list = s.get(
                f"https://paperswithcode.com/api/v1/papers/?arxiv_id={self.arxiv_id}"
            ).json()
        except Exception as e:
            logger.debug(f"Error when searching {self.arxiv_id}: {e}")
            return None

        if paper_list.get("count", 0) == 0:
            return None
        paper_id = paper_list["results"][0]["id"]

        try:
            repo_list = s.get(
                f"https://paperswithcode.com/api/v1/papers/{paper_id}/repositories/"
            ).json()
        except Exception as e:
            logger.debug(f"Error when searching {self.arxiv_id}: {e}")
            return None
        if repo_list.get("count", 0) == 0:
            return None
        return repo_list["results"][0]["url"]

    @cached_property
    def tex(self) -> dict[str, str]:
        with ExitStack() as stack:
            tmpdirname = stack.enter_context(TemporaryDirectory())
            # file = self._paper.download_source(dirpath=tmpdirname)
            try:
                # 尝试下载源文件
                file = self._paper.download_source(dirpath=tmpdirname)
            except HTTPError as e:
                # 捕获 HTTP 错误
                if e.code == 404:
                    # 如果是 404 Not Found，说明源文件不存在，这是正常情况
                    logger.warning(
                        f"Source for {self.arxiv_id} not found (404). Skipping source analysis."
                    )
                    return None  # 直接返回 None，后续依赖 tex 的代码会安全地处理
                else:
                    # 如果是其他 HTTP 错误 (如 503)，这可能是临时性问题，值得记录下来
                    logger.error(
                        f"HTTP Error {e.code} when downloading source for {self.arxiv_id}: {e.reason}"
                    )
                    raise  # 重新抛出异常，因为这可能是个需要关注的严重问题
            try:
                tar = stack.enter_context(tarfile.open(file))
            except tarfile.ReadError:
                logger.debug(
                    f"Failed to find main tex file of {self.arxiv_id}: Not a tar file."
                )
                return None

            tex_files = [f for f in tar.getnames() if f.endswith(".tex")]
            if len(tex_files) == 0:
                logger.debug(
                    f"Failed to find main tex file of {self.arxiv_id}: No tex file."
                )
                return None

            bbl_file = [f for f in tar.getnames() if f.endswith(".bbl")]
            match len(bbl_file):
                case 0:
                    if len(tex_files) > 1:
                        logger.debug(
                            f"Cannot find main tex file of {self.arxiv_id} from bbl: There are multiple tex files while no bbl file."
                        )
                        main_tex = None
                    else:
                        main_tex = tex_files[0]
                case 1:
                    main_name = bbl_file[0].replace(".bbl", "")
                    main_tex = f"{main_name}.tex"
                    if main_tex not in tex_files:
                        logger.debug(
                            f"Cannot find main tex file of {self.arxiv_id} from bbl: The bbl file does not match any tex file."
                        )
                        main_tex = None
                case _:
                    logger.debug(
                        f"Cannot find main tex file of {self.arxiv_id} from bbl: There are multiple bbl files."
                    )
                    main_tex = None
            if main_tex is None:
                logger.debug(
                    f"Trying to choose tex file containing the document block as main tex file of {self.arxiv_id}"
                )
            # read all tex files
            file_contents = {}
            for t in tex_files:
                f = tar.extractfile(t)
                content = f.read().decode("utf-8", errors="ignore")
                # remove comments
                content = re.sub(r"%.*\n", "\n", content)
                content = re.sub(
                    r"\\begin{comment}.*?\\end{comment}", "", content, flags=re.DOTALL
                )
                content = re.sub(r"\\iffalse.*?\\fi", "", content, flags=re.DOTALL)
                # remove redundant \n
                content = re.sub(r"\n+", "\n", content)
                content = re.sub(r"\\\\", "", content)
                # remove consecutive spaces
                content = re.sub(r"[ \t\r\f]{3,}", " ", content)
                if main_tex is None and re.search(r"\\begin\{document\}", content):
                    main_tex = t
                    logger.debug(f"Choose {t} as main tex file of {self.arxiv_id}")
                file_contents[t] = content

            if main_tex is not None:
                main_source: str = file_contents[main_tex]
                # find and replace all included sub-files
                include_files = re.findall(
                    r"\\input\{(.+?)\}", main_source
                ) + re.findall(r"\\include\{(.+?)\}", main_source)
                for f in include_files:
                    if not f.endswith(".tex"):
                        file_name = f + ".tex"
                    else:
                        file_name = f
                    main_source = main_source.replace(
                        f"\\input{{{f}}}", file_contents.get(file_name, "")
                    )
                file_contents["all"] = main_source
            else:
                logger.debug(
                    f"Failed to find main tex file of {self.arxiv_id}: No tex file containing the document block."
                )
                file_contents["all"] = None
        return file_contents

    @cached_property
    def article(self) -> str:
        """Generate a detailed article about the paper's key points using the full paper content."""
        full_content = ""

        # Get the full paper content
        if self.tex is not None:
            content = self.tex.get("all")
            if content is None:
                content = "\n".join(self.tex.values())

            # Clean up the content
            # Remove citations
            content = re.sub(r"~?\\cite.?\{.*?\}", "", content)
            # Remove figure environments but keep captions
            content = re.sub(
                r"\\begin\{figure\}.*?\\end\{figure\}", "", content, flags=re.DOTALL
            )
            # Remove table environments but keep captions
            content = re.sub(
                r"\\begin\{table\}.*?\\end\{table\}", "", content, flags=re.DOTALL
            )
            # Remove equation environments (keep inline math)
            content = re.sub(
                r"\\begin\{equation\}.*?\\end\{equation\}", "", content, flags=re.DOTALL
            )
            content = re.sub(
                r"\\begin\{align\}.*?\\end\{align\}", "", content, flags=re.DOTALL
            )
            # Remove bibliography and appendix sections
            content = re.sub(r"\\bibliography\{.*?\}.*$", "", content, flags=re.DOTALL)
            content = re.sub(r"\\appendix.*$", "", content, flags=re.DOTALL)
            # Clean up LaTeX commands that don't add content value
            content = re.sub(
                r"\\[a-zA-Z]+\*?\{[^}]*\}", " ", content
            )  # Remove most LaTeX commands
            content = re.sub(
                r"\\[a-zA-Z]+\*?", " ", content
            )  # Remove LaTeX commands without braces
            # Clean up formatting
            content = re.sub(r"\s+", " ", content)  # Normalize whitespace
            content = content.strip()

            full_content = content

        # If no LaTeX content available, use the abstract
        if not full_content.strip():
            full_content = self.summary

        llm = get_llm()

        # 根据论文类型生成不同格式的摘要
        paper_type = self.paper_type

        if paper_type == PaperType.SOLUTION_TYPE:
            # 解决方案型论文的提示词 - 输出HTML格式
            system_prompt = "请仔细阅读这篇解决方案型论文，并生成HTML格式的结构化摘要，不要输出其他内容。使用简明易懂、易于理解的语言和表达，总字数控制在500字左右。"
            user_prompt = f"""
以下是一些对你的知识补充，用于告知你近期已出现而你的知识库未更新的知识，它可能有用，也可能没用：

<知识补充>
### 1. 编排工程（Harness Engineering）
这是一个全新的系统层抽象，它标志着关注点从 **“如何对模型说话”** 转向了 **“为模型营造一个什么样的工作环境”**。
解释不再是绞尽脑汁写提示词，而是像给新员工准备工位一样，为模型构建一个清晰、可验证的执行环境。这包括规划好代码仓库结构、把CI（持续集成）流水线和自动化测试配置好、设定明确的架构约束。这个概念的核心洞见在于，要让智能体可靠，重点不是教育它，而是**约束它的工作边界并建立实时的反馈回路**，让它能在犯错后立刻看到错误并自我修正。

### 2. 技能（Skill）
在“编排工程”这个大环境设定好后，**技能**是具体执行任务时的能力层抽象。它超越了传统的“提示词模板”，更像是一个可复用的**业务能力单元**。
一个技能包里不仅包含任务流程，还把格式要求、模板、范例、检查规则甚至必要的工具访问权限都封装在一起。它的价值是解决企业应用中的现实痛点：团队成员不再需要各自去复制粘贴复杂的提示词，也不会因为提示词的微小变动而导致输出格式漂移。本质上，它让任务经验变成了模型可以随时调用的、标准化的**组织知识微服务**。

### 3. 推理能力的预算化与调度化
这打破了“让模型多想一会儿”的笼统概念，转而把推理视为一种可以**精细管理和分配的计算资源**。
就像你不会统计一记重锤和轻敲桌面消耗的卡路里一样，这种观点认为，简单问候不该消耗大量后台算力，而复杂的数学证明则需要模型能自适应地展开更长的“思维链”。报告中提到的“实时路由”和“并行测试时计算”就是其技术实现，它像一个智能资源调度器，让推理成本成为一笔能计算、能优化的账，以保证整个系统经济、高效地运行。
</知识补充>

---

以下是你需要解读的论文：

论文标题：{self.title}

论文摘要：{self.summary}

论文完整内容：{full_content}

请生成HTML格式的论文分析，包含以下三部分结构：
⚠️ 现有方案的缺点
（填充：分析当前存在方法或方案的不足）
💡 新方案的设计理念
（填充：阐述新方案的核心思想和设计原则）
🔧 新方案的实现方式
（填充：说明新方案的具体实现方法和关键技术）

请直接输出HTML代码，在填充部分可以使用合适美观的HTML标签格式组织内容。"""

        elif paper_type == PaperType.EXPLORATORY_TYPE:
            # 探究型论文的提示词 - 输出HTML格式
            system_prompt = "请仔细阅读这篇探究型论文，并生成HTML格式的结构化摘要，不要输出其他内容。使用简明易懂、易于理解的语言和表达，总字数控制在400字左右。"
            user_prompt = f"""
以下是一些对你的知识补充，用于告知你近期已出现而你的知识库未更新的知识，它可能有用，也可能没用：

<知识补充>
### 1. 编排工程
这是一个全新的系统层抽象，它标志着关注点从 **“如何对模型说话”** 转向了 **“为模型营造一个什么样的工作环境”**。
解释不再是绞尽脑汁写提示词，而是像给新员工准备工位一样，为模型构建一个清晰、可验证的执行环境。这包括规划好代码仓库结构、把CI（持续集成）流水线和自动化测试配置好、设定明确的架构约束。这个概念的核心洞见在于，要让智能体可靠，重点不是教育它，而是**约束它的工作边界并建立实时的反馈回路**，让它能在犯错后立刻看到错误并自我修正。

### 2. 技能
在“编排工程”这个大环境设定好后，**技能**是具体执行任务时的能力层抽象。它超越了传统的“提示词模板”，更像是一个可复用的**业务能力单元**。
一个技能包里不仅包含任务流程，还把格式要求、模板、范例、检查规则甚至必要的工具访问权限都封装在一起。它的价值是解决企业应用中的现实痛点：团队成员不再需要各自去复制粘贴复杂的提示词，也不会因为提示词的微小变动而导致输出格式漂移。本质上，它让任务经验变成了模型可以随时调用的、标准化的**组织知识微服务**。

### 3. 推理能力的预算化与调度化
这打破了“让模型多想一会儿”的笼统概念，转而把推理视为一种可以**精细管理和分配的计算资源**。
就像你不会统计一记重锤和轻敲桌面消耗的卡路里一样，这种观点认为，简单问候不该消耗大量后台算力，而复杂的数学证明则需要模型能自适应地展开更长的“思维链”。报告中提到的“实时路由”和“并行测试时计算”就是其技术实现，它像一个智能资源调度器，让推理成本成为一笔能计算、能优化的账，以保证整个系统经济、高效地运行。
</知识补充>

---

以下是你需要解读的论文：

论文标题：{self.title}

论文摘要：{self.summary}

论文完整内容：{full_content}

请生成HTML格式的论文分析，包含以下两部分结构：
🔍 探究的问题
（填充：描述论文要研究或验证的问题）
📊 实验结论
（填充：总结实验结果和发现）

请直接输出HTML代码，在填充部分可以使用合适美观的HTML标签格式组织内容。"""

        else:
            # 未知类型或回退到HTML格式
            system_prompt = "请仔细阅读这篇论文，并生成HTML格式的摘要，不要输出其他内容。总字数控制在600字以内。"
            user_prompt = f"""论文标题：{self.title}

论文摘要：{self.summary}

论文完整内容：{full_content}

请生成HTML格式的论文摘要，遵循以下格式：
<div style="margin-bottom: 20px;">
<h3 style="color: #333; font-size: 16px; margin-bottom: 8px;">📄 论文摘要</h3>
（请在这里生成论文的摘要内容）
</div>

请使用{llm.lang}输出，并直接输出HTML内容。"""

        article = llm.generate(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
        )
        return article

    @cached_property
    def tldr(self) -> str:
        """Backward compatibility - returns the article content."""
        return self.article
