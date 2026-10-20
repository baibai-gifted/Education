"""Create auxiliary learning-module labels without changing source questions.

Standard-library only. Run from any directory:
    python classify_modules.py
    python classify_modules.py --input questions-raw.json --output learning-modules.json

This is navigation metadata, not a claim about original chapters or correctness.
Explicit document titles and meaningful source headings take precedence. Otherwise
the question, options, citation and explanation receive weighted keyword scores.
Unmatched cases use nearby well-supported questions from the same worksheet
only when both sides agree; general questions retain a general module.
The mapping is deterministic and keyed by the stable source-sheet/Excel-row ID.
"""

from collections import Counter
from pathlib import Path
import argparse
import hashlib
import json
import re


MODULES = (
    "国防建设与国防教育",
    "国家安全与国防动员",
    "国际形势与军事战略",
    "军事思想与军史",
    "战争形态与作战理论",
    "武器装备与军事科技",
    "条令队列与内务",
    "纪律规定与功勋奖惩",
    "军事训练与应急防护",
    "军队组织与综合常识",
)

# First explicit title in the question wins. A cited alternative answer must not
# override the document actually named in the stem.
TITLE_RULES = (
    (7, r"纪律条令|功勋荣誉|军人荣誉|军队奖励"),
    (6, r"队列条令|内务条令|国旗法|国歌法"),
    (1, r"国家安全法|国家情报法|反间谍法|反恐怖主义法|保密法|生物安全法|网络安全法|核安全法|密码法|反分裂国家法|陆地国界法|领海及毗连区法|兵役法|征兵工作条例|预备役人员法|退役军人|军人地位|军人抚恤|烈士褒扬|人民防空法|境外非政府组织"),
    (0, r"国防法|国防教育法|爱国主义教育法|军事设施保护法|军事设施保护条例"),
    (3, r"孙子|吴子|六韬|尉缭|司马法|武经|孙膑|李卫公|太白阴经|纪效新书|筹海图编|战争论|国防论|论持久战|中国革命|井冈山|星星之火|为人民服务|八一宣言|人民军队忠于党|习近平论强军"),
    (2, r"海洋法公约|开罗宣言|波茨坦公告|印太战略|中国的军事战略"),
    (5, r"无人驾驶航空器|无人机"),
    (9, r"文职人员条例|宪法|治安管理处罚法"),
)

# Meaningful headings only: “第一章 总则” or bare article numbers are deliberately
# not treated as knowledge categories because they recur across unrelated laws.
HEADING_RULES = (
    (7, r"功勋|荣誉表彰|处分|纪律的|特殊措施|控告和申诉|奖惩"),
    (6, r"日常制度|日常管理|军容风纪|内部关系|军人宣誓|军旗|军徽|礼节|军事礼仪|队列|单个军人|分队.*队形|军人职责|与军外单位和人员的交往"),
    (8, r"战伤|救护|防护|野外|战术基础|射击|行军|军事地形|学生军事训练"),
    (1, r"国家安全|国家秘密|保密制度|人民防空|国防动员|国防交通|征兵|体格检查|政治考核|审定新兵|优待与安置|退役军|兵役|预备役|国界|边境|领海|反间谍|反恐怖|涉密|平时征集|服役待遇|抚恤优待|军人死亡抚恤|安全防范|调查处置|历史的十字路口|化解风险|维护党的执政地位|提高人民群众获得感|发展和安全|开放和安全"),
    (0, r"中国国防|国防职权|国防经费|国防资产|国防科研|军事采购|国防教育|爱国主义|军事禁区|军事管理区|军事设施|防御性国防|国防和军队|军队使命任务"),
    (3, r"军事思想|军史|人民战争|毛泽东|孙子|兵法"),
    (4, r"现代战争|战争形态|联合作战|信息化战争|智能化战争|新军事革命"),
    (5, r"信息化装备|武器装备|高技术|军事科技|无人驾驶航空器|飞行活动"),
    (2, r"国际安全形势|国际战略|国际形势|周边安全|共同安全|安全共同体|全球安全倡议"),
)

