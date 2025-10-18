## 1. LLM输出格式修改
- [x] 1.1 修改llm.py中的generate方法，输出HTML格式
- [x] 1.2 更新paper.py中的article生成逻辑，使用HTML提示词
- [x] 1.3 为不同论文类型创建HTML格式的提示词模板

## 2. 邮件模板优化
- [x] 2.1 更新construct_email.py，直接使用HTML格式摘要
- [x] 2.2 优化邮件模板，更好地展示HTML格式摘要
- [x] 2.3 移除现有的markdown转HTML转换逻辑

## 3. 代码简化
- [x] 3.1 清理不再需要的markdown转换相关代码
- [x] 3.2 简化邮件生成流程

## 4. 测试和验证
- [ ] 4.1 本地测试HTML输出效果
- [ ] 4.2 验证邮件显示效果
- [ ] 4.3 测试GitHub Actions环境下的功能