/** Editable presentation authoring. Use with the bundled @oai/artifact-tool
 * or invoke buildDeck(presentation, data) inside Artifact Session.
 * The experiment itself has no JavaScript dependency.
 */
const FONT = 'Microsoft YaHei';
const C = { ink:'#17392B', muted:'#587064', green:'#276749', pale:'#F7F9F5', line:'#D5DFD6' };

function text(slide, value, x, y, w, h, size=28, bold=false, color=C.ink) {
  const box=slide.shapes.add({geometry:'textbox',name:value.slice(0,36),
    position:{left:x,top:y,width:w,height:h},fill:'none',
    line:{fill:'none',width:0,style:'solid'}});
  box.text=value;
  box.text.style={fontFamily:FONT,fontSize:size,bold,color};
  return box;
}
function page(presentation,title,notes='') {
  const s=presentation.slides.add();
  s.background.fill=C.pale;
  text(s,title,64,45,1152,88,44,true);
  text(s,String(presentation.slides.items.length).padStart(2,'0'),1165,666,52,28,17,false,C.muted);
  s.speakerNotes.text=notes;
  return s;
}
function paragraphs(s, items, top=165, size=28, step=106) {
  items.forEach((v,i)=>text(s,v,66,top+i*step,1140,step-14,size));
}
function table(s,values,widths,top=170,height=350,size=24) {
  const t=s.tables.add({rows:values.length,columns:values[0].length,left:64,top,width:1152,height,
    columnWidths:widths,values});
  t.borders.assign({fill:C.line,width:1,style:'solid'});
  t.cells.block({row:0,column:0,rowCount:values.length,columnCount:values[0].length}).assign({
    textStyle:{fontSize:size,color:C.ink},margins:{left:14,right:14,top:12,bottom:12}});
  for(let r=0;r<values.length;r++) {
    for(let c=0;c<values[0].length;c++) {
      t.getCell(r,c).fill=r===0?'#E5EEE4':(r%2?'#FFFFFF':'#F0F5ED');
      if(r===0) t.getCell(r,c).text.style={fontFamily:FONT,fontSize:size,bold:true,color:C.ink};
    }
  }
  return t;
}
function chart(s,labels,values,{name='指标',max=undefined,numberFormat='0.0000',top=160,height=425}={}) {
  return s.charts.add('bar',{
    position:{left:64,top,width:1152,height},categories:labels,
    series:[{name,values:values.map(v=>Number(v.toFixed(8))),fill:C.green}],hasLegend:false,
    barOptions:{direction:'column',grouping:'clustered',gapWidth:110},
    xAxis:{textStyle:{fontSize:21,fill:C.ink}},
    yAxis:{min:0,max,numberFormatCode:numberFormat,
      textStyle:{fontSize:18,fill:C.muted},
      majorGridlines:{fill:'#DCE4DA',width:1,style:'solid'}},
    dataLabels:{showValue:true,position:'outEnd',numberFormatCode:numberFormat,
      textStyle:{fontSize:21,fill:C.ink}},
    chartFill:C.pale,plotAreaFill:C.pale,
  });
}