# Terms added after inspecting real short stems, generic stems with substantive
# options, and the original source's recurring internal-management sections.
EXTRA_KEYWORDS = (
    r"国防活动|国防设施|国防后备|军队建设|军队发展|军队性质|军队的性质|军队的宗旨|基层建设|军事政策制度|军事政策|军事制度改革|强国强军|强大的军队|现代化正规化|国防发展的|国防是|国防就是|国防事业|我国国防|自卫型国防|扩张型国防|联盟型国防|中立型国防|我军.*改革|军队.*改革",
    r"国家生存|国家的生存|维护统一|领土完整|国家主权|一个中国|台湾独立|香港基本法|澳门基本法|一国两制|服现役|抚恤|因公牺牲|残疾军人|边防|海防|国土防卫|内外网|互联网邮箱|邮件系统|邮箱密码|网络治理|信息安全|军事安全领域|重大安全领域|放射性废物|核设施|核材料|能源发展|能源供给|能源需求|发展和安全|尊重和优待|军人.*权益",
    r"陆上邻国|陆地邻国|接壤|外交政策|外交关系|外交活动|周边环境|周边形势|安全局势|战争与和平|和平与战争|国际统一战线|国家的根本性问题|政党.*根本性问题|霸权|核共享|核不扩散|不结盟|安全观|世界.*动荡|世界.*和平|世界.*局势|当代世界|战略目的|战略功能|战略行动|战略任务|战略力量|南沙|西沙|红海危机|胡塞武装|德黑兰宣言|开罗宣言|雅尔塔|波茨坦|大变局|世界之变",
    r"强军目标|听党指挥|能打胜仗|作风优良|党对(?:人民)?军队.*领导|习近平主席|习近平总书记|习近平指出|习主席|党的绝对领导|革命的政治工作|理论联系实际|马克思主义.*战争|政治工作|红色基因|革命军人|对党忠诚|三个绝对|三大民主|党组织建设|建党建军|人民军队.*根本保证|毛主席|延安整风|诉苦三查|新式整军|战役战斗|野战军|军事矛盾|军事领域.*矛盾|集中兵力|出其不意|避实就虚|攻其不备|兵贵神速|攻心为上|先胜思想|全胜思想|战胜思想|致人而不致于人|兵者|知彼|人和武器|人.*决定.*作用|武器.*决定.*人|人.*不是物|研究和指导战争|组织建设.*党|党委.*集体领导|中共.*大|党的[“”一二三四五六七八九十百0-9]+大|党的第.*全国代表大会|革命史|党史|法西斯|南京大屠杀|西安事变|大别山|刘邓|人民军队.*发展史|有利决战|慎重初战",
    r"战争本质|战争理论|战争特点|战争的特点|战斗力标准|战斗力这个|作战能力|打仗能力|打赢能力|一战必胜|决战决胜|一击必胜|以战止战|以武止戈|军事平均主义|局部优势|战争.*制胜|作战原则|机械化武器|火力打击|作战制胜",
    r"武器系统|信息化武器|武器的战斗|动能拦截|拦截弹|科技的威力|科技是|科技实力|核力量|火力|无线电测向|无线电监测|无线电监控|无线电侦察|频谱|天线|天馈线|测向|射频|无线电技术|军事通信|通信技术|无线通信|无线电波|波段|电波传播|超短波|短波|超声波|红外|精确打击|信息处理|创新能力|核心技术|关键技术|技术自主|电子设备.*功能|监测网络|监测设备|监测站|无人智能装备|火药|火器|智能化工具|计算机",
    r"肩枪|双手持枪|挂枪|提枪|托枪|背枪|持枪动作|持号|司号员|誓师大会|授装仪式|接装|颁发命令状|典礼仪式|纪念仪式|葬礼仪式|鸣枪礼|入伍仪式|退役仪式|晋升.*军衔仪式|仪式曲|献花曲|哀悼号|军官.*基本职责|旅.*长.*职责|军事工作.*职责|军外交往|军外单位|举止容|举止要求|举止行为|军人举止|三分四定|装备操作人员|装备使用管理|装备管理|安全管理.*人员|军队单位.*安全管理|军人.*社会活动|酗酒|酒后|迷信活动|军人.*宗教|实名制管理|智能电子设备.*管理|班务会|排务会|连务会|行政会议|军人大会|资产管理|军队车辆|派车命令|军车|印章使用|军队印章|公章|军队单位.*检查|军队单位.*登记|军队单位.*统计|重大安全隐患",
    r"军队的纪律|解放军的纪律|纪律严明|纪律的严肃性|三大纪律|八项注意|有令必行|有禁必止|纪律面前|禁止.*违纪|奖励.*实施|功勋荣誉|军人和军队单位的奖励",
    r"实战训练|以战领训|以训促战|训风|严格训练|从难从严|军事基础训练|战备训练|战备工作|训练水平|训练质量|训练考核|训战|训练组织|战场急救|初级卫生|化学侦察|生物侦察|辐射侦察|侦毒|滤毒|防毒通道|集体防护|工事防护|防护工程|去污|掩蔽|躲避空袭|防空警报|弹道.*瞄准|射击.*弹道|正压|简易防护|军事课|军事理论课|军事理论设置|军事课教学大纲|学生军事|军事理论教学",
    r"军队的根本职能|军队根本职能|根本职能定位|人民军队.*组成|军队人员|军队体制|官兵关系|党支部|党小组|军队党委|思想教育|军事人才|人才强军|后勤|基层强|人民军队.*培养人|人民军队.*教育人|大熔炉|大学校|有灵魂|有本事|有血性|有品德|我国经济体制|社会主义市场经济|党的指导理论|三严三实|理论的威力|马克思主义学风|中国特色社会主义思想|民兵|敢于斗争|敢于胜利|艰苦奋斗|勤俭节约|作风建设|反对.*浪费|中国正处在",
)

