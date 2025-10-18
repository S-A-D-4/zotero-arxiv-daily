## Why

当前系统使用LLM生成markdown格式的论文摘要，然后在邮件生成时进行简单的markdown到HTML转换。这种方式存在格式限制和转换不完整的问题，无法充分利用HTML的富文本表现能力。

## What Changes

- 修改LLM提示词，使其直接输出结构化的HTML格式摘要
- 更新论文摘要生成逻辑，支持HTML输出格式
- 优化邮件模板，更好地展示HTML格式的摘要内容
- 移除现有的markdown到HTML转换逻辑，简化代码结构

## Impact

- Affected specs: llm-output（新能力）
- Affected code:
  - `llm.py`: LLM生成方法
  - `paper.py`: ArxivPaper.article属性
  - `construct_email.py`: 邮件模板和HTML处理逻辑