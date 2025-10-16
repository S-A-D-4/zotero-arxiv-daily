from typing import Optional
from functools import cached_property
from tempfile import TemporaryDirectory
import arxiv
import tarfile
import re
import time
from llm import get_llm
import requests
from requests.adapters import HTTPAdapter, Retry
from loguru import logger
import tiktoken
from contextlib import ExitStack
from urllib.error import HTTPError
from enum import Enum


class PaperType(Enum):
    """论文类型枚举"""
    SOLUTION_TYPE = "solution"      # 解决方案型：提出新方法、算法或框架
    EXPLORATORY_TYPE = "exploratory"  # 探究型：实验分析、数据探索或理论验证
    UNKNOWN = "unknown"             # 未知类型


class ArxivPaper:
    def __init__(self,paper:arxiv.Result):
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
        return re.sub(r'v\d+$', '', self._paper.get_short_id())
    
    @property
    def entry_id(self) -> str:
        return self._paper.entry_id

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
                title=self.title,
                abstract=self.summary,
                content=tex_content
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
                logger.warning(f"Paper {self.arxiv_id} classified as {classification_result}, defaulting to UNKNOWN")

        except Exception as e:
            logger.error(f"Error classifying paper {self.arxiv_id}: {e}")
            self._paper_type = PaperType.UNKNOWN

        return self._paper_type

    @cached_property
    def code_url(self) -> Optional[str]:
        s = requests.Session()
        retries = Retry(total=5, backoff_factor=0.1)
        s.mount('https://', HTTPAdapter(max_retries=retries))
        try:
            paper_list = s.get(f'https://paperswithcode.com/api/v1/papers/?arxiv_id={self.arxiv_id}').json()
        except Exception as e:
            logger.debug(f'Error when searching {self.arxiv_id}: {e}')
            return None

        if paper_list.get('count',0) == 0:
            return None
        paper_id = paper_list['results'][0]['id']

        try:
            repo_list = s.get(f'https://paperswithcode.com/api/v1/papers/{paper_id}/repositories/').json()
        except Exception as e:
            logger.debug(f'Error when searching {self.arxiv_id}: {e}')
            return None
        if repo_list.get('count',0) == 0:
            return None
        return repo_list['results'][0]['url']
    
    @cached_property
    def tex(self) -> dict[str,str]:
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
                    logger.warning(f"Source for {self.arxiv_id} not found (404). Skipping source analysis.")
                    return None # 直接返回 None，后续依赖 tex 的代码会安全地处理
                else:
                    # 如果是其他 HTTP 错误 (如 503)，这可能是临时性问题，值得记录下来
                    logger.error(f"HTTP Error {e.code} when downloading source for {self.arxiv_id}: {e.reason}")
                    raise # 重新抛出异常，因为这可能是个需要关注的严重问题
            try:
                tar = stack.enter_context(tarfile.open(file))
            except tarfile.ReadError:
                logger.debug(f"Failed to find main tex file of {self.arxiv_id}: Not a tar file.")
                return None
 
            tex_files = [f for f in tar.getnames() if f.endswith('.tex')]
            if len(tex_files) == 0:
                logger.debug(f"Failed to find main tex file of {self.arxiv_id}: No tex file.")
                return None
            
            bbl_file = [f for f in tar.getnames() if f.endswith('.bbl')]
            match len(bbl_file) :
                case 0:
                    if len(tex_files) > 1:
                        logger.debug(f"Cannot find main tex file of {self.arxiv_id} from bbl: There are multiple tex files while no bbl file.")
                        main_tex = None
                    else:
                        main_tex = tex_files[0]
                case 1:
                    main_name = bbl_file[0].replace('.bbl','')
                    main_tex = f"{main_name}.tex"
                    if main_tex not in tex_files:
                        logger.debug(f"Cannot find main tex file of {self.arxiv_id} from bbl: The bbl file does not match any tex file.")
                        main_tex = None
                case _:
                    logger.debug(f"Cannot find main tex file of {self.arxiv_id} from bbl: There are multiple bbl files.")
                    main_tex = None
            if main_tex is None:
                logger.debug(f"Trying to choose tex file containing the document block as main tex file of {self.arxiv_id}")
            #read all tex files
            file_contents = {}
            for t in tex_files:
                f = tar.extractfile(t)
                content = f.read().decode('utf-8',errors='ignore')
                #remove comments
                content = re.sub(r'%.*\n', '\n', content)
                content = re.sub(r'\\begin{comment}.*?\\end{comment}', '', content, flags=re.DOTALL)
                content = re.sub(r'\\iffalse.*?\\fi', '', content, flags=re.DOTALL)
                #remove redundant \n
                content = re.sub(r'\n+', '\n', content)
                content = re.sub(r'\\\\', '', content)
                #remove consecutive spaces
                content = re.sub(r'[ \t\r\f]{3,}', ' ', content)
                if main_tex is None and re.search(r'\\begin\{document\}', content):
                    main_tex = t
                    logger.debug(f"Choose {t} as main tex file of {self.arxiv_id}")
                file_contents[t] = content
            
            if main_tex is not None:
                main_source:str = file_contents[main_tex]
                #find and replace all included sub-files
                include_files = re.findall(r'\\input\{(.+?)\}', main_source) + re.findall(r'\\include\{(.+?)\}', main_source)
                for f in include_files:
                    if not f.endswith('.tex'):
                        file_name = f + '.tex'
                    else:
                        file_name = f
                    main_source = main_source.replace(f'\\input{{{f}}}', file_contents.get(file_name, ''))
                file_contents["all"] = main_source
            else:
                logger.debug(f"Failed to find main tex file of {self.arxiv_id}: No tex file containing the document block.")
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
            content = re.sub(r'~?\\cite.?\{.*?\}', '', content)
            # Remove figure environments but keep captions
            content = re.sub(r'\\begin\{figure\}.*?\\end\{figure\}', '', content, flags=re.DOTALL)
            # Remove table environments but keep captions
            content = re.sub(r'\\begin\{table\}.*?\\end\{table\}', '', content, flags=re.DOTALL)
            # Remove equation environments (keep inline math)
            content = re.sub(r'\\begin\{equation\}.*?\\end\{equation\}', '', content, flags=re.DOTALL)
            content = re.sub(r'\\begin\{align\}.*?\\end\{align\}', '', content, flags=re.DOTALL)
            # Remove bibliography and appendix sections
            content = re.sub(r'\\bibliography\{.*?\}.*$', '', content, flags=re.DOTALL)
            content = re.sub(r'\\appendix.*$', '', content, flags=re.DOTALL)
            # Clean up LaTeX commands that don't add content value
            content = re.sub(r'\\[a-zA-Z]+\*?\{[^}]*\}', ' ', content)  # Remove most LaTeX commands
            content = re.sub(r'\\[a-zA-Z]+\*?', ' ', content)  # Remove LaTeX commands without braces
            # Clean up formatting
            content = re.sub(r'\s+', ' ', content)  # Normalize whitespace
            content = content.strip()

            full_content = content

        # If no LaTeX content available, use the abstract
        if not full_content.strip():
            full_content = self.summary

        llm = get_llm()

        # 根据论文类型生成不同格式的摘要
        paper_type = self.paper_type

        if paper_type == PaperType.SOLUTION_TYPE:
            # 解决方案型论文的提示词
            system_prompt = "你是一个专业的学术分析师，请仔细阅读这篇解决方案型论文，并按照以下结构抽取论文内容：需要解决的问题、现有方案的缺点、新方案的创新点。每个部分都要简明易懂，总字数控制在500字左右。"
            user_prompt = f"""论文标题：{self.title}

论文摘要：{self.summary}

论文完整内容：{full_content}

请按照以下格式抽取论文内容：

**需要解决的问题**
（明确说明论文要解决的核心问题）

**现有方案的缺点**
（分析当前存在方法或方案的不足）

**新方案的创新点**
（突出论文提出的新方法的创新之处，需要详细说明）"""

        elif paper_type == PaperType.EXPLORATORY_TYPE:
            # 探究型论文的提示词
            system_prompt = "你是一个专业的学术分析师，请仔细阅读这篇探究型论文，并按照以下结构抽取论文内容：探究的问题、实验结论。每个部分都要简明易懂，总字数控制在400字左右。"
            user_prompt = f"""论文标题：{self.title}

论文摘要：{self.summary}

论文完整内容：{full_content}

请按照以下格式抽取论文内容：

**探究的问题**
（描述论文要研究或验证的问题）

**实验结论**
（总结实验结果和发现）"""

        else:
            # 未知类型或回退到原始格式
            system_prompt = "仔细阅读这篇论文，并写一篇文章介绍该,600字以内。"
            user_prompt = f"""Paper Title: {self.title}

Paper Abstract: {self.summary}

Full Paper Content: {full_content}

Please write in {llm.lang}:"""

        article = llm.generate(
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {"role": "user", "content": user_prompt},
            ]
        )
        return article

    @cached_property
    def tldr(self) -> str:
        """Backward compatibility - returns the article content."""
        return self.article