# Each regex contributes once per text field. Distinctive concepts carry more
# weight than generic words such as “安全”“训练”“军人”, which are not triggers.
KEYWORDS = (
    (
        r"国防建设|国防政策|国防白皮书|国防法规|国防法|国防的|现代国防|古代国防|全民国防|防御性国防|国防类型|国防观|国防目的|国防力量|国防职权",
        r"国防教育|爱国主义教育|爱国精神|国防意识|国防观念|国防精神|学校国防|社会国防|国防知识|民族精神|国防义务",
        r"国防经费|国防开支|国防资产|军事采购|国防科研生产|军事设施|军事禁区|军事管理区|国防科技工业|军民融合|军地协同|军队现代化|国防现代化|军队改革|国防和军队改革",
        r"建军一百年|世界一流军队|军队使命任务|四个战略支撑|国防动员体制",
    ),
    (
        r"国家安全|总体安全观|总体国家安全观|非传统安全|传统安全|人民安全|政治安全|经济安全|军事安全|文化安全|社会安全|科技安全|生态安全|网络安全|数据安全|粮食安全|能源安全|生物安全|金融安全|核安全|太空安全|海洋安全|海外利益安全",
        r"保密|泄密|国家秘密|绝密|机密|涉密|密级|定密|解密|密件|密品|国家情报|情报工作机构|反间谍|间谍行为|间谍活动|恐怖主义|反恐|恐怖活动|暴恐|境外非政府组织|密码管理",
        r"征兵|兵役|应征|新兵|入伍|义务兵|预备役|兵员|退役军人|退役士兵|退役军官|退出现役|优抚|优待抚恤|军人抚恤|烈士|军属|军人地位|权益保障|安置条例|转业军官",
        r"国防动员|人民防空|人防工程|动员令|经济动员|交通动员|国防交通|武装动员|国家动员|军事动员|民用资源|征用|反分裂|台独|国家统一|祖国统一|陆地国界|界标|边境管理|领海|毗连区|领土主权|国土安全|国土完整",
    ),
    (
        r"国际形势|国际安全形势|国际战略|战略环境|战略格局|战略形势|军事战略|国家战略|战略目标|战略利益|战略手段|战略指导|战略方针|战略体系|战略的|战略是|战略要素|战略能力",
        r"周边安全|周边国家|邻国|边界争端|地缘|国际关系|大国关系|大国竞争|国际秩序|世界格局|世界多极化|单极格局|两极格局|多极格局|两极对抗|冷战|和平与发展|时代主题|安全共同体|全球安全倡议|共同安全|核威慑|核政策|不首先使用核武器",
        r"北约|欧盟|联合国|安理会|东盟|上合组织|金砖|中俄|中美|中日|美俄|美日|印太|俄乌|乌克兰|巴以|以色列|巴勒斯坦|朝鲜半岛|中东|南海|东海|台海|马六甲|恐怖袭击|北方四岛|南千岛|钓鱼岛|中印边界|中印边境|亚太地区",
        r"超级大国|霸权主义|强权政治|军备竞赛|军控|裁军|安全合作|军事同盟|军事集团|军事合作|军事外交|维和|国际维和|海外军事行动|全球治理|共同发展|军力排名|综合国力",
    ),
    (
        r"军事思想|强军思想|毛泽东|邓小平|江泽民|胡锦涛|习近平.*军事|习近平.*强军|人民战争|人民军队建设思想|积极防御思想|战争观|战争与政治|战争和政治|战争与经济|战争和经济|军事辩证|战争认识|军事理论家|军事著作",
        r"孙子|孙武|孙膑|吴起|尉缭|司马法|六韬|武经|李靖|戚继光|克劳塞维茨|若米尼|马汉|杜黑|马基雅维利|富勒|利德尔|兵法|不战而屈|知己知彼|知彼知己|上兵伐谋|避实击虚|奇正|重道轻器",
        r"解放战争|抗日战争|抗美援朝|红军|八路军|新四军|井冈山|遵义会议|南昌起义|秋收起义|三湾改编|广州起义|八一南昌|土地革命|大革命时期|工农武装|长征|四渡赤水|百团大战|平型关|台儿庄|辽沈战役|淮海战役|平津战役|渡江战役|三大战役|围剿|兵团战史|革命根据地|新民主主义革命|军队创建|建军节|中国共产党成立|辛亥革命|五四运动|鸦片战争|甲午战争|抗战|抗联|戚家军",
        r"持久战|十大军事原则|军队的宗旨|为人民服务|枪指挥党|党指挥枪|党对军队绝对领导|军队政治工作|三大纪律八项注意|农村包围城市|武装夺取政权|国共|黄埔军校|第一支.*军队",
    ),
    (
        r"战争形态|现代战争|机械化战争|信息化战争|智能化战争|冷兵器战争|热兵器战争|冷兵器时代|热兵器时代|机械化时代|信息化时代|工业时代|战争演变|战争样式|战争形势|战争发展|新军事革命|军事变革|军事革命",
        r"联合作战|一体化作战|体系作战|多域作战|混合作战|混合战争|非对称作战|精确作战|智能作战|制信息权|制网络权|制空权|制海权|制天权|战场空间|作战空间|作战样式|作战要素|作战体系|作战力量|作战行动|作战模式|作战理论|作战效果|战争制胜|战争致胜|战斗力生成|战略突袭|先发制人|闪击战|登陆作战|空地一体|信息战|电子战|网络战|心理战|舆论战|法律战|超限战|认知战|网络中心战",
        r"海湾战争|科索沃战争|阿富汗战争|伊拉克战争|马岛战争|六次中东战争|中东战争|越南战争|两次世界大战|第一次世界大战|第二次世界大战|作战指挥|军事斗争准备|战争动员|战争潜力|军事斗争|战争实践|战争胜负|战争的主体|战争主体|战争的本质|战争的性质|战争的分类",
    ),
    (
        r"武器装备|信息化装备|精确制导武器|精确制导|导弹|弹道|弹头|巡航|核武器|原子弹|氢弹|中子弹|核弹|核裂变|核聚变|核爆炸|化学武器|生物武器|激光武器|微波武器|电磁脉冲|非致命武器|动能武器|新概念武器|高超声速|杀伤半径",
        r"坦克|装甲车|战斗机|歼击机|轰炸机|预警机|直升机|航空母舰|航母|驱逐舰|护卫舰|潜艇|核潜艇|舰载机|战列舰|火炮|榴弹炮|迫击炮|火箭炮|步枪|冲锋枪|机枪|手枪|枪械|子弹|无人机|无人驾驶航空器|无人作战平台",
        r"军事高技术|军事科技|信息技术|侦察技术|侦察监视|雷达|声纳|卫星|北斗|导航系统|导航技术|遥感|电子对抗|隐身|伪装技术|夜视|光电|人工智能|量子|区块链|大数据|云计算|物联网|生物技术|纳米|材料技术|航天|外层空间|空间站|载人飞船|数字化系统|电子信息系统|指挥自动化|指挥控制系统|C[⁴4]I|C4ISR|C3I|超视距",
        r"探测|传感器|制导|火控|电磁频谱|天基|空天|技术创新|科技创新|科技强军|科技兴军|国防科技|两弹一星|东风[一二三四五六七八九十0-9]|歼[一二三四五六七八九十0-9]|辽宁舰|山东舰|福建舰",
    ),
    (
        r"队列|立正|稍息|跨立|停止间|行进间|齐步|正步|跑步|礼步|踏步|移步|步速|步幅|脚跟|脚尖|摆臂|摆动|拳眼|握拳|踢腿|靠脚|齐正|分列式|阅兵|阅兵式|受阅|标兵|取齐|间隔.*厘米|距离.*厘米|解散|集合口令|口令.*下达|口令.*组成|队形|纵队|横队|军人宣誓",
        r"内务|军容|风纪|军服|着装|佩戴|军衔标志|标志服饰|军帽|帽徽|脱帽|敬礼|举手礼|注目礼|举枪礼|军人礼节|军旗|军徽|国旗|国歌|军歌|奏唱|升旗|降旗|升挂|一日生活|起床|就寝|作息|睡眠|午睡|午休|点名|请假|销假|查铺|查哨|晚点名|连队值日|营区|宿舍|铺位|请示报告|查寝|日常制度",
        r"伙食|食谱|炊事|给养员|司务长|食堂|军人委员会|零散人员|军人之间|首长与部属|部属与首长|内部关系|日常管理|值班员|交接班|文体活动|请示报告|保管.*物品|携带.*证件|军队礼仪|两腿分开|手指.*并拢",
    ),
    (
        r"纪律条令|纪律建设|维护.*纪律|违反.*纪律|遵守.*纪律|政治纪律|组织纪律|战备训练纪律|群众纪律|廉洁纪律|保密纪律|工作纪律|生活纪律|军事纪律|组织性.*纪律性",
        r"功勋|荣誉表彰|表彰|勋章|纪念章|荣誉称号|立功|嘉奖|授奖|奖励|受奖|奖惩|施奖|记功|表功|喜报|处分|违纪|撤职|降职|降级|开除军籍|严重警告|行政看管|特别措施|申诉|控告|惩戒|惩前毖后|治病救人|纪律检查|纪检|禁闭|军人荣誉|军队荣誉|军人必须把|服从命令|听从指挥",
    ),
    (
        r"军事训练|军事教育|军事教学|学生军训|军训|教学法|四会|训练大纲|训练计划|训练方法|训练原则|技能训练|军事技能|训练保障|体能训练|体能考核|战术基础|战术动作|单兵战术|匍匐|卧倒|跪姿|据枪|瞄准|击发|射击|实弹|靶标|靶纸|射手|枪支走火|验枪|装弹|退弹",
        r"防毒|防化|三防|防核|核生化|战伤|救护|急救|止血|包扎|骨折|烧伤|烫伤|中暑|冻伤|人工呼吸|心肺复苏|心脏按压|担架|伤员|自救|互救|防护动作|防护器材|个人防护|防护措施|洗消|沾染|毒剂|生物战剂|应急避险|应急疏散|灾害防护|空袭警报",
        r"野外|行军|宿营|露营|迷失|迷路|地图|地形图|等高线|地物|地貌|方位角|辨别方向|判断方向|寻找水源|求生|生存技能|口渴|饮水|饮食卫生|净水|比例尺|指北针|罗盘|战备等级|紧急集合|战备状态|防护.*冲击波|防护.*光辐射",
    ),
    (
        r"军队组织|武装力量|军兵种|军种|兵种|战区|军委机关|军委主席|中央军委|中央军事委员会|领导指挥体制|指挥机构|军事领导|军队编制|军队体制|文职人员|军官.*军衔|军衔.*等级|军衔制度|军队.*机构|人民解放军.*组成|海军.*组成|陆军.*组成|空军.*组成|火箭军.*组成|武警.*组成|海警|战略支援部队|信息支援部队|联勤保障部队|军事航天部队|网络空间部队|国防大学|军事科学院",
        r"二十大|十九大|十八大|党代会|中国特色社会主义|社会主义核心价值观|中华民族伟大复兴|中国梦|现代化强国|改革开放|全面深化改革|全面依法治国|全面从严治党|五位一体|四个全面|四个意识|两个维护|四个自信|绿水青山|碳达峰|碳中和|民生|共同富裕|教育强国|人类命运共同体|依法治军",
    ),
)

