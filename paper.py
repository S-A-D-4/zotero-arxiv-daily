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



class ArxivPaper:
    def __init__(self,paper:arxiv.Result):
        self._paper = paper
        self.score = None
    
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
    def pdf_url(self) -> str:
        return self._paper.pdf_url
    
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

        # Create a comprehensive prompt for article generation
        prompt = """You are a scientific writing expert. Based on the provided paper content, write a comprehensive article that introduces the paper's key points, contributions, and significance. The article should be informative, well-structured, and accessible to researchers in the field.

Paper Title: __TITLE__

Paper Abstract: __ABSTRACT__

Full Paper Content: __CONTENT__

Please write a detailed article in __LANG__ that covers:
1. The main problem or research question addressed
2. Key contributions and novel approaches
3. Methodology and technical details (if applicable)
4. Important findings and results
5. Significance and potential impact

The article should be approximately 200-400 words, well-organized with clear paragraphs, and written in an engaging academic style."""

        prompt = prompt.replace('__LANG__', llm.lang)
        prompt = prompt.replace('__TITLE__', self.title)
        prompt = prompt.replace('__ABSTRACT__', self.summary)
        prompt = prompt.replace('__CONTENT__', full_content)

        # Use tokenizer for content management - increase limit for detailed articles
        enc = tiktoken.encoding_for_model("gpt-4o")
        prompt_tokens = enc.encode(prompt)

        article = llm.generate(
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert scientific writer who creates comprehensive, informative articles about research papers. Your articles are well-structured, engaging, and provide deep insights into the paper's contributions and significance.",
                },
                {"role": "user", "content": prompt},
            ]
        )
        return article

    @cached_property
    def tldr(self) -> str:
        """Backward compatibility - returns the article content."""
        return self.article

    @cached_property
    def affiliations(self) -> Optional[list[str]]:
        if self.tex is not None:
            content = self.tex.get("all")
            if content is None:
                content = "\n".join(self.tex.values())
            #search for affiliations
            possible_regions = [r'\\author.*?\\maketitle',r'\\begin{document}.*?\\begin{abstract}']
            matches = [re.search(p, content, flags=re.DOTALL) for p in possible_regions]
            match = next((m for m in matches if m), None)
            if match:
                information_region = match.group(0)
            else:
                logger.debug(f"Failed to extract affiliations of {self.arxiv_id}: No author information found.")
                return None
            prompt = f"Given the author information of a paper in latex format, extract the affiliations of the authors in a python list format, which is sorted by the author order. If there is no affiliation found, return an empty list '[]'. Following is the author information:\n{information_region}"
            # use gpt-4o tokenizer for estimation
            enc = tiktoken.encoding_for_model("gpt-4o")
            prompt_tokens = enc.encode(prompt)
            prompt_tokens = prompt_tokens[:4000]  # truncate to 4000 tokens
            prompt = enc.decode(prompt_tokens)
            llm = get_llm()
            affiliations = llm.generate(
                messages=[
                    {
                        "role": "system",
                        "content": "You are an assistant who perfectly extracts affiliations of authors from the author information of a paper. You should return a python list of affiliations sorted by the author order, like ['TsingHua University','Peking University']. If an affiliation is consisted of multi-level affiliations, like 'Department of Computer Science, TsingHua University', you should return the top-level affiliation 'TsingHua University' only. Do not contain duplicated affiliations. If there is no affiliation found, you should return an empty list [ ]. You should only return the final list of affiliations, and do not return any intermediate results.",
                    },
                    {"role": "user", "content": prompt},
                ]
            )

            try:
                affiliations = re.search(r'\[.*?\]', affiliations, flags=re.DOTALL).group(0)
                affiliations = eval(affiliations)
                affiliations = list(set(affiliations))
                affiliations = [str(a) for a in affiliations]
            except Exception as e:
                logger.debug(f"Failed to extract affiliations of {self.arxiv_id}: {e}")
                return None
            return affiliations
