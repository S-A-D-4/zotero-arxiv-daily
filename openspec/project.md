# Project Context

## Purpose

**zotero-arxiv-daily** 是一个智能学术论文推荐系统，旨在帮助研究人员每天发现与其研究兴趣相关的新arXiv论文。系统通过分析用户的Zotero图书馆内容，利用向量化相似度计算推荐相关论文，并通过邮件发送包含AI生成摘要的推荐列表。

### 核心目标
- 零成本自动化：通过GitHub Actions实现完全免费的每日自动化运行
- 智能推荐：基于用户历史文献的语义相似度进行推荐
- AI增强：使用本地或云端LLM生成论文摘要和关键点分析
- 易于部署：用户只需fork仓库并配置环境变量即可使用

## Tech Stack

### 核心技术
- **Python 3.11+**：主要编程语言
- **uv**：现代Python包管理器，提供快速的依赖安装和环境管理
- **GitHub Actions**：CI/CD平台，提供免费的自动化运行环境

### AI和机器学习
- **sentence-transformers**：文本向量化，使用GIST-small-Embedding-v0模型
- **llama-cpp-python**：本地LLM推理，支持Qwen2.5-3B模型
- **OpenAI API**：云端LLM API支持，兼容多种服务商

### 数据处理和API
- **arxiv**：arXiv API客户端，获取最新论文
- **pyzotero**：Zotero API客户端，访问用户文献库
- **feedparser**：RSS feed解析，获取arXiv更新
- **scikit-learn**：机器学习工具，向量相似度计算

### 工具库
- **loguru**：结构化日志记录
- **tiktoken**：Token计算工具
- **gitignore-parser**：Gitignore模式解析
- **python-dotenv**：环境变量管理
- **requests**：HTTP客户端，支持重试机制

## Project Conventions

### Code Style
- **中文优先**：注释和文档优先使用中文编写
- **PEP 8兼容**：遵循Python代码规范
- **类型提示**：使用Python类型注解增强代码可读性
- **函数式编程**：适当使用高阶函数和列表推导式
- **缓存机制**：使用`@cached_property`优化重复计算

### Architecture Patterns

#### 模块化设计
- **单一职责**：每个模块负责特定功能领域
- **松耦合**：模块间通过明确的接口交互
- **依赖注入**：LLM管理器使用单例模式统一接口

#### 核心类设计
- **ArxivPaper类**：封装论文相关操作和数据
- **推荐算法**：向量化相似度计算 + 时间衰减权重
- **LLM管理**：统一接口支持本地和云端模型

#### 数据流架构
```
Zotero Library → Vector Embedding → Similarity Calculation → Top-N Papers → LLM Processing → Email
     ↓                  ↓                    ↓                    ↓              ↓
   Collection         Time Weight         Score Ranking      Summary Generation  SMTP
   Filter             Application         Selection          (Qwen2.5-3B)       Send
```

### Testing Strategy
- **测试工作流**：使用`.github/workflows/test.yml`进行功能验证
- **调试模式**：支持固定论文数量测试，便于功能验证
- **日志调试**：使用loguru进行详细的调试信息记录
- **手动触发**：GitHub Actions支持手动测试工作流

### Git Workflow
- **主分支**：`main`分支包含稳定版本
- **开发分支**：`dev`分支用于新功能开发和测试
- **PR策略**：所有PR应该合并到`dev`分支
- **自动化同步**：支持从上游仓库自动同步最新代码

## Domain Context

### 学术推荐系统
- **相似度计算**：基于论文摘要的语义相似度
- **时间衰减**：较新的Zotero文献具有更高的权重
- **多模态分析**：结合论文标题、摘要、LaTeX源码进行综合分析

### LaTeX处理
- **源码解析**：自动下载和解析论文LaTeX源文件
- **内容清理**：移除LaTeX命令、图表、公式等非正文内容
- **章节提取**：智能识别和提取论文的引言和结论部分

### 邮件生成
- **HTML模板**：使用结构化的HTML邮件模板
- **多语言支持**：支持中英文摘要生成
- **链接聚合**：提供PDF、代码仓库等相关链接

## Important Constraints

### GitHub Actions限制
- **执行时间**：公开仓库每次执行限制6小时，每月总计2000分钟
- **存储空间**：临时磁盘空间有限，需要优化LLM模型大小
- **网络带宽**：论文下载和LLM模型下载需要考虑网络限制

### 性能约束
- **LLM生成速度**：本地LLM生成单篇论文摘要约70秒
- **论文数量限制**：默认最多处理50篇论文以避免超时
- **内存使用**：向量计算和LLM推理需要优化内存占用

### API限制
- **Zotero API**：需要遵循API访问频率限制
- **arXiv API**：需要处理网络错误和重试机制
- **PapersWithCode API**：代码仓库链接查询可能失败

## External Dependencies

### 必需的API服务
- **Zotero API**：访问用户文献库，需要用户ID和API密钥
- **arXiv API**：获取最新论文信息，通过RSS feed和REST API
- **SMTP服务**：发送推荐邮件，支持各种邮件服务商

### 可选的AI服务
- **OpenAI兼容API**：云端LLM服务，如SiliconFlow等
- **PapersWithCode API**：获取论文代码仓库链接
- **本地LLM**：Qwen2.5-3B开源模型，约3GB大小

### 部署平台
- **GitHub**：代码托管和Actions自动化
- **Docker**：容器化部署支持
- **本地环境**：支持Windows/Linux/macOS本地运行
