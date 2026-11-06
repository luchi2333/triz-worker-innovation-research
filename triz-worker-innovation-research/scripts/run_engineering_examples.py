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
    process=dict(common,id='FIG-PROCESS',title='工艺控制：废料垫片离线筛选与异常隔离',
        figure_type='F8-process-operation',width=1000,height=500,
        main_message='样片编号后保持载荷与恢复时间，记录位移和压痕；判据未冻结前仅保存观察，不把候选样片投入现场。',
        primitives=[
            {'kind':'rect','x':45,'y':110,'width':215,'height':95},
            {'kind':'text','x':60,'y':145,'text':'样片编号 / 外观记录'},
            {'kind':'text','x':60,'y':180,'text':'资源：废料，同批留对照'},
            {'kind':'arrow','x1':260,'y1':155,'x2':330,'y2':155},
            {'kind':'rect','x':330,'y':110,'width':265,'height':95},
            {'kind':'text','x':345,'y':145,'text':'同载荷、保持时间与恢复时间'},
            {'kind':'text','x':345,'y':180,'text':'记录位移 / 压痕 / 测量误差'},
            {'kind':'arrow','x1':595,'y1':155,'x2':660,'y2':155},
            {'kind':'rect','x':660,'y':110,'width':290,'height':95},
            {'kind':'text','x':675,'y':145,'text':'判据冻结后才进行样片比较'},
            {'kind':'text','x':675,'y':180,'text':'当前：存档观察，等待验证'},
            {'kind':'arrow','x1':805,'y1':205,'x2':805,'y2':330},
            {'kind':'text','x':820,'y':265,'text':'破损 / 失稳'},
            {'kind':'rect','x':565,'y':330,'width':385,'height':95,'semantic':'hypothesis'},
            {'kind':'text','x':580,'y':365,'text':'停止、隔离样片、保留异常数据'},
            {'kind':'text','x':580,'y':400,'text':'记录原因；另立返工方案，不直接回投'},
            {'kind':'text','x':65,'y':470,'text':'H 教学工艺；仪器、载荷和判据待确定，不表示试验已执行。'}])
    return [electrical,mechanical,process]


def run(output,browser=None):
    output=Path(output).resolve()
    if output.exists() and any(output.iterdir()):raise ValueError('use a new/empty example directory')
    output.mkdir(parents=True,exist_ok=True)
    record={'schema_version':'1.1','project':{'title':'工程原理图教学样例','maturity':'V0'},'routes':[],
            'parameters':[], 'figure_specs':examples(), 'claims':[
                {'id':'CLM-EX','evidence_status':'H','allowed_wording':'本文件展示电气端口、机械接触与工艺控制的绘图方法；三例均为教学假设，未取得实测证据。'}]}
    record_path=output/'research-record.json'
    source={'schema_version':'1.3','title':record['project']['title'],'subtitle':'黑白原理图 端口与接触关系 图文配合','cover_page':False,
            'research_record_path':'research-record.json',
            'figure_manifest_path':'figures/figure-manifest.json','critical_facts_policy':'bound',
            'sections':[{'title':'阅读说明','blocks':[{'type':'paragraph','claim_ref':'/claims/CLM-EX'}]}]}
    text=[
        '从左侧激励源沿上方支路读图：开关决定连接状态，限流元件改变充电过程，储能元件两端的电压由测量端口读取。测量端口画出两个连接点，避免把单端悬空读数误认为跨端测量。',
        '从输入力箭头开始读图：滑块向右运动，在左侧接触面向工件传力。工件右侧靠上止挡后停止，顶面的被保护区域不与止挡接触。止挡不能消除输入力，过载仍需独立的限力措施及验证。图中的间隙需要回到设计记录确定，不能从示意图比例量取。',
        '沿上方正常路径读取：先编号和保留对照，再保持同载荷、保持时间和恢复时间，分别记录位移、压痕及测量误差。右侧节点当前只存档观察，判据与仪器尚未确定。出现破损或失稳时沿向下的异常路径停止并隔离样片，保留不利数据；返工要另立方案，不能直接回投。该图说明工艺控制关系，没有记录任何实测结果。']
    for index,spec in enumerate(record['figure_specs']):
        cid='CLM-DOMAIN-'+str(index+1)
        record['claims'].append({'id':cid,'evidence_status':'H','allowed_wording':text[index],
                                 'conditions':'仅解释教学图，不作为现场方案','next_validation':'按实际工况另立验证协议'})
        source['sections'].append({'title':spec['title'],'page_break_before':True,'blocks':[
            {'type':'figure','figure_ref':spec['id']}, {'type':'paragraph','claim_ref':'/claims/'+cid},
            {'type':'paragraph','text':'读者复核：沿真实连接或接触关系复述作用路径，指出一个可能失效的环节，再对照正文解释。'}]})
    record_path.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    figure_manifest=build_figures(record_path,output/'figures',browser)
    source['research_record_sha256']=digest(record_path)
    path=output/'report-source.json';path.write_text(json.dumps(source,ensure_ascii=False,indent=2),encoding='utf-8')
    report=build_report(path,output/'engineering-examples.docx')
    receipt={'report':report,'figures':figure_manifest,'visual_review':'pending','engineering_validation':'not-performed'}
    (output/'example-receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--png-browser')
    args=parser.parse_args();print(json.dumps(run(args.output,args.png_browser),ensure_ascii=False,indent=2))
