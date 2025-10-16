<!-- OPENSPEC:START -->
# OpenSpec Instructions

These instructions are for AI assistants working in this project.

Always open `@/openspec/AGENTS.md` when the request:
- Mentions planning or proposals (words like proposal, spec, change, plan)
- Introduces new capabilities, breaking changes, architecture shifts, or big performance/security work
- Sounds ambiguous and you need the authoritative spec before coding

Use `@/openspec/AGENTS.md` to learn:
- How to create and apply change proposals
- Spec format and conventions
- Project structure and guidelines

Keep this managed block so 'openspec update' can refresh the instructions.

<!-- OPENSPEC:END -->

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

**zotero-arxiv-daily** 是一个智能学术论文推荐系统，根据用户的Zotero图书馆内容，每天推荐相关的新arXiv论文并通过邮件发送。项目设计为可以通过GitHub Actions零成本自动化运行。

## 常用命令

### 本地开发和测试
```bash
# 安装依赖（使用uv包管理器）
uv install

# 设置环境变量后运行主程序
export ZOTERO_ID=your_zotero_id
export ZOTERO_KEY=your_zotero_key
export ARXIV_QUERY="cs.AI+cs.CV+cs.LG"
export SMTP_SERVER="smtp.qq.com"
export SMTP_PORT=465
export SENDER="your_email@qq.com"
export SENDER_PASSWORD="your_smtp_password"
export RECEIVER="receiver@example.com"
uv run main.py

# 运行测试（如果有的话）
uv run pytest
```

### GitHub Actions调试
- **手动触发测试工作流**：在GitHub Actions页面点击"I want to test this workflow"
- **调试版本工作流**：`.github/workflows/test.yml` - 始终获取5篇arXiv论文进行测试
- **主工作流**：`.github/workflows/main.yml` - 每天22:00 UTC自动运行

## 核心架构

### 主要模块和文件结构

```
├── main.py                    # 主入口点，协调整个推荐流程
├── paper.py                   # ArxivPaper类，处理单篇论文的所有操作
├── recommender.py             # 推荐算法实现，基于向量相似度
├── llm.py                     # LLM管理，支持本地和云端API
├── construct_email.py         # 邮件生成和发送
├── parse_html.py              # HTML内容解析工具
├── pyproject.toml             # 项目依赖配置
├── .github/workflows/         # GitHub Actions配置
│   ├── main.yml              # 每日自动运行工作流
│   └── test.yml              # 测试工作流
└── assets/                   # 静态资源文件
```

### 数据流架构

```
Zotero Library → Vector Embedding → Similarity Calculation → Top-N Papers → LLM Processing → Email
     ↓                  ↓                    ↓                    ↓              ↓
   Collection         Time Weight         Score Ranking      Summary Generation  SMTP
   Filter             Application         Selection          (Qwen2.5-3B)       Send
```

### 核心类和函数

#### ArxivPaper类 (paper.py)
- **数据封装**：封装arXiv论文的所有属性和信息
- **LaTeX源码解析**：下载并解析论文的LaTeX源文件，提取主要内容
- **内容清理**：自动移除LaTeX命令、图表、公式等非正文内容
- **代码链接获取**：通过PapersWithCode API获取代码仓库链接
- **论文类型识别**：使用LLM自动识别论文类型（解决方案型/探究型）
- **结构化摘要生成**：根据论文类型生成不同格式的结构化摘要
- **LLM集成**：生成论文摘要和关键点分析

#### 推荐算法 (recommender.py)
- **向量化相似度计算**：使用sentence-transformers进行语义嵌入
- **时间衰减权重**：根据论文添加时间计算权重，越新的论文权重越高
- **相关性评分**：计算候选论文与用户Zotero库的整体相关性

#### LLM管理 (llm.py)
- **双模式支持**：本地LLM（Qwen2.5-3B）和云端API（OpenAI兼容）
- **单例模式**：确保性能优化和统一接口
- **自动重试机制**：网络错误处理和重试逻辑
- **论文类型识别**：专门的方法用于自动识别论文类型（解决方案型 vs 探究型）
- **结构化摘要生成**：根据论文类型生成不同格式的摘要

#### 邮件生成 (construct_email.py)
- **HTML邮件模板**：结构化的邮件内容展示
- **论文类型标签**：在邮件中显示论文类型标识
- **格式化摘要显示**：支持结构化的论文摘要格式，包含图标和颜色区分

