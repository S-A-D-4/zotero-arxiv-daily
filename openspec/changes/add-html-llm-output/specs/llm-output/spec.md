## ADDED Requirements

### Requirement: HTML格式LLM输出
系统 SHALL 支持LLM直接输出HTML格式的论文摘要，以提供更丰富的邮件展示效果。

#### Scenario: 解决方案型论文HTML摘要生成
- **WHEN** 系统识别论文为解决方案型并生成摘要时
- **THEN** LLM SHALL 输出包含HTML标签的结构化摘要，包括现有方案缺点、新方案设计理念和实现方式的段落格式

#### Scenario: 探究型论文HTML摘要生成
- **WHEN** 系统识别论文为探究型并生成摘要时
- **THEN** LLM SHALL 输出包含HTML标签的结构化摘要，包括探究问题和实验结论的段落格式

#### Scenario: HTML摘要邮件集成
- **WHEN** 生成邮件内容时
- **THEN** 系统 SHALL 直接使用LLM输出的HTML格式摘要，无需额外的markdown到HTML转换

#### Scenario: HTML格式验证
- **WHEN** LLM生成HTML格式摘要时
- **THEN** 系统 SHALL 验证HTML格式正确性，确保邮件正常显示

## MODIFIED Requirements

### Requirement: 论文摘要生成
论文摘要生成过程 SHALL 支持HTML格式输出，提供更丰富的内容展示方式。

#### Scenario: HTML格式输出
- **WHEN** 生成论文摘要时
- **THEN** 系统 SHALL 直接输出HTML格式，移除markdown转换步骤

#### Scenario: 内容结构保持
- **WHEN** 使用HTML格式输出时
- **THEN** 摘要 SHALL 保持原有的逻辑结构和信息完整性

#### Scenario: 邮件展示优化
- **WHEN** HTML格式的摘要集成到邮件中时
- **THEN** 邮件 SHALL 正确渲染HTML格式，提供更好的可读性和视觉效果