COMPILED = tuple(tuple(re.compile(x, re.I) for x in (*group, EXTRA_KEYWORDS[index])) for index, group in enumerate(KEYWORDS))
GENERIC = re.compile(r"^(?:第[一二三四五六七八九十百0-9]+[章节条]|总则|法律责任|管理职责|保障与监督|监督管理|附则|未分类|\s|[、，,。：:；;（）()\d])+$")


def compact(value):
    return re.sub(r"\s+", "", str(value or ""))


def classify_one(question):
    stem = compact(question.get("stem"))
    source = compact(question.get("sourceCitation") or question.get("topic"))
    options = compact(" ".join(str(x.get("text", "")) for x in question.get("options", [])))
    explanation = compact(question.get("explanation"))
    for title in re.findall(r"《([^》]+)》", stem):
        for index, pattern in TITLE_RULES:
            if re.search(pattern, title):
                return index, 100, "explicit-title"
    if re.search(r"仪式|典礼|鸣枪礼|持筒时|着作训服|着常服|着礼服", stem):
        return 6, 90, "regulation-semantics"
    if re.search(r"奖惩项目|另立.*奖惩", stem + options):
        return 7, 90, "regulation-semantics"
    for index, pattern in HEADING_RULES:
        if re.search(pattern, source):
            return index, 85, "source-heading"
    # Regulations governing personal devices and social contacts are internal
    # management questions, even when distractors contain technology vocabulary.
    if re.search(r"军队单位|所属人员|军人|官兵|私人", stem + options) and re.search(r"电子设备.*(?:使用|管理)|智能手机|智能眼镜|智能手环|智能手表|社会交往|婚恋|迷信活动|酒后驾驶|三分四定", stem + options):
        return 6, 80, "management-semantics"
    scores = [0.0] * len(MODULES)
    option_weight = 3 if len(stem) <= 40 and re.search(r"以下|下列|哪些|哪项|何种|正确的是|错误的是", stem) else 1.5
    for index, patterns in enumerate(COMPILED):
        for pattern in patterns:
            # Stem dominates distractor options; explanation helps short/generic
            # stems without treating an answer's correctness as verified.
            scores[index] += min(3, len(pattern.findall(stem))) * 6
            scores[index] += min(3, len(pattern.findall(options))) * option_weight
            scores[index] += min(2, len(pattern.findall(explanation))) * 1.5
            if not GENERIC.fullmatch(source):
                scores[index] += min(2, len(pattern.findall(source))) * 3
    best = max(range(len(scores)), key=lambda i: (scores[i], -i))
    if scores[best] == 0:
        return 9, 0, "general-fallback"
    ordered = sorted(scores, reverse=True)
    margin = ordered[0] - ordered[1]
    return best, scores[best], "keywords" if margin >= 3 else "close-keywords"


