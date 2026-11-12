"""Write the course report by patching the supplied DOCX template in place.

Untouched OOXML parts are copied byte-for-byte. This authoring utility needs
python-docx and lxml, supplied by the Codex document runtime.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

from docx import Document
from lxml import etree


ROOT = Path(__file__).resolve().parents[1]
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
NS = {"w": W, "m": M}


def tag(name):
    prefix, local = name.split(":")
    return "{" + NS[prefix] + "}" + local


def element(name, **attrs):
    e = etree.Element(tag(name))
    for key, value in attrs.items():
        e.set(tag("w:" + key), str(value))
    return e


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", default=str(ROOT.parent / "推荐系统实验报告模版.docx"))
    parser.add_argument("--output", default=str(ROOT / "deliverables" / "园艺商品推荐实验报告.docx"))
    args = parser.parse_args()
    template, output = Path(args.template), Path(args.output)
    if template.resolve() == output.resolve():
        raise ValueError("Output must differ from the reference template")
    original_hash = hashlib.sha256(template.read_bytes()).hexdigest()
    ref = Document(template)
    p_templates = {"body": deepcopy(ref.paragraphs[47]._p),
                   "h1": deepcopy(ref.paragraphs[44]._p),
                   "h2": deepcopy(ref.paragraphs[45]._p),
                   "h3": deepcopy(ref.paragraphs[59]._p)}
    table_template = deepcopy(ref.tables[0]._tbl)
    with ZipFile(template) as archive:
        document = etree.fromstring(archive.read("word/document.xml"))
        settings = etree.fromstring(archive.read("word/settings.xml"))
        body = document.find("w:body", NS)
        source_paragraphs = body.findall("w:p", NS)
        # Replace text only. Retain original cover drawings and paragraph styles.
        name_nodes = source_paragraphs[8].xpath(".//w:t", namespaces=NS)
        name_nodes[0].text = "项目名称：   园艺商品推荐实验"
        for node in name_nodes[1:]:
            node.text = ""
        # Cover p28 contains the original page break. Keep it and the section.
        cutoff = False
        for node in list(body):
            if node is source_paragraphs[29]:
                cutoff = True
            if cutoff and node.tag != tag("w:sectPr"):
                body.remove(node)
        section = body.find("w:sectPr", NS)
        content_log = []

        def append(node):
            body.insert(body.index(section), node)

        def paragraph(text, role="body", keep=False, centered=False):
            p = deepcopy(p_templates[role])
            for child in list(p):
                if child.tag != tag("w:pPr"):
                    p.remove(child)
            props = p.find("w:pPr", NS)
            if props is None:
                props = element("w:pPr")
                p.insert(0, props)
            # No orphan single line at either end of a paragraph.
            props.append(element("w:widowControl", val=1))
            if keep:
                props.append(element("w:keepNext"))
            if centered:
                props.append(element("w:jc", val="center"))
                props.append(element("w:ind", firstLine=0, firstLineChars=0))
            r = element("w:r")
            t = etree.SubElement(r, tag("w:t"))
            t.text = text
            t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            p.append(r)
            append(p)
            content_log.append((role, text))
            return p

        def h1(text):
            return paragraph(text, "h1")

        def h2(text):
            return paragraph(text, "h2")

        def h3(text):
            return paragraph(text, "h3")

        def eq(text):
            p = paragraph("", centered=True)
            for r in p.findall("w:r", NS):
                p.remove(r)
            math = etree.SubElement(p, tag("m:oMath"))
            run = etree.SubElement(math, tag("m:r"))
            etree.SubElement(run, tag("m:t")).text = text
            content_log.append(("equation", text))

        def table(title, values, widths):
            paragraph(title, keep=True, centered=True)
            tbl = deepcopy(table_template)
            # Keep the template's table style and original black grid system.
            props = tbl.find("w:tblPr", NS)
            for key in ("w:tblW", "w:tblLayout"):
                old = props.find(key, NS)
                if old is not None:
                    props.remove(old)
            props.append(element("w:tblW", w=sum(widths), type="dxa"))
            props.append(element("w:tblLayout", type="fixed"))
            grid = tbl.find("w:tblGrid", NS)
            for child in list(grid):
                grid.remove(child)
            for width in widths:
                grid.append(element("w:gridCol", w=width))
            original_rows = tbl.findall("w:tr", NS)
            row_patterns = [deepcopy(original_rows[0]), deepcopy(original_rows[1])]
            for row in original_rows:
                tbl.remove(row)
            for row_no, row_values in enumerate(values):
                row = deepcopy(row_patterns[0 if row_no == 0 else 1])
                for child in list(row):
                    if child.tag == tag("w:tc"):
                        row.remove(child)
                row_props = row.find("w:trPr", NS)
                if row_props is None:
                    row_props = element("w:trPr")
                    row.insert(0, row_props)
                for key in ("w:trHeight", "w:tblHeader"):
                    for old in row_props.findall(key, NS):
                        row_props.remove(old)
                row_props.append(element("w:cantSplit"))
                if row_no == 0:
                    row_props.append(element("w:tblHeader"))
                for col, value in enumerate(row_values):
                    cell = element("w:tc")
                    cp = element("w:tcPr")
                    cp.append(element("w:tcW", w=widths[col], type="dxa"))
                    cp.append(element("w:vAlign", val="center"))
                    margins = element("w:tcMar")
                    for side, width in (("top",65),("bottom",65),("left",85),("right",85)):
                        margins.append(element("w:"+side, w=width, type="dxa"))
                    cp.append(margins)
                    cell.append(cp)
                    p = element("w:p")
                    pp = element("w:pPr")
                    pp.append(element("w:spacing", before=0, after=0))
                    pp.append(element("w:jc", val="center" if row_no == 0 or col != 0 else "left"))
                    pp.append(element("w:ind", firstLine=0, firstLineChars=0))
                    if row_no < len(values) - 1:
                        pp.append(element("w:keepNext"))
                    p.append(pp)
                    r = element("w:r")
                    if row_no == 0:
                        rp = element("w:rPr")
                        rp.append(element("w:b"))
                        r.append(rp)
                    etree.SubElement(r, tag("w:t")).text = str(value)
                    p.append(r)
                    cell.append(p)
                    row.append(cell)
                tbl.append(row)
            append(tbl)
            content_log.append(("table", values))

        result_dir = ROOT / "outputs" / "default"
        def read(name):
            return json.loads((result_dir / f"{name}.json").read_text(encoding="utf-8"))
        results, stats, manifest = read("metrics"), read("data_stats"), read("manifest")
        trials, selection = read("validation_trials"), read("selection")
        by_name = {r["model"]: r for r in results}

        h1("实验概述")
        h2("实验目的")
        purpose = "通过园艺商品评分数据，掌握逐用户数据划分、协同过滤与矩阵分解方法，理解评分预测和推荐排序的评价差异，形成防止数据泄漏、验证选参与结果复核的实验能力。"
        assert len(purpose) <= 100
        paragraph(purpose)
        h2("实验内容")
        paragraph("围绕数据准备、模型比较与结果解释完成表1所列任务，统一保存可复现的实验产物。")
        table("表1  实验任务及分工", [
            ["序号", "任务说明", "负责人", "工作量比例"],
            ["1", "校验园艺评分数据", "________", "____%"],
            ["2", "逐用户划分数据集", "________", "____%"],
            ["3", "实现评分预测模型", "________", "____%"],
            ["4", "验证选参并重新训练", "________", "____%"],
            ["5", "生成并评价十项推荐", "________", "____%"],
            ["6", "复核指标与调试问题", "________", "____%"],
            ["7", "整理报告和答辩材料", "________", "____%"],
        ], [720, 4800, 1680, 1440])
        h2("实验环境")
        h3("硬件环境")
        paragraph("实验在配备第12代 Intel Core i7-12700H 处理器的个人计算机上完成，系统识别20个逻辑处理器，可用物理内存总容量约15.73 GiB。模型在CPU上训练，不依赖GPU。当前数据规模为1,686名用户与962件商品，使用NumPy稠密矩阵即可完成计算，适合在本机开展模型对照实验。")
        h3("网络环境")
        paragraph("数据集已存放在项目的data目录中。数据加载、模型拟合、推荐生成和离线评价均在本地完成，训练阶段无需连接外部服务器，也不涉及网络设备、路由或拓扑配置。安装软件依赖及查阅资料时可以使用普通互联网连接。")
        h3("软件环境")
        paragraph("本次实验使用Windows 11操作系统，实际运行记录的系统标识为Windows-11-10.0.26200-SP0，Python版本为3.12.14，NumPy版本为2.3.5。代码通过PowerShell调用命令行入口执行，测试使用Python标准库unittest，JSON、CSV与NPZ分别用于保存配置、评价结果和模型状态。训练程序的第三方依赖仅为NumPy。")
        h2("实验结果")
        summary = "已完成数据划分、四种评分模型及热门推荐对照，计算全部指定指标。Bias的测试RMSE为0.9669，热门推荐的NDCG@10为0.0601，测试与结果复核均通过。"
        assert len(summary) <= 100
        paragraph(summary)

        h1("实验方案")
        h2("总体方案设计")
        paragraph("依据实验指导书，本实验选择Amazon Patio, Lawn and Garden（园艺）5-core子集，将评分预测作为基础任务，并完成Top-10推荐的进阶任务。输入数据为用户提供的Patio_Lawn_and_Garden_5.json文件。模型只使用reviewerID、asin和overall三个字段，分别表示用户、商品及1至5星评分；评论正文、摘要和时间戳随交互记录保留，但不作为本次模型的输入特征。这一设置符合指导书允许仅使用用户、商品和评分完成实验的范围。")
        paragraph("总体实现由数据处理、推荐模型、评价与产物导出组成。数据处理模块负责字段校验和逐用户划分；模型模块提供GlobalMean、Bias、ItemKNN与MFALS四种评分方法，并以Popularity作为排序对照；评价模块统一计算评分误差和推荐质量。实验先利用训练集内部的验证集确定参数，再使用完整训练集重新拟合各模型，最后在同一测试集上评价，避免利用测试结果反复调整参数。")
        h2("实验流程设计")
        h3("数据读取与预处理")
        paragraph("原始文件按JSON Lines格式逐行读取，每行是一条用户对商品的评价记录。读取时检查用户和商品标识是否为非空字符串，评分是否为1至5之间的整数，并保留评论和时间信息。对可能出现的重复用户商品对，按时间戳保留最新记录，时间相同时保留最后一条。本次检查未发现重复用户商品对，因此没有因去重改变原始交互数量。")
        paragraph("完成校验后，用户与商品标识按字典序映射为连续整数，交互记录也按用户和商品排序，以获得稳定的数据索引。用户商品矩阵中，已观测位置存储真实星级，未观测位置用零占位。零只用于标识缺失，不能作为零星评分参与损失函数。原始文件保持不变，并记录其SHA256摘要，以便复核后续运行是否使用相同数据。")
        h3("逐用户划分与内部验证")
        paragraph("按照指导书建议，对每个用户的评分单独随机打乱，再取floor(0.8×n)条作为训练数据，其余作为测试数据，其中n为该用户的评分条数。外层随机种子固定为42。由于每条评分和对应评论作为一个整体移动，评分和文本不会被划到不同子集中。每位用户均有至少五条交互，因此外层训练集与测试集中都包含该用户的记录。")
        paragraph("逐用户划分时，样本条数必须取整数。本次采用向下取整，得到10,054条训练记录和3,218条测试记录，训练记录占总量的75.75%。该比例是逐用户80%目标在当前取整规则下的实际汇总结果，不能将它误写成严格的全局80%/20%。本实验不通过交换测试样本强制保证所有商品在训练集中出现，以保持既定的随机划分规则。")
        paragraph("在外层训练集内部再按用户进行一次80%/20%划分，内层种子为43，得到7,552条fit记录和2,502条validation记录。fit用于拟合候选参数，validation用于选参；两者合起来恰好组成外层训练集，且都不与测试集重叠。评分模型的参数按验证RMSE选择，评分模型本身也按验证RMSE预选；排序模型则从各算法已选配置与热门基线中，按验证NDCG@10预选。")
        h3("最终训练与结果导出")
        paragraph("参数和模型选择完成后，程序在完整外层训练集上重新拟合，训练均值、偏置、相似度和潜在因子全部重新计算。随后，模型对3,218条测试交互预测评分，并为每位用户生成Top-10列表。测试评分仅在此阶段进入评价计算，测试评论始终不参与模型训练。整个已知商品目录用于构造候选，其标识可以预先获知，但不能据此读取测试交互标签。")
        paragraph("运行后导出数据统计、候选参数的验证结果、最终测试指标、逐条评分预测、逐用户推荐列表和逐用户指标。四个数据子集以JSONL保存，模型以NPZ保存，并保留ID映射及固定划分索引。通过这些中间产物，可以核对每个汇总指标的来源，而不必只依赖终端中的最终数值。")
        h2("评分预测算法设计")
        h3("全局均值与偏置基线")
        paragraph("GlobalMean将训练集中所有观测评分的平均值μ作为任意用户商品对的预测。这一模型不区分用户与商品，用于衡量更复杂模型相对于简单均值的收益。Bias进一步加入用户偏置和商品偏置，分别描述用户评分习惯与商品整体评分水平，其预测形式为：")
        eq("r̂ᵤᵢ = μ + bᵤ + bᵢ")
        paragraph("Bias固定训练均值μ，交替更新用户偏置和商品偏置，最小化已观测评分上的平方误差与偏置L2正则项之和。正则化可以抑制少量评分造成的过大偏置。本实验每次拟合进行20轮偏置更新，并在验证集上比较正则系数5、15和30。")
        h3("基于物品的协同过滤")
        paragraph("ItemKNN先拟合偏置基线，再计算已观测评分减去基线后的残差。每件商品以其面向所有用户的残差向量表示，缺失位置设为零。两个商品的相似度取残差余弦相似度，再乘共同评分人数c对应的收缩因子c/(c+s)，其中s为收缩参数。为减少不稳定关联的影响，本实现只使用正相似度，并将商品与自身的相似度设为零。")
        paragraph("预测用户对目标商品的评分时，从该用户已经评分的商品中选择至多k个正相似邻居，对邻居残差求加权平均，再加回目标用户商品对的偏置基线。若没有可用邻居，则直接使用偏置基线。该方法参考物品协同过滤思路[3]，具体实现为带收缩的残差余弦变体，并不声称复现参考论文的全部细节。")
        h3("显式反馈矩阵分解")
        paragraph("MFALS在偏置基线的基础上，为用户和商品分别学习低维潜在因子p和q。用户偏置与商品偏置先独立拟合并固定，然后通过交替最小二乘更新两类潜在因子，预测形式为：")
        eq("r̂ᵤᵢ = μ + bᵤ + bᵢ + pᵤᵀqᵢ")
        paragraph("因子优化目标只包含训练集中已观测交互的残差平方误差，以及用户因子和商品因子的L2正则项。更新用户时固定商品因子，更新商品时固定用户因子，均求解带正则项的线性方程。本次每个候选训练20轮，比较8维与16维因子、正则系数2与10。该实现属于显式反馈ALS，未将缺失条目作为负反馈，也未实现隐式反馈ALS或完整的SVD++算法。矩阵分解的基本思路参见文献[4]。")
        h3("预测范围与冷商品回退")
        paragraph("用于MAE和RMSE计算的预测统一裁剪到1至5星。排序时保留未裁剪得分，防止多个高于5星的原始得分在裁剪后变成相同数值。训练中未出现的商品不具备可学习的邻居残差或因子信息，因而使用均值或用户偏置基线回退；MFALS中无交互商品的因子更新为零。对于完全未知的外部用户或商品评分查询，接口回退到训练均值。")
        h2("推荐列表与评价指标设计")
        h3("全商品候选与热门推荐对照")
        paragraph("对每个用户，从962件商品构成的目录中排除其在外层训练集中已经评分的商品，形成推荐候选集。评分模型对这些候选商品计算得分并降序排列，取前10项作为推荐列表；若得分相同，按ASIN字典序稳定排序。候选不进行负采样，也不先用测试标签筛选商品，因此各模型面对相同的完整候选空间。")
        paragraph("Popularity按照商品在当前训练集中被评分的次数排序，同样排除用户训练历史，作为受欢迎程度对照。它的得分是次数而非星级，因此只计算排序指标，不计算MAE和RMSE。GlobalMean的所有候选得分相同，其推荐顺序完全来自确定性的同分规则，只用于提供最低复杂度的排序对照。")
        h3("评分预测评价")
        paragraph("评分预测在同一组测试交互上计算MAE和RMSE。MAE表示平均绝对偏差，RMSE对较大的单条误差更敏感，二者均越小越好。设测试记录数为m，真实评分为r，预测评分为r̂，则：")
        eq("MAE = (1/m) ∑ |rᵤᵢ − r̂ᵤᵢ|")
        eq("RMSE = √[(1/m) ∑ (rᵤᵢ − r̂ᵤᵢ)²]")
        h3("推荐质量评价")
        paragraph("按照指导书，将某用户的全部测试商品作为相关集合Tᵤ，不额外采用评分不低于4星等筛选条件。因此，相关集合也包含低星评价商品。设推荐列表为Lᵤ，长度为10，命中数为hᵤ，则每位用户的Precision和Recall分别为Pᵤ=hᵤ/10与Rᵤ=hᵤ/|Tᵤ|。先对1,686名用户分别计算，再取宏平均P和R。F-measure严格按指导书给出的公式，由宏平均P与R计算：")
        eq("F = 2PR / (P + R)")
        paragraph("本实验同时实现可选的二值NDCG@10。推荐位置j上的商品属于测试集合时，hitⱼ为1，否则为0；DCG为hitⱼ/log₂(j+1)的累加，IDCG由min(10,|Tᵤ|)个相关商品的理想排列确定。每位用户的NDCG为DCG/IDCG，最终再对用户平均。另将逐用户F1的平均值以macro_f1单独保存，避免与课程规定的F-measure混淆。目录覆盖率定义为所有推荐中不同商品的数量除以962，用于辅助解释推荐集中程度。")
        h2("参数配置与复现方式")
        paragraph("configs/default.json固定随机种子、划分及表2参数。ItemKNN、MFALS的偏置正则固定为15，与Bias独立调参不同，比较时需注意这一差异。排序只比较按验证RMSE选定的各算法配置，未另行按排序目标调参。")
        table("表2  候选参数配置", [
            ["模型", "候选配置", "其他设置"],
            ["GlobalMean", "无可调参数", "训练评分均值"],
            ["Bias", "偏置正则5、15、30", "偏置更新20轮"],
            ["ItemKNN", "(k,s)为(10,5)、(30,5)、(30,20)、(60,20)", "偏置正则15"],
            ["MFALS", "因子维度8、16；因子正则2、10", "偏置正则15；训练20轮"],
            ["Popularity", "无可调参数", "训练评分次数降序"],
        ], [1560, 4320, 2760])
        paragraph("在项目根目录安装requirements.txt中的依赖后，执行python -m gardenrec run --config configs/default.json即可完成数据划分、验证选参、重新训练和测试评价。相同原始文件、配置与种子可复现划分及指标；训练用时受系统负载影响，不作为跨设备的固定结果。manifest.json记录本次Python、NumPy、平台、配置及数据摘要，splits/indices.npz保存实际使用的行索引。")

        h1("实验结果")
        h2("数据统计与划分结果")
        paragraph("原始园艺数据经校验后保留13,272条交互，包含1,686名用户和962件商品，评分日期从2000年4月5日至2014年7月22日。所有用户和商品都至少有五条记录，符合5-core子集的特征。矩阵密度约为0.8183%，即绝大多数用户商品组合没有观测评分。表3给出基本统计及评分分布。")
        table("表3  数据集基本统计", [
            ["统计项", "结果", "统计项", "结果"],
            ["交互数量", "13,272", "用户数量", "1,686"],
            ["商品数量", "962", "矩阵密度", "0.8183%"],
            ["平均评分", "4.1865", "重复用户商品对", "0"],
            ["1星／2星数量", "519／673", "3星数量", "1,659"],
            ["4星／5星数量", "3,384／7,037", "4至5星占比", "78.52%"],
        ], [2400, 1920, 2400, 1920])
        paragraph("评分主要集中在4星与5星，合计10,421条，占全部记录的78.52%。这使全局均值已经具有一定预测能力，也意味着评价复杂模型时必须检查其是否真正优于简单基线，而不能仅根据模型形式判断效果。各数据子集的实际规模见表4，其中fit与validation是train的进一步划分，不能把四个子集数量直接相加理解为总记录数。")
        table("表4  数据划分结果", [
            ["子集", "记录数量", "用途"],
            ["train", "10,054", "外层训练及最终拟合"],
            ["test", "3,218", "最终评分与推荐评价"],
            ["fit", "7,552", "内层候选参数训练"],
            ["validation", "2,502", "内层参数和模型选择"],
        ], [1920, 1920, 4800])
        paragraph("划分后有2件目录商品完全未在外层训练集中出现，对应10条测试记录。本实验保留这些记录参与最终评价，通过模型回退策略获得预测，而不是删除这些较难样本。所有用户均有测试记录，因此排序评价覆盖全部1,686名用户。")
        h2("验证选参与预选模型")
        paragraph("程序共评价13组候选配置，并记录验证RMSE及NDCG@10。各评分算法取验证RMSE最低的参数，随后确定评分预选模型为Bias，排序预选模型为Popularity。表5列出各算法的最终配置及其内层验证表现，所有选择均在读取测试评分进行评价之前完成。")
        val_rows = [["模型", "验证RMSE", "验证NDCG@10", "选定参数"]]
        params_text = {
            "GlobalMean": "无", "Popularity": "无", "Bias": "偏置正则5",
            "ItemKNN": "k=10，s=5，偏置正则15",
            "MFALS": "8维，因子正则10，偏置正则15，20轮",
        }
        for r in results:
            t = next(t for t in trials if t["model"] == r["model"] and t["params"] == selection["model_settings"][r["model"]])
            val_rows.append([r["model"], f"{t['rmse']:.6f}" if "rmse" in t else "不适用", f"{t['ndcg']:.6f}", params_text[r["model"]]])
        table("表5  内层验证结果与选定参数", val_rows, [1560, 1680, 2040, 3360])
        paragraph("从验证结果看，Bias在当前网格中优于其他评分模型，而Popularity在排序指标上占优。两类任务预选出不同算法，说明较小评分误差和较高推荐命中不必同时出现。MFALS的最终因子正则为10，表示本次验证更偏向较强的因子约束，但仅据此还不能断言更大模型或其他参数范围必然无效。")
        h2("评分预测结果")
        paragraph("使用选定参数在完整train上重新拟合后，对同一测试集进行评分预测，结果见表6。Popularity不输出星级，因此未纳入该表。四个评分模型的真实评分、预测值和逐条绝对误差均已导出，可以独立复算MAE与RMSE。")
        table("表6  测试集评分预测结果", [["模型", "MAE", "RMSE"]] + [
            [r["model"], f"{r['mae']:.6f}", f"{r['rmse']:.6f}"] for r in results if "rmse" in r
        ], [2880, 2880, 2880])
        paragraph("Bias的MAE为0.741726、RMSE为0.966929，两项误差均为本次对照中最低。相对于GlobalMean，MAE降低约12.96%，RMSE降低约8.82%，表明区分用户评分习惯与商品整体评分水平有助于预测。本次平均绝对误差约为0.74星，体现出一定改进，但不能将其解释为某种分类正确率。")
        paragraph("MFALS的RMSE为0.978459，优于全局均值，但没有超过Bias。ItemKNN的MAE虽然比GlobalMean低，其RMSE却上升到1.106110，说明两种误差指标对预测结果的评价不同，较大误差的影响值得进一步检查。当前数据稀疏、相似度估计以及参数范围都可能影响表现，现有结果不足以把差异归因于单一原因。")
        h2("Top10推荐结果")
        paragraph("五个对照方法都为每位用户生成10项推荐，每种方法保存16,860条用户商品推荐记录，合计84,300条。评价使用完整未评分候选集，以该用户全部测试商品为相关集合，测试结果见表7。表中的P、R和F均以0至1之间的小数表示，目录覆盖率单独以百分数显示。")
        table("表7  测试集Top10推荐结果", [["模型", "P@10", "R@10", "F值", "NDCG@10", "覆盖率"]] + [
            [r["model"], f"{r['precision']:.6f}", f"{r['recall']:.6f}", f"{r['f_measure']:.6f}", f"{r['ndcg']:.6f}", f"{r['catalog_coverage']:.2%}"]
            for r in results
        ], [1560, 1416, 1416, 1416, 1416, 1416])
        paragraph("Popularity的Precision@10为0.017556、Recall@10为0.079844、F-measure为0.028784、NDCG@10为0.060129，是本次排序评价中表现最好的方法。其Precision约为1.76%，对应平均每位用户的10项列表命中约0.176件测试商品；Recall约为7.98%，表示先逐用户计算后平均的测试商品找回比例。由于候选目录较大且每位用户测试记录有限，不能把这些数值与使用负采样或高分相关项筛选的实验直接比较。")
        paragraph("ItemKNN的NDCG@10为0.023166，高于Bias和MFALS，但仍低于Popularity，说明当前个性化模型没有在命中指标上超过热门对照。同时，Popularity只覆盖17件商品，目录覆盖率为1.77%；ItemKNN覆盖753件商品，覆盖率为78.27%。因此，热门推荐的较高命中伴随着推荐集中的代价，若实际应用重视长尾商品曝光，需要同时考虑这一差异。")
        h2("结果分析与适用范围")
        paragraph("评分预测与推荐排序具有不同的评价目标。Bias中的用户偏置对同一用户所有候选商品施加相同偏移，所以在未裁剪得分排序时，它本身不会改变该用户的商品相对次序，列表主要受商品偏置和历史排除规则影响。这能够解释为什么Bias可以降低评分误差，却没有获得同样明显的Top-10收益。对MFALS和ItemKNN而言，模型形式虽然能引入个性化差异，但当前拟合目标、样本规模和所选网格并未保证其排序指标更优。")
        paragraph("本次实验只有一个外层随机种子，没有给出多次划分的均值、方差或置信区间，因此结论只描述当前划分下的对照结果。逐用户随机划分符合指导书建议，但不属于严格的时间外推，可能让较晚交互用于预测较早交互。相关集合包含低星商品也会影响指标含义，这是本次依照课程定义采用的口径，不能将它改称为只推荐用户喜欢商品的评价。")
        paragraph("本实验完成了指导书规定的基础与进阶计算流程，但尚未体现复杂模型稳定优于简单基线的证据。后续可以开展多随机种子重复实验、按时间划分和独立的排序目标调参，并研究在严格训练边界内加入评论文本等特征。本次结果不包含这些扩展，报告中的改进方向也不作为已经取得的实验成果。")
        h2("实现验证与交付产物")
        paragraph("代码的10项单元测试全部通过，覆盖逐用户划分的可复现与不相交性质、异常评分校验、去重策略、手工可算指标、冷商品回退、推荐排除、同分稳定排序、模型保存与加载，以及ALS目标单调不增等行为。另通过verify_outputs.py逐模型核对全量推荐和逐条预测CSV，确认每个用户的推荐无重复且不包含其训练历史，并复算出与汇总JSON一致的MAE、RMSE、Precision、Recall、F-measure和NDCG。")
        paragraph("模型、固定划分和逐用户结果保存在outputs/default下，报告和答辩幻灯片保存在deliverables下。提交打包脚本收集代码、配置、说明、报告、幻灯片和汇总结果，排除原始数据集、拆分评论及模型文件，符合指导书无需提交数据集的说明。本次实验的训练、验证及测试评价总用时约14.52秒，该时间仅对应当前运行环境，不作为算法计算效率的严格基准。")

        h1("问题及调试过程")
        h2("系统Python入口不可用")
        paragraph("最初在PowerShell中直接执行python时，命令解析到WindowsApps目录中的占位程序，实际启动失败，因而无法读取数据或运行实验。调试时先区分命令名称与真实解释器，再检查可用Python路径，最终使用已安装的Python 3.12.14运行时完成数据处理和训练。这个问题属于运行入口配置，不是推荐算法实现错误。")
        paragraph("为便于后续复现，项目补充了scripts/run.ps1，按项目虚拟环境、系统Python和当前机器备用运行时的顺序探测，并检查是否可以导入NumPy。说明文档同时保留了使用实际解释器路径的运行方式。迁移到其他计算机时应安装独立Python环境，不能照搬当前机器的专用运行时路径。")
        h2("临时目录写入受到权限限制")
        paragraph("首次执行单元测试时，部分数据读取和模型持久化测试出现PermissionError。错误发生在创建测试临时文件的阶段，测试尚未进入对应算法断言。根据错误路径定位后，发现默认临时目录位于受限的应用沙箱中，文件写入及清理受到权限限制。")
        paragraph("修正方法是将测试临时目录显式放到项目可写的tmp/tests下，再由TemporaryDirectory管理测试文件。修改后10项测试全部通过，模型保存与加载后的推荐顺序和得分保持一致。调试经验是先根据堆栈判断错误属于环境、输入还是算法，不能将权限异常误判为模型计算失败。")
        h2("划分比例与冷商品处理核查")
        paragraph("检查划分产物时，训练集总体占比为75.75%，没有达到字面上的全局80%。进一步逐用户核对后确认，程序使用floor(0.8×n)分别取整，每个用户都会舍去不足一条的部分，小样本用户占比较高时，这种舍入差异在汇总后会比较明显。代码按已声明规则划分，报告需要同时给出目标比例、取整方式和实际数量。")
        paragraph("同一检查还发现2件冷商品及其10条测试评分。处理时保留原随机划分和这些测试记录，采用基线回退，并以单元测试确认冷商品不会产生无穷值或空预测。没有把测试交互移动到训练集，也没有删除这些交互来改善指标。这样能保证评价集合完整，并使冷启动情形在报告中可追溯。")
        h2("指标定义与全量输出复核")
        paragraph("评价实现需要区分用户宏平均、交互平均和F1的计算次序。特别是，先计算每个用户F1再平均，与使用宏平均Precision、Recall求调和平均通常不相等。本实验把课程规定的后一种定义保存为f_measure，将前一种作为macro_f1另存，防止混用同名指标。")
        paragraph("调试中使用真实评分[1,5]与预测[2,3]的手工样例核对MAE=1.5、RMSE=√2.5，并通过已知命中位置验证NDCG折损。随后从导出的CSV重新计算全量指标，检查所有推荐列表长度、商品去重和训练历史排除。复核结果与metrics.json一致，说明报告中的数值可以由明细结果重建，而非只依赖实现内部的单次输出。")
        h2("复杂模型效果未超过基线的诊断")
        paragraph("最终结果中，MFALS没有超过Bias的评分预测效果，ItemKNN的RMSE还高于均值基线。首先检查是否存在计算错误：ALS训练目标由约8,595.08下降至约8,503.97，持久化前后推断一致，评分和推荐指标也通过独立复算。目前这些检查支持训练流程正常运行，但不能证明参数范围已经充分或模型一定适合当前数据。")
        paragraph("因此，这一现象被保留为实验结果进行分析，没有将其描述成已经消除的程序故障。数据稀疏、评分偏高、邻居残差估计不稳定以及评分目标与排序目标不同，都是可能影响效果的因素，还需额外实验才能判断各自作用。后续应继续以训练集内部验证确定改动，再用独立评价检验改进，避免因为已经看到测试结果就反复针对该测试集优化。")
        paragraph("参考资料", keep=True)
        paragraph("[1] 课程实验指导书 RS-Project-description(2).pdf，第2至3页，数据预处理、评分预测、推荐与提交要求。")
        paragraph("[2] McAuley J. Amazon product data（2014），数据集与字段说明。https://cseweb.ucsd.edu/~jmcauley/datasets/amazon/links.html")
        paragraph("[3] Sarwar B, Karypis G, Konstan J, Riedl J. Item-Based Collaborative Filtering Recommendation Algorithms. WWW, 2001. https://files.grouplens.org/papers/www10_sarwar.pdf")
        paragraph("[4] Koren Y, Bell R, Volinsky C. Matrix Factorization Techniques for Recommender Systems. Computer, 2009, 42(8): 30-37. DOI: 10.1109/MC.2009.263.")

        field_setting = settings.find("w:updateFields", NS)
        if field_setting is None:
            field_setting = element("w:updateFields", val="true")
            settings.append(field_setting)
        else:
            field_setting.set(tag("w:val"), "true")
        edited = {
            "word/document.xml": etree.tostring(document, encoding="UTF-8", xml_declaration=True, standalone=True),
            "word/settings.xml": etree.tostring(settings, encoding="UTF-8", xml_declaration=True, standalone=True),
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        with ZipFile(output, "w") as target:
            for info in archive.infolist():
                target.writestr(info, edited.get(info.filename, archive.read(info.filename)))

    assert hashlib.sha256(template.read_bytes()).hexdigest() == original_hash
    with ZipFile(template) as old, ZipFile(output) as new:
        assert old.namelist() == new.namelist()
        changed = [name for name in old.namelist() if old.read(name) != new.read(name)]
        assert set(changed) == {"word/document.xml", "word/settings.xml"}
        final = etree.fromstring(new.read("word/document.xml"))
        assert not final.xpath('//w:p[w:pPr/w:pStyle[@w:val="af8"]]', namespaces=NS)
        assert etree.tostring(final.find("w:body/w:sectPr", NS)) == etree.tostring(section)
    qa = ROOT / "tmp" / "template-report"
    qa.mkdir(parents=True, exist_ok=True)
    (qa / "report-content.json").write_text(json.dumps(content_log, ensure_ascii=False, indent=2), encoding="utf-8")
    (qa / "fidelity.json").write_text(json.dumps({"reference_sha256": original_hash,
        "changed_parts": changed, "unchanged_parts": len(old.namelist())-len(changed),
        "reference_unchanged": True, "output": str(output)}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Created {output}")
    print(f"Template preserved: only {changed} changed")


if __name__ == "__main__":
    main()
