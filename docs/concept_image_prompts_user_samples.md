# Concept Image Prompts For User Samples

Updated: 2026-07-01

This document records the prompt layer for the three user-provided concept
image samples. It is meant for human review before the image MCP is called.

## 1. Agent System Rules

English prompt rules passed to `ConceptPromptPlanner`:

```text
ConceptPromptPlanner rules:
- Treat scene_spec as the source of truth for subjects, environment, camera, lighting, props, and constraints.
- For any subject that names an IP, franchise, game, anime, brand, or specific character, require explicit identity research evidence before writing generation prompts. If this node is delegated to an agent/MCP channel with web-search capability, that agent must search the web for the character/IP, prefer official sources, and summarize the verified identity in context before prompt writing. If no search evidence is present in context_json, do not rely on model memory; set requires_clarification=true or add identity_notes describing the missing research.
- Preserve exact subject identity. Use display_name, canonical_identity, identity_aliases, source_text_span, and reference_image_ids when present. Do not silently substitute or rename a character. If identity is uncertain, set requires_clarification=true and add open_questions.
- For every scene_spec subject with needs_2d_concept=true, create exactly one subject_prompts entry keyed by subject_id. Do not create subject prompts for procedural props or scene-service components.
- Subject concept prompts must be subject-only: clean studio/neutral background, full body or whole vehicle, readable silhouette, no scene environment, no unrelated props. When the subject has reference_image_ids or a subject_reference binding, the matching image_requirement must list those ids in input_reference_image_ids, set generation_mode='image_guided', and the prompt must explicitly preserve identity from those input images. Downstream image-generation MCP calls must attach/upload those reference image files as actual image inputs, not merely mention them in text.
- Scene concept prompts must be scene-only: environment, terrain, props, layout, lighting direction, and camera staging. They must exclude hero subjects and characters. When scene_reference images exist, list them in input_reference_image_ids.
- The final_preview_prompt is not a substitute for subject/scene prompts. It must be an art-directed target render prompt that combines the generated subject_concept image(s) and scene_concept image(s) as visual references. Its target_render image_requirement must set generation_mode='multi_image_composite' and source_requirement_ids to the subject_concept and scene_concept requirements it depends on. Downstream MCP calls must attach/upload the resolved source images for those source_requirement_ids.
- Use a higher beauty bar for the final target render: polished composition, appealing camera, coherent light direction, clear face/front orientation for characters, and enough scale to inspect the main subject.
- Keep uploaded user references scoped to their declared binding. A subject reference must not become scene content; a scene reference must not overwrite subject identity.
```

Chinese phrase-by-phrase translation:

```text
ConceptPromptPlanner rules = ConceptPromptPlanner 规则
Treat scene_spec as the source of truth = 把 scene_spec 当作事实来源
subjects / environment / camera / lighting / props / constraints = 主体 / 环境 / 相机 / 灯光 / 道具 / 约束
any subject that names an IP/franchise/game/anime/brand/specific character = 任何命名 IP/系列/游戏/动画/品牌/具体角色的主体
require explicit identity research evidence = 要求显式身份研究证据
delegated to an agent/MCP channel with web-search capability = 委派给有联网搜索能力的 agent/MCP 通道
search the web = 联网搜索
prefer official sources = 优先官方来源
summarize the verified identity = 总结已验证身份
do not rely on model memory = 不依赖模型记忆
requires_clarification=true = 需要澄清
identity_notes = 身份研究备注
Preserve exact subject identity = 保留精确主体身份
display_name / canonical_identity / identity_aliases / source_text_span / reference_image_ids = 显示名 / 规范身份 / 身份别名 / 原文片段 / 参考图 id
Do not silently substitute or rename = 不要静默替换或改名
needs_2d_concept=true = 需要二维概念图
one subject_prompts entry keyed by subject_id = 一个以 subject_id 为键的主体 prompt 条目
procedural props or scene-service components = 程序化道具或场景服务组件
Subject concept prompts must be subject-only = 主体概念 prompt 必须只含主体
clean studio/neutral background = 干净摄影棚/中性背景
full body or whole vehicle = 全身或完整车辆
readable silhouette = 可读轮廓
no scene environment / no unrelated props = 没有场景环境 / 没有无关道具
input_reference_image_ids = 输入参考图 id
generation_mode='image_guided' = 生成模式为图像引导
attach/upload as actual image inputs = 作为真实图像输入上传/附加
Scene concept prompts must be scene-only = 场景概念 prompt 必须只含场景
environment / terrain / props / layout / lighting direction / camera staging = 环境 / 地形 / 道具 / 布局 / 光照方向 / 相机舞台
exclude hero subjects and characters = 排除主角主体和角色
final_preview_prompt is not a substitute = 最终预览 prompt 不是替代品
art-directed target render prompt = 有艺术指导的目标渲染 prompt
combines generated subject_concept and scene_concept images = 组合已生成主体概念图和场景概念图
multi_image_composite = 多图合成
source_requirement_ids = 来源 requirement id
higher beauty bar = 更高审美标准
polished composition / appealing camera / coherent light direction = 精修构图 / 好看的相机 / 连贯光照方向
clear face/front orientation = 清晰脸部/正面朝向
scoped to their declared binding = 限定在声明绑定范围内
```

