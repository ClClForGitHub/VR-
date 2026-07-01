import {
  project as mockProject,
  references as mockReferences,
  concepts as mockConcepts,
  subjects as mockSubjects,
  sceneAssets as mockSceneAssets,
  deliveryFiles as mockDeliveryFiles,
  sceneObjects as mockSceneObjects,
  cameraPresets as mockCameraPresets,
  allAssets as mockAllAssets,
} from '../data/mockProject.js';

const PHASE_TO_SCREEN = {
  INTAKE: 'intake',
  SCENE_SPEC_DRAFT: 'intake',
  SCENE_SPEC_READY: 'intake',
  CONCEPT_GENERATION: 'reveal',
  CONCEPT_REVIEW: 'concept-review',
  CONCEPT_APPROVED: 'model-review',
  SUBJECT_ASSET_GENERATION: 'model-review',
  SCENE_ASSET_GENERATION: 'model-review',
  SUBJECT_ASSET_QA: 'model-review',
  SCENE_ASSET_ADAPTATION: 'model-review',
  BLENDER_ASSEMBLY_PLANNING: 'composition',
  BLENDER_ASSEMBLY_EXECUTION: 'composition',
  BLENDER_PREVIEW: 'final-review',
  BLENDER_EDIT: 'final-review',
  DELIVERY: 'delivery',
};

const PHASE_LABELS = {
  INTAKE: '需求输入',
  SCENE_SPEC_DRAFT: '需求整理',
  SCENE_SPEC_READY: '需求就绪',
  CONCEPT_GENERATION: '概念生成',
  CONCEPT_REVIEW: '概念确认',
  CONCEPT_APPROVED: '概念已确认',
  SUBJECT_ASSET_GENERATION: '模型生成',
  SCENE_ASSET_GENERATION: '场景生成',
  SUBJECT_ASSET_QA: '模型验收',
  SCENE_ASSET_ADAPTATION: '场景适配',
  BLENDER_ASSEMBLY_PLANNING: '场景组装',
  BLENDER_ASSEMBLY_EXECUTION: '场景组装',
  BLENDER_PREVIEW: '最终验收',
  BLENDER_EDIT: '最终调整',
  DELIVERY: '交付',
};

const ARTIFACT_IMAGE_TYPES = new Set([
  'CONCEPT_IMAGE',
  'SUBJECT_CONCEPT_IMAGE',
  'SCENE_CONCEPT_IMAGE',
  'PREVIEW_RENDER',
]);

const SUBJECT_MODEL_TYPES = new Set(['SUBJECT_3D_ASSET']);
const SCENE_MODEL_TYPES = new Set(['SCENE_3D_ASSET', 'BLENDER_SCENE', 'VIEWER_SCENE']);

export class RuntimeAdapter {
  constructor({ baseUrl = '' } = {}) {
    this.baseUrl = (baseUrl || '').replace(/\/$/, '');
  }

  async request(path, options = {}) {
    const url = `${this.baseUrl}${path}`;
    const response = await fetch(url, {
      headers: { Accept: 'application/json', ...(options.headers || {}) },
      ...options,
    });

    const text = await response.text();
    let payload = {};
    if (text) {
      try {
        payload = JSON.parse(text);
      } catch {
        throw new Error(`Runtime response was not JSON: ${response.status} ${url}`);
      }
    }

    if (!response.ok) {
      throw new Error(payload.error || `Runtime request failed: ${response.status} ${url}`);
    }
    return payload;
  }

  listRuns() {
    return this.request('/api/runs');
  }

  getRun(runKey) {
    return this.request(`/api/runs/${encodeURIComponent(runKey)}`);
  }

  getRunBundle(runKey) {
    return this.request(`/api/runs/${encodeURIComponent(runKey)}/bundle`);
  }

  fileUrl(runKey, relativePath) {
    const query = new URLSearchParams({ path: relativePath });
    return `${this.baseUrl}/api/runs/${encodeURIComponent(runKey)}/file?${query}`;
  }

