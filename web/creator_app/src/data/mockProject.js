export const stages = [
  { id: 1, key: 'intake', label: '需求输入' },
  { id: 2, key: 'concept', label: '概念确认' },
  { id: 3, key: 'model', label: '模型生成' },
  { id: 4, key: 'assembly', label: '场景组装' },
  { id: 5, key: 'delivery', label: '交付' },
];

export const screens = [
  { id: 'intake', label: '输入/绑定', stage: 1 },
  { id: 'reveal', label: '揭幕动画', stage: 2 },
  { id: 'concept-review', label: '概念审稿', stage: 2 },
  { id: 'feedback-compare', label: '反馈对比', stage: 2 },
  { id: 'model-review', label: '模型验收', stage: 3 },
  { id: 'asset-memory', label: '资产记忆', stage: 3 },
  { id: 'composition', label: '自由组合', stage: 4 },
  { id: 'final-review', label: '最终验收', stage: 5 },
  { id: 'delivery', label: '交付下载', stage: 5 },
];

const img = (name) => `/mock-assets/${name}`;

export const project = {
  title: 'VR - 世界观场景设定',
  user: 'CICIFORGE',
  styleName: 'Premium Cinematic Dark Creation Studio',
  updatedAt: '2026-07-01 14:32',
};

export const references = [
  {
    id: 'ref_subject_001',
    alias: '@图片1',
    title: '机械灵兽 · 霜牙',
    role: '主体参考',
    image: img('subject_mecha_beast.jpg'),
    bindingRole: 'subject',
  },
  {
    id: 'ref_scene_001',
    alias: '@图片2',
    title: '古老遗迹 · 破环拱门',
    role: '场景参考',
    image: img('scene_ruins_sunset.jpg'),
    bindingRole: 'scene',
  },
];

export const concepts = [
  {
    id: 'concept_v3',
    title: 'V3 当前方案',
    status: '已选用',
    kind: 'overall_concept',
    image: img('concept_overall_v3.jpg'),
    createdAt: '2026-07-01 14:32',
    note: '古老遗迹的回响，与未来机械的共鸣',
  },
  {
    id: 'concept_v2',
    title: 'V2 优化光影',
    status: '历史版本',
    kind: 'overall_concept',
    image: img('concept_alt_v2.jpg'),
    createdAt: '2026-07-01 13:20',
    note: '增强天光和主体边缘光。',
  },
  {
    id: 'concept_v1',
    title: 'V1 初稿',
    status: '历史版本',
    kind: 'overall_concept',
    image: img('concept_alt_v1.jpg'),
    createdAt: '2026-06-30 18:45',
    note: '初始构图和氛围草案。',
  },
  {
    id: 'concept_rejected_001',
    title: 'V0 废弃方案',
    status: '已拒绝',
    kind: 'overall_concept',
    image: img('concept_rejected.jpg'),
    createdAt: '2026-06-29 11:10',
    note: '构图压迫感不足，可归档可复用。',
  },
];

export const subjects = [
  {
    id: 'subject_beast_v12',
    title: '机械灵兽 · 霜牙',
    version: 'v1.2',
    status: '当前查看',
    image: img('subject_mecha_beast.jpg'),
    sourceConceptId: 'concept_v3',
    modelType: '主体模型',
    fileFormat: 'GLB',
    size: '12.4 MB',
    qa: ['拓扑结构', '法线方向', 'UV 展开', '贴图完整性', '比例一致性'],
  },
  {
    id: 'subject_warrior_v11',
    title: '重装机甲 · 战士',
    version: 'v1.1',
    status: '备选方案',
    image: img('model_review_strip.jpg'),
    sourceConceptId: 'concept_v2',
    modelType: '主体模型',
    fileFormat: 'GLB',
    size: '18.2 MB',
    qa: ['拓扑结构', '材质贴图', '骨架预留'],
  },
];

export const sceneAssets = [
  {
    id: 'scene_ruins_v12',
    title: '古老遗迹',
    version: 'v1.2',
    status: '已选用',
    image: img('scene_ruins_sunset.jpg'),
    fileFormat: 'GLB',
  },
  {
    id: 'scene_final_v13',
    title: '浮空遗迹 · 最终合成',
    version: 'v1.3',
    status: '最终场景',
    image: img('final_scene_preview.jpg'),
    fileFormat: 'GLB + .blend',
  },
];

export const deliveryFiles = [
  { id: 'blend', label: 'scene_final.blend', type: 'Blender 场景文件', size: '512 MB' },
  { id: 'glb', label: 'viewer_scene.glb', type: '可交互 3D 预览', size: '286 MB' },
  { id: 'preview', label: 'preview_4k.jpg', type: '预览主图（4K）', size: '8.2 MB' },
  { id: 'state', label: 'scene_state.json', type: '场景状态配置', size: '32 KB' },
  { id: 'camera', label: 'camera_presets.cam', type: '相机机位预设', size: '128 KB' },
  { id: 'readme', label: 'readme.txt', type: '使用说明', size: '6 KB' },
];

export const cameraPresets = [
  { id: 'director', label: '导演镜头' },
  { id: 'wide', label: '全景横屏' },
  { id: 'low', label: '低角度' },
  { id: 'tracking', label: '跟随镜头' },
  { id: 'top', label: '俯视鸟瞰' },
  { id: 'close', label: '细节特写' },
];

export const sceneObjects = [
  { id: 'obj_subject_beast', label: '机械灵兽 · 霜牙', type: '主体', visible: true },
  { id: 'obj_gate', label: '悬浮遗迹拱门', type: '场景', visible: true },
  { id: 'obj_energy_core', label: '能量核心塔', type: '场景', visible: true },
  { id: 'obj_clouds', label: '云层体积', type: '氛围', visible: true },
  { id: 'obj_water', label: '地面反射面', type: '材质', visible: true },
];

export const allAssets = [
  ...concepts,
  ...subjects,
  ...sceneAssets,
];