## 2. MCP Image Generation Handoff Template

English template for ChatGPT image / image MCP calls:

```text
Before image generation, perform web search for every named IP, franchise, game, brand, or specific character in this request. Prefer official sources. Summarize the verified identity, aliases, visual traits, and uncertainty. Do not generate from hidden memory alone.

Use the attached/uploaded reference images exactly as listed by input_reference_image_ids. If this requirement is image_guided, the referenced images are mandatory visual inputs. If this requirement is multi_image_composite, attach the resolved generated source images listed by source_requirement_ids.

Generate exactly one image for the current requirement. Obey the prompt boundary: subject-only, scene-only, or target-render composite. Do not leak subject identity into scene-only images. Do not leak scene background into subject-only images. No text, watermark, UI, logo overlay, or extra captions.
```

Chinese phrase-by-phrase translation:

```text
Before image generation = 生图之前
perform web search = 执行联网搜索
every named IP/franchise/game/brand/specific character = 每个命名 IP/系列/游戏/品牌/具体角色
Prefer official sources = 优先官方来源
Summarize verified identity, aliases, visual traits, uncertainty = 总结已验证身份、别名、视觉特征、不确定性
Do not generate from hidden memory alone = 不要只靠隐藏记忆生成
attached/uploaded reference images = 已附加/上传参考图
input_reference_image_ids = 输入参考图 id
mandatory visual inputs = 必需视觉输入
multi_image_composite = 多图合成
source_requirement_ids = 来源 requirement id
Generate exactly one image = 只生成一张图
prompt boundary = prompt 边界
subject-only / scene-only / target-render composite = 只含主体 / 只含场景 / 目标渲染合成
Do not leak subject identity into scene-only images = 场景图不要混入主体身份
Do not leak scene background into subject-only images = 主体图不要混入场景背景
No text, watermark, UI, logo overlay, or extra captions = 不要文字、水印、界面、logo 叠层或额外字幕
```

## 3. Sample 1: Wuthering Waves Phoebe And Phrolova Beach

Identity research targets:

```text
Search: Wuthering Waves Phoebe official character
Search: Wuthering Waves Phrolova 弗洛洛 official character
Resolved aliases: 菲比 / Phoebe, 弗糯糯 / 弗洛洛 / Phrolova
```

Subject prompt: Phoebe.

```text
Subject-only Q-version 菲比 from Wuthering Waves, identity verified by web search before generation, oversized head, simplified bright fantasy outfit, cute expression, clean neutral studio background, front three-quarter full-body silhouette. No beach, no sand, no chair, no sand castle, no water, no unrelated props, no text, no watermark.
```

Translation:

```text
Subject-only = 只包含主体
Q-version = Q版
菲比 from Wuthering Waves = 来自《鸣潮》的菲比
identity verified by web search before generation = 生成前通过联网搜索核查身份
oversized head = 大头比例
simplified bright fantasy outfit = 简化的明亮幻想服装
cute expression = 可爱表情
clean neutral studio background = 干净中性摄影棚背景
front three-quarter full-body silhouette = 正面三分之四全身轮廓
No beach/sand/chair/sand castle/water/unrelated props = 不要沙滩/沙子/椅子/沙堡/水/无关道具
No text/no watermark = 不要文字/水印
```

Subject prompt: Phrolova.

```text
Subject-only Q-version 弗洛洛 / Phrolova from Wuthering Waves, canonical identity resolved from user wording 弗糯糯 and verified by web search before generation, round chibi proportions, quiet mysterious conductor-like fantasy character mood, playful but slightly gothic outfit simplified for a readable full-body source image, clean neutral studio background, front three-quarter full-body silhouette. No beach, no sand, no chair, no sand castle, no water, no unrelated props, no text, no watermark.
```

Translation:

```text
Subject-only = 只包含主体
Q-version = Q版
弗洛洛 / Phrolova from Wuthering Waves = 来自《鸣潮》的弗洛洛 / Phrolova
canonical identity resolved from user wording 弗糯糯 = 规范身份由用户写法“弗糯糯”解析
verified by web search before generation = 生成前通过联网搜索核查
round chibi proportions = 圆润Q版比例
quiet mysterious conductor-like fantasy character mood = 安静神秘、指挥家感的幻想角色气质
playful but slightly gothic outfit = 活泼但略带哥特感的服装
simplified for a readable full-body source image = 为可读全身源图进行简化
clean neutral studio background = 干净中性摄影棚背景
front three-quarter full-body silhouette = 正面三分之四全身轮廓
No beach/sand/chair/sand castle/water/unrelated props = 不要沙滩/沙子/椅子/沙堡/水/无关道具
No text/no watermark = 不要文字/水印
```

Scene prompt:

```text
Scene-only sunny stylized beach, warm sand ground plane, shallow blue water, gentle waves, striped beach chair to the side, small sand castle in the foreground, shells, soft beach shadows, open placement area for two chibi characters. No characters, no humanoids, no Phoebe, no Phrolova, no text, no watermark.
```

Translation:

```text
Scene-only = 只包含场景
sunny stylized beach = 阳光风格化沙滩
warm sand ground plane = 暖色沙地平面
shallow blue water = 浅蓝海水
gentle waves = 柔和海浪
striped beach chair to the side = 侧边条纹沙滩椅
small sand castle in the foreground = 前景小沙堡
shells = 贝壳
soft beach shadows = 柔和沙滩阴影
open placement area for two chibi characters = 为两个Q版角色留出摆放空地
No characters/humanoids/Phoebe/Phrolova = 不要角色/人形/菲比/弗洛洛
No text/no watermark = 不要文字/水印
```

Target render prompt:

```text
High-artistry polished target render using the generated Phoebe subject concept, generated Phrolova subject concept, and generated beach scene concept as visual references: Q-version Wuthering Waves characters 菲比 and 弗洛洛 together on a sunny beach, with a striped beach chair and a small sand castle nearby, coherent warm daylight, appealing front three-quarter composition, both characters large enough to inspect, faces unobstructed. No text, no watermark.
```

Translation:

```text
High-artistry polished target render = 高艺术性精修目标渲染图
using generated Phoebe subject concept = 使用已生成菲比主体概念图
generated Phrolova subject concept = 已生成弗洛洛主体概念图
generated beach scene concept = 已生成沙滩场景概念图
as visual references = 作为视觉参考
Q-version Wuthering Waves characters = 《鸣潮》Q版角色
菲比 and 弗洛洛 together = 菲比和弗洛洛同框
on a sunny beach = 在阳光沙滩上
striped beach chair and small sand castle nearby = 旁边有条纹沙滩椅和小沙堡
coherent warm daylight = 连贯暖色日光
appealing front three-quarter composition = 好看的正面三分之四构图
large enough to inspect = 足够大便于检查
faces unobstructed = 脸部无遮挡
No text/no watermark = 不要文字/水印
```