## 环境变量配置

### 必需环境变量
- `ZOTERO_ID`: Zotero用户ID（数字序列，非用户名）
- `ZOTERO_KEY`: Zotero API密钥
- `ARXIV_QUERY`: arXiv查询分类（如：cs.AI+cs.CV+cs.LG）
- `SMTP_SERVER`: SMTP服务器地址
- `SMTP_PORT`: SMTP端口
- `SENDER`: 发送邮件的邮箱
- `SENDER_PASSWORD`: SMTP认证密码
- `RECEIVER`: 接收邮件的邮箱

### 可选环境变量
- `MAX_PAPER_NUM`: 最大论文数量（默认：50，-1表示全部）
- `SEND_EMPTY`: 是否发送空邮件（默认：False）
- `USE_LLM_API`: 是否使用云端LLM API（默认：0，使用本地LLM）
- `OPENAI_API_KEY`: LLM API密钥
- `OPENAI_API_BASE`: LLM API基础URL
- `MODEL_NAME`: LLM模型名称
- `ZOTERO_IGNORE`: Gitignore风格的Zotero收藏夹过滤规则
- `LANGUAGE`: TLDR生成语言（默认：Chinese）

## 依赖关系

### 核心依赖
- `arxiv>=2.1.3`: arXiv API访问
- `pyzotero>=1.5.25`: Zotero API客户端
- `sentence-transformers>=3.3.1`: 文本向量化
- `llama-cpp-python>=0.3.2`: 本地LLM推理
- `openai>=1.57.0`: OpenAI API客户端
- `scikit-learn>=1.5.2`: 机器学习工具
- `loguru>=0.7.2`: 日志记录

### 工具库
- `gitignore-parser>=0.1.11`: Gitignore模式解析
- `tiktoken>=0.8.0`: Token计算
- `python-dotenv>=1.0.1`: 环境变量管理
- `feedparser>=6.0.11`: RSS feed解析

## 关键设计特性

### 模块化设计
- **松耦合架构**：各模块职责明确，易于扩展和维护
- **统一接口**：LLM管理器提供统一API，支持多种LLM提供商
- **错误处理**：完善的异常捕获和重试机制

### 性能优化
- **向量化缓存**：避免重复计算论文嵌入
- **时间衰减权重**：优先推荐较新的相关论文
- **LLM单例模式**：避免重复加载模型

### 部署灵活性
- **GitHub Actions集成**：零成本自动化部署
- **本地运行支持**：支持开发和调试环境
- **Docker支持**：提供容器化部署选项

## 测试和调试

### 测试工作流
- 使用`.github/workflows/test.yml`进行功能测试
- 测试工作流始终获取固定数量的论文，便于验证功能

### 日志调试
- 使用`loguru`库进行详细日志记录
- 支持不同日志级别和输出格式
- 关键步骤和错误信息都有详细记录

### 常见问题排查
1. **Zotero API限制**：检查API密钥权限和访问频率
2. **LLM下载失败**：确保网络连接稳定，本地存储空间充足
3. **邮件发送失败**：验证SMTP配置和认证信息
4. **GitHub Actions超时**：调整`MAX_PAPER_NUM`参数或使用更快的LLM API

## 新功能特性

### 论文类型识别和结构化摘要

系统现在支持自动识别论文类型并生成结构化摘要：

#### 论文类型
- **解决方案型**（绿色标签）：提出新方法、算法、框架或技术解决方案的论文
- **探究型**（橙色标签）：进行实验分析、数据探索或理论验证的论文

#### 摘要格式
- **解决方案型论文**包含：
  - 🎯 需要解决的问题
  - ⚠️ 现有方案的缺点
  - 💡 新方案的创新点
- **探究型论文**包含：
  - 🔍 探究的问题
  - 📊 实验结论

#### 使用说明
- 论文类型由LLM自动识别，无需手动配置
- 邮件模板会根据论文类型显示不同的颜色标签和格式
- 如果类型识别失败，系统会回退到通用摘要格式
- 支持向后兼容，不会影响现有的邮件生成流程

## 开发注意事项

- 项目主要使用中文进行注释和文档编写
- 遵循PEP 8代码规范
- 新功能应优先合并到`dev`分支
- 所有PR都应该考虑GitHub Actions环境的限制
- 注意LLM相关功能对计算资源和时间的影响
- 论文类型识别需要额外的LLM调用，可能增加处理时间