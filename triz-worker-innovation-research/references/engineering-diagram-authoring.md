# 从技术关系绘制原理图

G3 建立主方案时读取；G5 按此资源绘图。先确认技术关系，再排版。节点、符号数量及文件校验结果不能证明原理正确。

## 技术关系与绘图数据

先写一句：“输入通过哪些部件，在哪个端口或接触面改变哪个量，形成什么输出；哪个条件不满足就失效。”从研究记录取部件、参数和证据。缺失尺寸保留待定及选择依据，不为图面完整而编数值。

电气图先列节点、元件端口、参考点、测量正负端、开关状态；机械图先列部件、刚性连接、接触、自由度、输入力和真实止挡对象。逐条沿回路或受力路径复述：测量跨哪两点、哪个对象先触及止挡。限制位移不等于限制力；保护面不能被画成需要撞上止挡的工作面。

依据原厂原理、公式或工程推导核对拓扑，再转为绘图数据。没有实测的设计保留 H。主机理图不使用仅表达步骤的方框流程图；外观概念图另行标注用途。

## 可运行的领域图元

在 figure_specs 或 frames 下使用 `semantic_diagram`；原有 primitives 继续可用。完整 JSON 和图示可通过教学入口生成：

```sh
python scripts/run_engineering_examples.py --output examples
python scripts/run_engineering_examples.py --output examples-png --png-browser "Chromium 可执行文件"
```

`domain=electrical` 使用 `nodes[{id,at:[x,y]}]`、`elements[{id,kind,a,b}]`，支持 source、resistor、capacitor、switch、sensor、measurement_port、ground、wire。ground 只有 a；switch 必填 state=open/closed；导线拐点用 via。标签位置用 label_at，数值用 label_template 绑定记录。元件端点从节点生成；悬空、重合却不同名节点、错误端口、导线穿过未声明节点会失败。刻意悬空须说明 open_nodes，独立隔离域分图并说明接口。符号不是完整 IEC 库，极性、传感器类型和接地含义仍须复核。

`domain=mechanical` 使用 `bodies[{id,box:[x,y,width,height],section,label,label_at}]` 与 relations，支持 contact、constraint、force、motion、dimension、clearance、protected_surface。接触关系的 a/b 端点须同时位于 body、other_body 的实际边界；保护面与约束须落在引用部件边界。尺寸标签写参数名和证据等级，可用 label_template。复杂曲面、装配和公差采用适合的参数化 CAD，保存可编辑源和部件引用。

目前自动检查覆盖端口、接触、坐标、标签互撞和面板溢出，不验证电路可辨识、材料强度或失效安全。CT、复杂液压阀、相位图和公差链等未实现的专用符号使用适合工具；不能拿通用圆框冒充。

## 排版与说明

采用白底黑字黑线、少量灰阶剖面、清晰线型和图例；报告表格保持黑白三线表。先按报告宽度规划画布，核心标注建议最终 9pt 以上；不要用巨大画布缩图。长说明移到图后，复杂机理拆成整体、局部和状态视图，部件编号保持一致。

导线优先正交，连接点画黑点，跨线是否相连必须明确。文字不压线、符号、箭头或剖面纹理，必要时加引出线。电流、信号、力和运动箭头分别说明。局部放大画出实际接触几何，不能用纹理代替。

图后紧接“看图顺序 → 中间机理 → 输出 → 一个失效条件”，与公式符号逐项对应。动态过程用动作帧、时序或波形；帧间变化具有连续因果。初步设计另列视图、接口、尺寸链、选型和待定项，不能只给概念图改名。

## 按最终报告验收

从 DOCX 的 wp:extent 读取实际宽高，结合 SVG viewBox、字体单位及缩放计算有效字号；重复引用逐次检查。小于 6pt 阻断；未知字号先解析，不能以源图 14px 或 manifest 声明替代。增加 PNG 像素不增加物理字号。

先看 SVG/PNG，再渲染 DOCX→PDF→每页图片，检查裁切、字形、图题位置、标注对线、接触对象、箭头与空白页。可选 render_smoke.py 需要 LibreOffice 与 PyMuPDF，检查页数、空白像素、替代字符及页面边界；不是完整视觉验收。

首次阅读者遮住正文复述输入、路径、输出和失效；工程视角核对最危险误读。记录文件哈希、时间、模式和可用的模型/工具身份；串行自审不得记作独立专家审查。发现问题回到记录或拓扑修正，再生成图文，旧收据失效。