export function buildDeck(presentation,{stats,results,trials,selection,manifest}) {
  if(presentation.slides.items.length) throw new Error('Build into an empty presentation');
  presentation.theme.defaultFont=FONT;
  const rating=results.filter(r=>r.rmse!==undefined);
  const bias=results.find(r=>r.model==='Bias');
  const global=results.find(r=>r.model==='GlobalMean');
  const pop=results.find(r=>r.model==='Popularity');
  let s=page(presentation,'园艺商品推荐实验',
    '课程项目：Frontier of Cross-media Recommendation System。任务来源：RS-Project-description(2).pdf，第2至3页。数据使用用户提供的本地文件。');
  text(s,'Amazon Patio, Lawn and Garden',66,205,1148,76,48,true);
  text(s,'评分预测与 Top-10 推荐',66,315,1148,66,36);
  text(s,'13,272 条评分    1,686 位用户    962 件商品',66,450,1148,56,28,false,C.muted);
  text(s,'按用户划分，验证集选参，全目录评估',66,532,1148,50,28,false,C.muted);

  s=page(presentation,'实验任务与实现', '来源：课程任务文档第2至3页。基础任务和进阶任务全部包含。NDCG 是进阶任务的可选指标，本项目已实现。');
  table(s,[['任务','本项目实现'],['数据划分','逐用户随机划分 80% / 20%'],
    ['评分预测','MAE、RMSE，四种评分模型'],['Top-10 推荐','全目录候选，排除训练历史'],
    ['排序评估','Precision、Recall、F-measure、NDCG']], [300,852],160,420,28);

  s=page(presentation,'数据稀疏且评分偏高',
    `来源：outputs/default/data_stats.json。原始文件 SHA256=${manifest.data_sha256}。原始来源：https://cseweb.ucsd.edu/~jmcauley/datasets/amazon/links.html。`);
  text(s,'矩阵密度 0.82%',66,154,535,58,34,true);
  text(s,'4–5 星占 78.52%',660,154,540,58,34,true);
  chart(s,['1 星','2 星','3 星','4 星','5 星'],[519,673,1659,3384,7037],
    {name:'评分条数',numberFormat:'0',top:245,height:338});
  text(s,'13,272 条记录无重复用户商品对，用户和商品均至少有 5 条记录',66,614,1148,42,23,false,C.muted);

  s=page(presentation,'训练与评估的数据边界',
    '来源：gardenrec/data.py、experiment.py 及 outputs/default/data_stats.json。逐用户 floor(0.8*n)，不能整除时导致实际训练占比75.75%。不交换冷商品。');
  table(s,[['划分','记录数','用途'],['train','10,054','最终模型训练'],['test','3,218','最终一次性评价'],
    ['fit','7,552','train 内部的参数训练'],['validation','2,502','train 内部的参数选择']], [250,220,682],156,355,26);
  text(s,'随机种子 42，内层种子 43，评论随整条交互移动',66,546,1148,44,27);
  text(s,'逐用户取整后训练占 75.75%，2 件冷商品通过基线回退',66,606,1148,44,25,false,C.muted);

  s=page(presentation,'对照算法',
    '来源：gardenrec/models.py。ItemKNN 是正残差余弦加共同人数收缩的变体，参考 Sarwar et al., WWW 2001, https://files.grouplens.org/papers/www10_sarwar.pdf。MF 参考 Koren et al., Computer 2009, https://doi.org/10.1109/MC.2009.263，未声称完整复现论文。');
  table(s,[['算法','训练与预测方式'],['GlobalMean','所有评分预测训练均值'],
    ['Bias','全局均值 + 用户偏置 + 商品偏置'],['ItemKNN','基线残差余弦相似度 + 邻居残差加权'],
    ['MFALS','固定偏置 + 用户与物品潜在因子内积'],['Popularity','按训练评分次数排序，只作排序基线']], [265,887],153,445,25);

  s=page(presentation,'验证集确定模型与参数', '来源：outputs/default/validation_trials.json 和 selection.json。评分模型按验证 RMSE 选参，排序模型在这些配置和 Popularity 中按验证 NDCG 选择。未按测试结果调参。');
  const valRows=[['模型','验证 RMSE','验证 NDCG@10']];
  for(const r of results) {
    const best=trials.find(t=>t.model===r.model && JSON.stringify(t.params)===JSON.stringify(selection.model_settings[r.model]));
    valRows.push([r.model,best.rmse===undefined?'不适用':best.rmse.toFixed(4),best.ndcg.toFixed(4)]);
  }
  table(s,valRows,[410,371,371],153,400,26);
  text(s,'预选结果：评分使用 Bias，排序使用 Popularity',66,598,1148,44,29,true);

  s=page(presentation,'Bias 的评分预测误差最低',
    `来源：outputs/default/metrics.json。Bias MAE=${bias.mae}，RMSE=${bias.rmse}。相对 GlobalMean 的RMSE降低 ${(100*(global.rmse-bias.rmse)/global.rmse).toFixed(2)}%。预测裁剪至[1,5]。`);
  chart(s,rating.map(r=>r.model),rating.map(r=>r.rmse),{name:'测试 RMSE',max:1.25});
  text(s,`Bias MAE ${bias.mae.toFixed(4)}，RMSE ${bias.rmse.toFixed(4)}，相对均值基线降低 8.82%`,66,613,1148,45,26,true);

  s=page(presentation,'Top-10 的相关项与指标', '来源：课程要求第3页与 gardenrec/metrics.py。测试集所有商品作为二值相关项，包括低评分。F-measure 是宏平均 P、R 的调和平均，另存逐用户F1的均值。NDCG使用二值相关性和对数折损。');
  paragraphs(s,[
    '候选集合：全部 962 件商品，排除该用户训练集已评分商品',
    '相关集合：该用户的所有测试商品，不设置高分阈值',
    'P@10 = 命中数 / 10，R@10 = 命中数 / 测试商品数',
    '先对用户取平均，再计算 F = 2PR / (P + R)',
    'NDCG@10 使用二值相关性，按排名进行 log2 折损',
  ],155,26,91);

  s=page(presentation,'热门推荐在本次排序评价中领先',
    `来源：outputs/default/metrics.json。Popularity P@10=${pop.precision}，R@10=${pop.recall}，F=${pop.f_measure}，NDCG=${pop.ndcg}。全目录候选，无负采样。`);
  chart(s,results.map(r=>r.model),results.map(r=>r.ndcg),{name:'测试 NDCG@10',max:0.07});
  text(s,'Popularity  P@10 0.0176   R@10 0.0798   F-measure 0.0288',66,613,1148,45,27,true);

  s=page(presentation,'完整测试结果', '来源：outputs/default/metrics.json 与 comparison.csv。F 根据宏P/R计算。Popularity 不预测星级，MAE/RMSE不适用。原始精度见 JSON。');
  table(s,[['模型','MAE','RMSE','P@10','R@10','F','NDCG'],...results.map(r=>[
    r.model,...['mae','rmse','precision','recall','f_measure','ndcg'].map(k=>r[k]===undefined?'不适用':r[k].toFixed(4))])],
    [230,150,150,150,150,150,172],167,370,23);
  text(s,'同一测试划分，不同优化目标需要分别评价',66,590,1148,50,29,true);

  s=page(presentation,'结果解释与局限', '来源：本次实验数据与代码。这里的稀疏性、评分偏高解释属于推测，未进行因果或显著性检验。ItemKNN目录覆盖率约78.27%，热门推荐约1.77%。');
  paragraphs(s,[
    '评分误差较低的模型，其 Top-10 命中率未必更高',
    '稀疏数据和偏高评分可能使正则基线更有竞争力',
    '热门推荐覆盖目录仅 1.77%，存在集中推荐的代价',
    '单次随机划分缺少置信区间，也不等于时间外推测试',
    '后续可增加多种子对比、时间划分与文本特征',
  ],156,28,93);

  s=page(presentation,'复现与项目交付', '来源：项目 README.md、scripts/package_submission.py。实验只依赖 Python3.10+ 和 NumPy。10项单元测试通过，另按导出CSV核验了全量用户推荐与指标。身份信息需由小组在提交前补充。');
  text(s,'python -m gardenrec run --config configs/default.json',66,174,1148,62,29,true);
  paragraphs(s,[
    '代码与配置：数据校验、固定划分、模型训练和评估',
    '结果产物：逐条预测、每用户 Top-10、逐用户指标和模型',
    '报告材料：完整中文实验报告与可编辑答辩幻灯片',
    '提交包：排除原始数据、拆分评论和训练模型',
  ],277,28,85);
  return presentation;
}