  normalizeFileUrl(url) {
    if (!url) return null;
    if (/^https?:\/\//.test(url)) return url;
    return `${this.baseUrl}${url.startsWith('/') ? url : `/${url}`}`;
  }
}

export function createMockViewModel({ source = 'mock', error = null } = {}) {
  return {
    source,
    error,
    runKey: 'mock',
    phase: 'CONCEPT_REVIEW',
    publicPhaseLabel: '概念确认',
    currentScreen: 'concept-review',
    nextAction: { type: 'mock', label: '接受并进入下一步', enabled: true },
    project: mockProject,
    references: mockReferences,
    concepts: mockConcepts,
    subjects: mockSubjects,
    sceneAssets: mockSceneAssets,
    finalScene: mockSceneAssets.find((asset) => asset.status === '最终场景') ?? mockSceneAssets[0],
    assetMemory: { allAssets: mockAllAssets, concepts: mockConcepts, references: mockReferences },
    deliveryFiles: mockDeliveryFiles,
    sceneObjects: mockSceneObjects,
    cameraPresets: mockCameraPresets,
    fileManifest: [],
    runtime: { runs: [], bundle: null },
  };
}

export function normalizeRunIndex(rawRuns = []) {
  if (!Array.isArray(rawRuns)) return [];
  return rawRuns.map((run) => ({
    runKey: run.run_key,
    displayName: publicRunLabel(run),
    phase: run.frontend_phase ?? null,
    status: run.frontend_status_value ?? null,
    hasViewerScene: Boolean(run.has_viewer_scene),
    hasSceneState: Boolean(run.has_scene_state),
    modifiedAt: run.modified_at ?? null,
  })).filter((run) => run.runKey);
}

export function normalizeRuntimeBundle(rawBundle, adapter, { runs = [] } = {}) {
  if (!rawBundle || typeof rawBundle !== 'object') {
    return createMockViewModel({ source: 'mock', error: 'missing runtime bundle' });
  }

  const state = rawBundle.state ?? {};
  const frontendStatus = rawBundle.frontend_status ?? {};
  const sceneSpec = state.scene_spec ?? {};
  const phase = frontendStatus.phase ?? state.phase ?? 'INTAKE';
  const files = normalizeFileManifest(rawBundle, adapter);
  const artifacts = Array.isArray(state.artifacts) ? state.artifacts : [];
  const assetLibrary = Array.isArray(state.asset_library) ? state.asset_library : [];
  const imageArtifacts = artifacts.filter((artifact) => ARTIFACT_IMAGE_TYPES.has(artifact.artifact_type));
  const subjectArtifacts = artifacts.filter((artifact) => SUBJECT_MODEL_TYPES.has(artifact.artifact_type));
  const sceneArtifacts = artifacts.filter((artifact) => SCENE_MODEL_TYPES.has(artifact.artifact_type));
  const previewImage = findPreviewImage(rawBundle, adapter, artifacts, files);
  const concepts = imageArtifacts.length > 0
    ? imageArtifacts.map((artifact, index) => conceptFromArtifact(artifact, rawBundle, adapter, assetLibrary, index))
    : mockConcepts;
  const references = buildReferences(state);
  const subjects = subjectArtifacts.length > 0
    ? subjectArtifacts.map((artifact, index) => modelAssetFromArtifact(artifact, rawBundle, adapter, index, '主体模型'))
    : mockSubjects;
  const sceneAssets = buildSceneAssets(sceneArtifacts, rawBundle, adapter, previewImage);
  const finalScene = buildFinalScene(rawBundle, adapter, previewImage, sceneAssets);
  const sceneObjects = buildSceneObjects(rawBundle.scene_state);
  const cameraPresets = buildCameraPresets(rawBundle.scene_state);
  const deliveryFiles = buildDeliveryFiles(files);
  const allAssets = [...concepts, ...subjects, ...sceneAssets];

  return {
    source: 'backend',
    error: null,
    runKey: rawBundle.run_key,
    phase,
    publicPhaseLabel: PHASE_LABELS[phase] ?? phase,
    currentScreen: PHASE_TO_SCREEN[phase] ?? 'intake',
    nextAction: nextActionFor(frontendStatus, phase),
    project: {
      title: sceneSpec.title || publicRunLabel(rawBundle) || mockProject.title,
      user: frontendStatus.workflow || 'Runtime',
      styleName: Array.isArray(sceneSpec.style?.style_keywords)
        ? sceneSpec.style.style_keywords.join(' / ')
        : mockProject.styleName,
      updatedAt: frontendStatus.generated_at || rawBundle.summary?.generated_at || mockProject.updatedAt,
    },
    references,
    concepts,
    subjects,
    sceneAssets,
    finalScene,
    assetMemory: { allAssets, concepts, references },
    deliveryFiles,
    sceneObjects,
    cameraPresets,
    fileManifest: files,
    runtime: {
      runs,
      bundle: rawBundle,
      status: frontendStatus.status ?? null,
      progressLabel: frontendStatus.progress_label ?? null,
      missingFiles: rawBundle.missing_files ?? [],
    },
  };
}

function normalizeFileManifest(bundle, adapter) {
  const files = bundle.file_manifest?.files;
  if (!Array.isArray(files)) return [];
  return files.map((file) => ({
    id: file.label,
    label: labelForFile(file),
    type: typeForFile(file),
    kind: file.kind,
    relativePath: file.relative_path,
    exists: Boolean(file.exists),
    size: formatBytes(file.size_bytes),
    sizeBytes: file.size_bytes ?? 0,
    url: adapter.normalizeFileUrl(file.url),
  }));
}

function conceptFromArtifact(artifact, bundle, adapter, assetLibrary, index) {
  const libraryItem = assetLibrary.find((item) => item.artifact_id === artifact.artifact_id);
  const status = libraryItem?.review_status === 'rejected'
    ? '已拒绝'
    : libraryItem?.selection_status?.includes('selected')
      ? '已选用'
      : index === 0 ? '当前查看' : '历史版本';
  return {
    id: artifact.artifact_id,
    title: readableArtifactTitle(artifact, `概念图 ${index + 1}`),
    status,
    kind: artifact.artifact_type?.toLowerCase() ?? 'concept_image',
    image: artifactUrl(bundle, adapter, artifact) || mockConcepts[index % mockConcepts.length]?.image,
    createdAt: artifact.created_at,
    note: artifact.semantic_role || artifact.artifact_type || 'Runtime concept artifact',
  };
}

function modelAssetFromArtifact(artifact, bundle, adapter, index, modelType) {
  return {
    id: artifact.artifact_id,
    title: readableArtifactTitle(artifact, `${modelType} ${index + 1}`),
    version: `v${artifact.version ?? 1}`,
    status: index === 0 ? '当前查看' : '备选方案',
    image: findArtifactPreview(bundle, adapter, artifact) || mockSubjects[index % mockSubjects.length]?.image || mockSceneAssets[0].image,
    sourceConceptId: artifact.metadata?.source_concept_id ?? null,
    modelType,
    fileFormat: fileFormatFromArtifact(artifact),
    size: formatBytes(artifact.size_bytes),
    qa: ['文件存在', '格式识别', '运行记录', '派生状态'],
    url: artifactUrl(bundle, adapter, artifact),
  };
}

function buildReferences(state) {
  const referenceImages = state.reference_images || state.references || [];
  if (!Array.isArray(referenceImages) || referenceImages.length === 0) return mockReferences;
  return referenceImages.map((reference, index) => ({
    id: reference.image_id || reference.artifact_id || `reference_${index + 1}`,
    alias: reference.alias || `@图片${index + 1}`,
    title: reference.title || reference.filename || `参考图 ${index + 1}`,
    role: reference.binding_role || reference.role || '参考图',
    image: reference.url || reference.uri || mockReferences[index % mockReferences.length]?.image,
    bindingRole: reference.binding_role || 'other',
  }));
}

function buildSceneAssets(sceneArtifacts, bundle, adapter, previewImage) {
  const runtimeAssets = sceneArtifacts.map((artifact, index) => ({
    ...modelAssetFromArtifact(artifact, bundle, adapter, index, artifact.artifact_type === 'BLENDER_SCENE' ? 'Blender 场景' : '场景模型'),
    fileFormat: fileFormatFromArtifact(artifact),
  }));
  if (runtimeAssets.length === 0) return mockSceneAssets;
  if (previewImage) {
    runtimeAssets.push({
      id: 'runtime_final_preview',
      title: bundle.frontend_status?.blender_scene_id || '最终场景预览',
      version: 'runtime',
      status: '最终场景',
      image: previewImage,
      fileFormat: 'Preview + runtime files',
    });
  }
  return runtimeAssets;
}

function buildFinalScene(bundle, adapter, previewImage, sceneAssets) {
  const viewerFile = findFile(bundle, 'viewer_scene');
  const poster = previewImage || sceneAssets.find((asset) => asset.status === '最终场景')?.image || mockSceneAssets[1].image;
  return {
    id: bundle.frontend_status?.viewer_scene_id || 'runtime_final_scene',
    title: bundle.frontend_status?.blender_scene_id || bundle.display_name || '最终场景',
    version: bundle.frontend_status?.phase || 'runtime',
    status: bundle.frontend_status?.phase === 'DELIVERY' ? '最终场景' : '当前查看',
    image: poster,
    fileFormat: viewerFile?.exists ? 'GLB + runtime bundle' : 'Runtime preview',
    viewerSceneUrl: adapter.normalizeFileUrl(viewerFile?.url),
  };
}

function buildSceneObjects(sceneState) {
  const objects = sceneState?.objects;
  if (!Array.isArray(objects) || objects.length === 0) return mockSceneObjects;
  return objects.slice(0, 24).map((object, index) => ({
    id: object.object_id || object.id || `object_${index + 1}`,
    label: object.label || object.name || `场景对象 ${index + 1}`,
    type: object.type || object.semantic_role || 'object',
    visible: object.visible !== false,
  }));
}

function buildCameraPresets(sceneState) {
  const presets = sceneState?.camera_presets;
  if (!Array.isArray(presets) || presets.length === 0) return mockCameraPresets;
  return presets.slice(0, 12).map((preset, index) => ({
    id: preset.id || `camera_${index + 1}`,
    label: preset.label || preset.name || `镜头 ${index + 1}`,
  }));
}

function buildDeliveryFiles(files) {
  const existing = files.filter((file) => file.exists && ['state', 'summary', 'frontend_status', 'delivery_handoff', 'scene_state', 'viewer_scene', 'delivery_package'].includes(file.id));
  if (existing.length === 0) return mockDeliveryFiles;
  return existing.map((file) => ({
    id: file.id,
    label: file.label,
    type: file.type,
    size: file.size,
    url: file.url,
  }));
}

function nextActionFor(frontendStatus, phase) {
  if (frontendStatus?.pending_action) {
    return { type: frontendStatus.pending_action.action_type || 'pending_action', label: '等待用户确认', enabled: true };
  }
  if (phase === 'CONCEPT_REVIEW') return { type: 'approve_concept', label: '接受并进入模型生成', enabled: true };
  if (phase === 'BLENDER_PREVIEW') return { type: 'approve_blender_preview', label: '确认交付', enabled: true };
  if (phase === 'DELIVERY') return { type: 'delivery', label: '下载交付文件', enabled: true };
  return { type: phase, label: PHASE_LABELS[phase] ?? '继续', enabled: false };
}

function findPreviewImage(bundle, adapter, artifacts, files) {
  const previewArtifact = artifacts.find((artifact) => artifact.mime_type?.startsWith('image/') && /preview|render|png|jpg/i.test(`${artifact.artifact_id} ${artifact.semantic_role} ${artifact.uri}`));
  if (previewArtifact) return artifactUrl(bundle, adapter, previewArtifact);
  const previewFile = files.find((file) => /preview|render|png|jpg/i.test(`${file.id} ${file.relativePath}`));
  return previewFile?.url || null;
}

function findArtifactPreview(bundle, adapter, artifact) {
  if (artifact.mime_type?.startsWith('image/')) return artifactUrl(bundle, adapter, artifact);
  const previewArtifactId = artifact.metadata?.preview_artifact_id;
  const artifacts = Array.isArray(bundle.state?.artifacts) ? bundle.state.artifacts : [];
  const previewArtifact = artifacts.find((item) => item.artifact_id === previewArtifactId);
  return previewArtifact ? artifactUrl(bundle, adapter, previewArtifact) : null;
}

function artifactUrl(bundle, adapter, artifact) {
  if (!artifact?.uri) return null;
  if (/^https?:\/\//.test(artifact.uri)) return artifact.uri;
  const uri = artifact.uri.replace(/\\/g, '/');
  const roots = [bundle.effective_run_dir, bundle.run_dir].filter(Boolean).map((root) => root.replace(/\\/g, '/').replace(/\/$/, ''));
  for (const root of roots) {
    if (uri.startsWith(`${root}/`)) {
      return adapter.fileUrl(runKeyForRoot(bundle, root), uri.slice(root.length + 1));
    }
  }
  return null;
}

function runKeyForRoot(bundle, root) {
  const normalizedRoot = root.replace(/\\/g, '/').replace(/\/$/, '');
  const normalizedRunDir = bundle.run_dir?.replace(/\\/g, '/').replace(/\/$/, '');
  if (!normalizedRunDir || normalizedRoot === normalizedRunDir) return bundle.run_key;
  const runsRoot = runsRootFromBundle(bundle);
  if (!runsRoot || !normalizedRoot.startsWith(`${runsRoot}/`)) return bundle.run_key;
  return encodeRuntimeRunKey(normalizedRoot.slice(runsRoot.length + 1));
}

function runsRootFromBundle(bundle) {
  const runDir = bundle.run_dir?.replace(/\\/g, '/').replace(/\/$/, '');
  const relativePath = bundle.relative_path?.replace(/\\/g, '/').replace(/\/$/, '');
  if (!runDir || !relativePath || !runDir.endsWith(relativePath)) return null;
  return runDir.slice(0, runDir.length - relativePath.length).replace(/\/$/, '');
}

function encodeRuntimeRunKey(relativePath) {
  const bytes = new TextEncoder().encode(relativePath);
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return `r_${btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')}`;
}

function findFile(bundle, label) {
  const files = bundle.file_manifest?.files;
  if (!Array.isArray(files)) return null;
  return files.find((file) => file.label === label) || null;
}

function labelForFile(file) {
  const labels = {
    state: 'state.json',
    summary: 'summary.json',
    frontend_status: 'frontend_status.json',
    delivery_handoff: 'delivery_handoff.json',
    scene_state: 'scene_state.json',
    viewer_scene: 'viewer_scene.glb',
    delivery_package: 'delivery_package.zip',
  };
  return labels[file.label] || file.relative_path || file.label;
}

function typeForFile(file) {
  const types = {
    state: '运行状态',
    summary: '运行摘要',
    frontend_status: '前端派生状态',
    delivery_handoff: '交付清单',
    scene_state: '场景对象状态',
    viewer_scene: '可交互 GLB',
    delivery_package: '交付压缩包',
  };
  return types[file.label] || file.kind || '运行文件';
}

function readableArtifactTitle(artifact, fallback) {
  return artifact.metadata?.display_name
    || artifact.metadata?.title
    || artifact.semantic_role
    || artifact.artifact_id
    || fallback;
}

function publicRunLabel(run) {
  return run.display_name || run.run_id || run.relative_path || 'Runtime Run';
}

function fileFormatFromArtifact(artifact) {
  if (artifact.mime_type === 'model/gltf-binary') return 'GLB';
  if (artifact.mime_type?.startsWith('image/')) return artifact.mime_type.replace('image/', '').toUpperCase();
  const suffix = artifact.uri?.split('.').pop();
  return suffix ? suffix.toUpperCase() : 'Runtime Asset';
}

function formatBytes(value) {
  if (!Number.isFinite(value) || value <= 0) return '未知大小';
  const units = ['B', 'KB', 'MB', 'GB'];
  let size = value;
  let index = 0;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }
  return `${size >= 10 || index === 0 ? size.toFixed(0) : size.toFixed(1)} ${units[index]}`;
}