## 4. Sample 2: Chibi Gwen On Chessboard

Identity research and references:

```text
Search: League of Legends Teamfight Tactics Chibi Gwen official
Subject input_reference_image_ids: image_little_gwen_ref
Reference file to upload to image MCP: /home/team/zouzhiyuan/image23D_Agent/tests/fixtures/images/little_gwen_reference.png
```

Subject prompt:

```text
Use uploaded input reference image image_little_gwen_ref as the mandatory subject identity reference. Before generation, search the web for League of Legends / Teamfight Tactics Chibi Gwen and verify that 小小格温 corresponds to Chibi Gwen. Generate a subject-only Q-version Little Gwen / Chibi Gwen character, preserving the uploaded reference image identity: cyan blue twin-tail hair, cute face, simplified fantasy outfit, magical blue scissor-like energy accents, clean neutral studio background, full-body front three-quarter view. Do not include chessboard, chess pieces, or scene background. No text, no watermark.
```

Translation:

```text
Use uploaded input reference image = 使用上传的输入参考图
image_little_gwen_ref = image_little_gwen_ref
mandatory subject identity reference = 必需的主体身份参考
Before generation = 生成前
search the web = 联网搜索
League of Legends / Teamfight Tactics Chibi Gwen = 英雄联盟 / 云顶之弈 小小格温
verify 小小格温 corresponds to Chibi Gwen = 确认“小小格温”对应 Chibi Gwen
subject-only = 只包含主体
Q-version Little Gwen / Chibi Gwen = Q版小小格温 / Chibi Gwen
preserving uploaded reference image identity = 保留上传参考图身份
cyan blue twin-tail hair = 青蓝色双马尾
cute face = 可爱脸
simplified fantasy outfit = 简化幻想服装
magical blue scissor-like energy accents = 蓝色魔法剪刀状能量装饰
clean neutral studio background = 干净中性摄影棚背景
full-body front three-quarter view = 全身正面三分之四视角
Do not include chessboard/chess pieces/scene background = 不要棋盘/棋子/场景背景
No text/no watermark = 不要文字/水印
```

Scene prompt:

```text
Scene-only large chessboard stage with alternating dark and light squares, many black and white pawns, rooks, bishops, knights, queen and king arranged around an empty central square, cool magical lighting, clean Blender-friendly layout, open central placement area for one chibi character. No characters, no Little Gwen, no humanoids, no text, no watermark.
```

Translation:

```text
Scene-only = 只包含场景
large chessboard stage = 大型棋盘舞台
alternating dark and light squares = 深浅交替格子
many black and white pawns/rooks/bishops/knights/queen/king = 许多黑白兵/车/象/马/后/王
arranged around an empty central square = 围绕空中央格摆放
cool magical lighting = 冷色魔法光照
clean Blender-friendly layout = 干净、适合 Blender 的布局
open central placement area = 中央留出摆放区域
for one chibi character = 给一个Q版角色
No characters/Little Gwen/humanoids = 不要角色/小小格温/人形
No text/no watermark = 不要文字/水印
```

Target render prompt:

```text
High-artistry polished target render using the generated image-guided Little Gwen subject concept and the generated chessboard scene concept as visual references: 小小格温 / Chibi Gwen from image_little_gwen_ref standing clearly on a large chessboard, surrounded by many black and white chess pieces that frame but do not block her, cool magical blue accents, coherent front three-quarter lighting, character large enough to inspect, face unobstructed. No text, no watermark.
```

Translation:

```text
High-artistry polished target render = 高艺术性精修目标渲染图
using generated image-guided Little Gwen subject concept = 使用已生成的图像引导小小格温主体概念图
generated chessboard scene concept = 已生成棋盘场景概念图
as visual references = 作为视觉参考
小小格温 / Chibi Gwen from image_little_gwen_ref = 来自 image_little_gwen_ref 的小小格温 / Chibi Gwen
standing clearly on a large chessboard = 清楚站在大型棋盘上
surrounded by many black and white chess pieces = 被许多黑白棋子围绕
frame but do not block her = 构成画面框架但不遮挡她
cool magical blue accents = 冷色蓝色魔法点缀
coherent front three-quarter lighting = 连贯正面三分之四光照
large enough to inspect = 足够大便于检查
face unobstructed = 脸部无遮挡
No text/no watermark = 不要文字/水印
```

## 5. Sample 3: Explorer Robot Rover On Moon

Identity/reference research:

```text
Search: lunar explorer rover robot visual reference, moon rover design, NASA lunar rover reference
No user-uploaded subject reference image.
```

Subject prompt:

```text
Before generation, search the web for real lunar rover / explorer robot rover visual references and summarize common design traits. Generate a subject-only compact explorer robot rover, rugged wheels, boxy sensor mast, small antenna, front cameras, white and gray dusty panels, clean neutral studio background, full vehicle visible, front three-quarter silhouette. Do not include moon terrain, craters, astronauts, stars, planets, or scene background. No text, no watermark.
```

Translation:

```text
Before generation = 生成前
search the web = 联网搜索
real lunar rover / explorer robot rover visual references = 真实月球车 / 探索机器人车视觉参考
summarize common design traits = 总结共同设计特征
subject-only = 只包含主体
compact explorer robot rover = 紧凑探索者机器人车
rugged wheels = 粗犷耐用车轮
boxy sensor mast = 方形传感器桅杆
small antenna = 小天线
front cameras = 前置摄像头
white and gray dusty panels = 白灰色带尘面板
clean neutral studio background = 干净中性摄影棚背景
full vehicle visible = 完整车辆可见
front three-quarter silhouette = 正面三分之四轮廓
Do not include moon terrain/craters/astronauts/stars/planets/scene background = 不要月面地形/坑/宇航员/星星/星球/场景背景
No text/no watermark = 不要文字/水印
```

Scene prompt:

```text
Scene-only moon surface with pitted lunar regolith, many small craters, dusty uneven ground, distant ridge, black sky, hard low-angle sunlight, open foreground area for rover placement. No rover, no astronaut, no vehicle, no text, no watermark.
```

Translation:

```text
Scene-only = 只包含场景
moon surface = 月球表面
pitted lunar regolith = 坑坑洼洼的月壤
many small craters = 许多小陨坑
dusty uneven ground = 布满尘土的不平地面
distant ridge = 远处山脊
black sky = 黑色天空
hard low-angle sunlight = 强烈低角度阳光
open foreground area for rover placement = 前景留出摆放月球车区域
No rover/astronaut/vehicle = 不要月球车/宇航员/车辆
No text/no watermark = 不要文字/水印
```

Target render prompt:

```text
High-artistry polished target render using the generated rover subject concept and generated moon-surface scene concept as visual references: a compact explorer robot rover on the moon, parked beside cratered pitted lunar regolith, low wide front three-quarter camera, hard coherent sunlight, long shadows, dark sky, rover large enough to inspect, clean readable silhouette. No text, no watermark.
```

Translation:

```text
High-artistry polished target render = 高艺术性精修目标渲染图
using generated rover subject concept = 使用已生成月球车主体概念图
generated moon-surface scene concept = 已生成月面场景概念图
as visual references = 作为视觉参考
compact explorer robot rover on the moon = 紧凑探索者机器人车在月球上
parked beside cratered pitted lunar regolith = 停在有陨坑且坑洼的月壤旁
low wide front three-quarter camera = 低机位广角正面三分之四相机
hard coherent sunlight = 强烈且方向一致的阳光
long shadows = 长阴影
dark sky = 黑色天空
rover large enough to inspect = 月球车足够大便于检查
clean readable silhouette = 干净可读轮廓
No text/no watermark = 不要文字/水印
```

