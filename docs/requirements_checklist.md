# 课程任务核对

任务来源：用户提供的 `E:/研究生上课/媒体推荐/RS-Project-description(2).pdf`。

| 文档条目 | 交付内容 | 检查方式 |
|---|---|---|
| 选择一个商品域 | Patio, Lawn and Garden 5-core | 原始文件 SHA256 与 data_stats.json |
| 逐用户随机 80%/20% | train、test JSONL 和 indices.npz | 单元测试及 verify_outputs.py |
| 评论自动随评分划分 | reviewText、summary 与记录一同导出 | 数据读取及导出代码 |
| 根据训练集预测测试评分 | GlobalMean、Bias、ItemKNN、MFALS | predictions CSV |
| 计算 MAE、RMSE | 四个评分模型的测试指标 | 可从导出预测独立复算 |
| 每用户 10 个推荐 | 1,686 位用户，每模型 16,860 行 | 推荐条数、去重、排除训练历史检查 |
| Precision、Recall | 逐用户计算后宏平均 | per_user CSV 与 verify_outputs.py |
| F-measure | 对宏平均 P、R 取调和平均 | 指标定义及单元测试 |
| 可选 NDCG | 二值 NDCG@10 | 手工样例测试与全量复算 |
| 源代码，无需数据 | gardenrec_submission.zip | 提交包目录检查 |
| 实验报告 | project_report.pdf / md / html | 基于实际结果生成 |
| 报告幻灯片 | project_slides.pptx | 12 页，原生表格与图表可编辑 |

课程文档规定进阶推荐可选；本项目已经完成。数据中的 review、helpful、图片、元数据并非全部必须使用，当前模型仅使用 ID 与评分。

数据协议细节：外层每用户 `floor(0.8×n)` 条作为训练，实际总占比 75.75%。2 个冷商品不强制移动到训练。相关集合按照课程定义采用全部测试商品，包括低分评价。

提交前由小组补充姓名、学号和分工。未提供的信息没有编造。报告的 Markdown 版本和 PowerPoint 均可继续编辑。
