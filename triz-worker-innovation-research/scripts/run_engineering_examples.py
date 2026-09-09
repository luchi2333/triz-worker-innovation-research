"""Generate H teaching examples of topology, contact/limits and an illustrated DOCX."""
import sys
sys.dont_write_bytecode=True
import argparse
import copy
import json
from pathlib import Path
from build_figures import build_figures
from build_report import build_report
from research_contract import digest


def examples():
    common={'figure_type':'F4-mechanism-section','purpose':'explanation','design_status':'V0',
            'claim_limit':'H 教学示意；未做实物验证，不作为制造图或现场接线依据。','route_ids':[], 'parameter_ids':[]}
    electrical=dict(common,id='FIG-CIRCUIT',title='电气原理：受控充电与跨端测量',width=1020,height=500,
        main_message='开关闭合后电源通过 R1 给 C1 充电；M1 跨接 C1 两端测量，GND 仅是本回路参考点。',
        semantic_diagram={'domain':'electrical','nodes':[{'id':n,'at':p} for n,p in [
            ('A',[140,120]),('B',[360,120]),('C',[640,120]),('D',[640,360]),('E',[140,360]),('F',[820,120]),('G',[820,360])]],
            'elements':[
                {'id':'VS','kind':'source','a':'E','b':'A','label':'U1 激励源','label_at':[24,195]},
                {'id':'S1','kind':'switch','a':'A','b':'B','state':'open','label':'S1 当前断开','label_at':[200,78]},
                {'id':'R1','kind':'resistor','a':'B','b':'C','label':'R1 限流','label_at':[425,78]},
                {'id':'C1','kind':'capacitor','a':'C','b':'D','label':'C1 储能','label_at':[475,255]},
                {'id':'RETURN','kind':'wire','a':'D','b':'E'},
                {'id':'MP','kind':'wire','a':'C','b':'F'},
                {'id':'MN','kind':'wire','a':'G','b':'D'},
                {'id':'M1','kind':'measurement_port','a':'F','b':'G','label':'M1 测量端口','label_at':[735,414]},
                {'id':'GND','kind':'ground','a':'E','label':'GND 参考点','label_at':[60,438]}],
            'notes':[{'text':'黑点为同一节点；交叉线只有标黑点才相连。','at':[265,477]}]})
    mechanical=dict(common,id='FIG-CONTACT',title='机械原理：接触传力与独立行程限位',width=1000,height=490,
        main_message='滑块沿导向推动工件，工件右侧靠上止挡后停止；顶面为被保护面，停止接触面与被保护面分开。',
        semantic_diagram={'domain':'mechanical','bodies':[
            {'id':'BASE','box':[120,290,750,55],'section':True,'label':'剖切基座 / 导向','label_at':[145,393]},
            {'id':'SLIDE','box':[260,180,220,110],'label':'滑块','label_at':[325,152]},
            {'id':'WORK','box':[480,180,185,110],'label':'工件','label_at':[530,152]},
            {'id':'STOP','box':[775,180,40,110],'section':True,'label':'独立止挡（H）','label_at':[715,148]}],
            'relations':[
                {'kind':'contact','body':'SLIDE','other_body':'WORK','a':[480,188],'b':[480,280],'label':'接触面','label_at':[492,241]},
                {'kind':'constraint','body':'BASE','a':[280,290],'b':[440,290]},
                {'kind':'motion','body':'SLIDE','a':[275,100],'b':[440,100],'label':'沿导向移动','label_at':[275,65]},
                {'kind':'force','body':'SLIDE','a':[170,225],'b':[250,225],'label':'输入力 F','label_at':[135,180]},
                {'kind':'protected_surface','body':'WORK','a':[480,180],'b':[665,180],'label':'顶面受保护','label_at':[500,106]},
                {'kind':'clearance','a':[665,370],'b':[775,370],'label':'g 待定（H）','label_at':[680,416]}],
            'notes':[{'text':'几何不按比例；g 的选择需依据工况、公差链与验证结果。','at':[170,468]}]})
    return [electrical,mechanical]


def run(output,browser=None):
    output=Path(output).resolve()
    if output.exists() and any(output.iterdir()):raise ValueError('use a new/empty example directory')
    output.mkdir(parents=True,exist_ok=True)
    record={'schema_version':'1.1','project':{'title':'工程原理图教学样例','maturity':'V0'},'routes':[],
            'parameters':[], 'figure_specs':examples(), 'claims':[
                {'id':'CLM-EX','evidence_status':'H','allowed_wording':'本文件展示电气端口与机械接触的绘图方法；两例均为教学假设，未取得实测证据。'}]}
    record_path=output/'research-record.json'
    record_path.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    figure_manifest=build_figures(record_path,output/'figures',browser)
    source={'schema_version':'1.3','title':record['project']['title'],'subtitle':'黑白原理图 端口与接触关系 图文配合','cover_page':False,
            'research_record_path':'research-record.json','research_record_sha256':digest(record_path),
            'figure_manifest_path':'figures/figure-manifest.json','critical_facts_policy':'bound',
            'sections':[{'title':'阅读说明','blocks':[{'type':'paragraph','claim_ref':'/claims/CLM-EX'}]}]}
    text=[
        '从左侧激励源沿上方支路读图：开关决定连接状态，限流元件改变充电过程，储能元件两端的电压由测量端口读取。测量端口画出两个连接点，避免把单端悬空读数误认为跨端测量。',
        '从输入力箭头开始读图：滑块向右运动，在左侧接触面向工件传力。工件右侧靠上止挡后停止，顶面的被保护区域不与止挡接触。止挡不能消除输入力，过载仍需独立的限力措施及验证。图中的间隙需要回到设计记录确定，不能从示意图比例量取。']
    for index,spec in enumerate(record['figure_specs']):
        source['sections'].append({'title':spec['title'],'page_break_before':index>0,'blocks':[
            {'type':'figure','figure_ref':spec['id']}, {'type':'paragraph','text':text[index]},
            {'type':'paragraph','text':'读者复核：沿真实连接或接触关系复述作用路径，指出一个可能失效的环节，再对照正文解释。'}]})
    path=output/'report-source.json';path.write_text(json.dumps(source,ensure_ascii=False,indent=2),encoding='utf-8')
    report=build_report(path,output/'engineering-examples.docx')
    receipt={'report':report,'figures':figure_manifest,'visual_review':'pending','engineering_validation':'not-performed'}
    (output/'example-receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--png-browser')
    args=parser.parse_args();print(json.dumps(run(args.output,args.png_browser),ensure_ascii=False,indent=2))