def classify_all(questions):
    results = [classify_one(q) for q in questions]
    # A narrow worksheet-local tie-breaker is used only when no text keyword
    # matched at all, and both sides have the same clear label within 2 rows.
    # It never crosses a worksheet or overrides a textual classification.
    for pos, (index, score, reason) in enumerate(results):
        if score:
            continue
        question = questions[pos]
        nearby = []
        for direction in (-1, 1):
            for distance in (1, 2):
                other_pos = pos + distance * direction
                if not 0 <= other_pos < len(questions):
                    continue
                other = questions[other_pos]
                if other.get("sourceSheetIndex") != question.get("sourceSheetIndex"):
                    continue
                other_result = results[other_pos]
                if other_result[1] >= 6 and other_result[2] not in ("close-keywords", "neighbor-context"):
                    nearby.append(other_result[0])
                    break
        if len(nearby) == 2 and nearby[0] == nearby[1]:
            results[pos] = (nearby[0], 0, "neighbor-context")
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path(__file__).with_name("questions-raw.json"))
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("learning-modules.json"))
    args = parser.parse_args()
    source_bytes = args.input.read_bytes()
    questions = json.loads(source_bytes)
    if not isinstance(questions, list) or not questions:
        raise ValueError("Input must be a nonempty question list")
    if any(not isinstance(q.get("id"), str) or not q["id"] for q in questions):
        raise ValueError("Every question must have a stable string ID")
    if len({q["id"] for q in questions}) != len(questions):
        raise ValueError("Duplicate IDs would lose source rows")
    results = classify_all(questions)
    mapping = {q["id"]: MODULES[result[0]] for q, result in zip(questions, results)}
    args.output.write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    assert args.input.read_bytes() == source_bytes, "Source changed during classification"
    print(json.dumps({
        "questions": len(mapping),
        "modules": {module: sum(label == module for label in mapping.values()) for module in MODULES},
        "methods": dict(Counter(x[2] for x in results)),
        "sourceSha256": hashlib.sha256(source_bytes).hexdigest(),
        "meaning": "Auxiliary navigation labels; original text, citations, answers and topics are unchanged.",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
