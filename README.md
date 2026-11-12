# Amazon 园艺商品推荐实验

针对 Patio, Lawn and Garden 5-core 数据，完整实现课程基础任务与进阶 Top-10 推荐。只需 Python 3.10+ 和 NumPy，可在 CPU 上运行。

## 快速开始

在项目根目录打开终端，确认 `data/Patio_Lawn_and_Garden_5.json` 存在：

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m gardenrec run --config configs/default.json
.venv\Scripts\python -m unittest discover -s tests -v
.venv\Scripts\python scripts/verify_outputs.py
```

无需创建虚拟环境时，使用已有 Python 直接运行以上 `-m gardenrec` 和 `-m unittest` 命令。
不要在 Windows 商店的 Python 占位程序上执行，需使用实际安装的解释器。

在当前 Codex 环境中，系统 `python` 指向不可用的 WindowsApps 占位程序，可以使用已验证的运行时：

```powershell
& 'C:\Users\lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m gardenrec run --config configs/default.json
```

该路径仅适用于当前机器。也可运行 `scripts/run.ps1`，它会依次检查虚拟环境、系统 Python 和该备用运行时。

运行结束后打开 `outputs/default/report.html`，可浏览完整中文报告、结果表与图表。
`deliverables` 中提供整理后的实验报告和答辩幻灯片，实际结果来自本地完整实验。

## 实验内容

| 课程要求 | 实现 |
|---|---|
| 数据集选择 | 用户提供的 Patio, Lawn and Garden 5-core |
| 按用户随机划分 80%/20% | 每用户 floor(0.8×n) 条训练，剩余测试，seed=42 |
| 评论随评分划分 | train/test/fit/validation JSONL 保留正文和摘要 |
| 评分预测 | GlobalMean、Bias、ItemKNN、MFALS |
| MAE 与 RMSE | 在相同测试交互上计算，预测限制在 1–5 星 |
| 每用户 Top-10 | 全商品目录，排除该用户训练集已评分商品 |
| Precision 与 Recall | 先逐用户计算，再宏平均 |
| F-measure | 使用宏平均 P、R 的调和平均，另存逐用户宏 F1 |
| NDCG | 二值相关性 NDCG@10，并报告目录覆盖率 |
| 对照实验 | 增加只用于排序的热门商品基线 |
| 提交 | 代码、报告、幻灯片，可一键打包且排除数据集 |

## 文件组织

```text
gardenrec/                 数据、模型、指标、实验和自动报告代码
configs/default.json       数据路径、随机种子、候选参数
tests/test_protocol.py     划分边界、指标、冷启动、推荐排除与模型持久化检查
scripts/                   Windows 运行、交付材料生成与提交打包
data/                      原始 JSONL，不提交
outputs/default/           实际实验输出
deliverables/              整理后的报告与答辩材料
docs/                      设计说明与课程要求对照
```

## 评估边界

外层 train/test 固定后，在 train 内再按用户拆分 fit/validation。先在验证集选参数与评分、排序模型，再在完整 train 上重新训练，最后一次性评估 test。测试评分和测试评论均不进入训练。目录由原始文件的 ASIN 构成，假设商品目录已知。

每用户小样本取整使本次训练集为 10,054 条、测试集为 3,218 条，实际训练占比约 75.75%。本项目使用 `floor(0.8×n)`，没有用全局随机划分代替逐用户划分，也没有为消除冷商品而交换测试样本。

按照课程文档，相关项是该用户所有测试商品，包括其低分商品。排序在完整候选集中进行，不做负采样，不使用测试标签先筛候选。评分预测裁剪到 1–5 星；排序保留未裁剪得分，同分按 ASIN 字典序。

GlobalMean 的排序同分，指标只作最低复杂度对照。Popularity 只按训练评分次数排序，不预测星级，MAE/RMSE 留空。其余模型按验证 RMSE 选参，排序任务从这些配置中按验证 NDCG 选择模型，未对每个算法单独以排序目标调参。

## 查看推荐结果

查看 `outputs/default/selection.json` 中的预选排序模型名，加载对应模型。例如：

```powershell
python -m gardenrec recommend --model outputs/default/models/Popularity.npz --user A1JZFGZEZVWQPY --top-k 10
```

用户须为训练中的原始 `reviewerID`，完整列表在 `splits/id_maps.json`。输出只显示商品 ASIN，没有元数据时不编造商品名称。模型只见外层训练记录，因此这个命令展示离线评估场景的推荐，不声称基于全部评分重新训练。

## 结果文件

| 文件 | 内容 |
|---|---|
| data_stats.json | 数据规模、分布、划分与冷商品统计 |
| manifest.json | 实际配置、SHA256、Python/NumPy 版本、运行时间 |
| validation_trials.json | 所有候选参数的验证指标 |
| selection.json | 查看测试前确定的参数与预选模型 |
| metrics.json / comparison.csv | 各模型最终测试指标 |
| predictions/*.csv | 逐条真实评分、预测与误差 |
| recommendations/*.csv | 每用户的 Top-10、顺序与得分类型 |
| per_user/*.csv | 逐用户命中、P、R、F1、NDCG |
| models/*.npz | 无 pickle 的模型状态与 ID 映射 |
| splits/*.jsonl | 四个数据子集，保留评论字段，移除无用姓名字段 |
| splits/indices.npz | 基于规范化原始记录顺序的固定行索引 |
| als_loss_history.json | 最终 ALS 的训练目标历史 |
| report.md / report.html | 基于实际结果自动生成的中文报告 |
| figures/*.svg | 评分分布与性能图表 |

修改参数后可用 `--output outputs/new_run` 保存到新目录，也可用 `--seed 7` 运行另一划分。相同数据和种子下划分及指标可复现，训练用时、文件时间戳随机器负载变化，浮点计算也可能有极小跨平台误差。

如需重新生成可打印报告，安装 `requirements-authoring.txt`，再运行 `python scripts/build_report.py`。报告生成器不属于训练依赖。`scripts/build_slides.mjs` 是本次默认实验的幻灯片源码，包含针对当前数据的解说，修改数据或实验协议时需同步检查这些解说。

## 算法和扩展

Bias 交替求解用户和商品偏置。ItemKNN 使用带共同评分人数收缩的正残差余弦相似度，从每个用户历史中选择邻居。MFALS 在固定偏置残差上交替最小二乘，仅使用观测条目，带 L2 正则。实现和局限详见 `docs/design.md` 及实验报告。

实现采用稠密矩阵，适合当前数据规模。更大类别建议改用 SciPy 稀疏矩阵与分块评分。当前没有引入评论 NLP、图像或商品元数据，也没有声称实现多模态模型。课程允许只用用户 ID、商品 ID 和评分完成实验。

## 提交打包

```powershell
python scripts/package_submission.py
```

生成 `dist/gardenrec_submission.zip`，不包含原始数据、拆分评论、逐用户推荐、姓名、训练模型或缓存。仅包含代码、配置、说明、汇总指标和交付报告、幻灯片。提交前补充组员姓名、学号与分工，核对老师对命名和版式的额外要求。
