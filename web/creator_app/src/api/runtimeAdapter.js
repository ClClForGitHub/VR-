import {
  project as mockProject,
  referenceSlots as mockReferenceSlots,
  references as mockReferences,
  entities as mockEntities,
  assetVersions as mockAssetVersions,
  approvedConceptSelection as mockApprovedConceptSelection,
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
  CONCEPT_GENERATION: 'intake',
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
  'FINAL_PREVIEW_IMAGE',
  'PREVIEW_RENDER',
]);

const SUBJECT_MODEL_TYPES = new Set(['SUBJECT_3D_ASSET']);
const SCENE_MODEL_TYPES = new Set(['SCENE_3D_ASSET', 'BLENDER_SCENE', 'VIEWER_SCENE']);

export class RuntimeAdapter {
  constructor({ baseUrl = '/api/creator' } = {}) {
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

  listRuns({ collection, limit } = {}) {
    const query = new URLSearchParams();
    if (collection) query.set('collection', collection);
    if (limit) query.set('limit', String(limit));
    const suffix = query.toString() ? `?${query}` : '';
    return this.request(`/projects${suffix}`);
  }

  getRun(runKey) {
    return this.request(`/projects/${encodeURIComponent(runKey)}`);
  }

  getRunBundle(runKey) {
    return this.request(`/projects/${encodeURIComponent(runKey)}/bundle`);
  }

  sendChat(runKey, { text, attachmentIds = [], metadata = {} } = {}) {
    return this.request(`/projects/${encodeURIComponent(runKey)}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        role: 'user',
        text,
        attachment_ids: attachmentIds,
        metadata,
      }),
    });
  }

  uploadReference(runKey, { file, slot } = {}) {
    if (!file) throw new Error('uploadReference requires a file');
    const form = new FormData();
    form.append('file', file, file.name || 'reference.png');
    if (slot?.slot_kind) form.append('binding_role', slot.slot_kind);
    if (slot?.slot_id) form.append('slot_id', slot.slot_id);
    if (slot?.entity_id) form.append('entity_id', slot.entity_id);
    if (slot?.mention) form.append('mention', slot.mention);
    if (slot?.display_label) form.append('display_label', slot.display_label);
    return this.request(`/projects/${encodeURIComponent(runKey)}/upload`, {
      method: 'POST',
      headers: {},
      body: form,
    });
  }

  fileUrl(runKey, relativePath) {
    const query = new URLSearchParams({ path: relativePath });
    return `${this.baseUrl}/projects/${encodeURIComponent(runKey)}/file?${query}`;
  }

  normalizeFileUrl(url) {
    if (!url) return null;
    if (/^https?:\/\//.test(url)) return url;
    if (url.startsWith('/api/')) return url;
    if (this.baseUrl && url.startsWith(`${this.baseUrl}/`)) return url;
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
    referenceSlots: mockReferenceSlots,
    references: mockReferences,
    entities: mockEntities,
    assetVersions: mockAssetVersions,
    approvedConceptSelection: mockApprovedConceptSelection,
    concepts: mockConcepts,
    subjects: mockSubjects,
    sceneAssets: mockSceneAssets,
    finalScene: mockSceneAssets.find((asset) => asset.status === '最终场景') ?? mockSceneAssets[0],
    assetMemory: { allAssets: mockAllAssets, concepts: mockConcepts, references: mockReferences },
    deliveryFiles: mockDeliveryFiles,
    sceneObjects: mockSceneObjects,
    cameraPresets: mockCameraPresets,
    activeObjectId: mockSceneObjects[0]?.id ?? null,
    fileManifest: [],
    runtime: { runs: [], bundle: null, generationStatus: null },
  };
}

export function normalizeRunIndex(rawRuns = []) {
  if (!Array.isArray(rawRuns)) return [];
  return rawRuns.map((run) => ({
    runKey: run.project_key ?? run.run_key,
    displayName: publicRunLabel(run),
    relativePath: run.relative_path ?? run.project_id ?? run.run_id ?? null,
    phase: run.frontend_phase ?? null,
    status: run.frontend_status_value ?? null,
    hasViewerScene: Boolean(run.has_viewer_scene),
    hasSceneState: Boolean(run.has_scene_state),
    modifiedAt: run.modified_at ?? null,
    collectionId: run.collection_id ?? null,
    collectionRank: run.collection_rank ?? null,
  })).filter((run) => run.runKey);
}

export function normalizeRunIndexItemFromBundle(rawBundle) {
  if (!rawBundle?.project_key && !rawBundle?.run_key) return null;
  return {
    runKey: rawBundle.project_key ?? rawBundle.run_key,
    displayName: publicRunLabel(rawBundle),
    relativePath: rawBundle.relative_path ?? rawBundle.project_id ?? rawBundle.run_id ?? null,
    phase: rawBundle.frontend_status?.phase ?? rawBundle.state?.phase ?? null,
    status: rawBundle.frontend_status?.status ?? null,
    hasViewerScene: Boolean(rawBundle.file_manifest?.files?.some((file) => file.label === 'viewer_scene' && file.exists)),
    hasSceneState: Boolean(rawBundle.scene_state),
    modifiedAt: null,
    collectionId: null,
    collectionRank: null,
  };
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
  const referenceSlots = buildReferenceSlots(state, rawBundle, adapter);
  const references = referencesFromSlots(referenceSlots);
  const concepts = imageArtifacts.length > 0
    ? imageArtifacts.map((artifact, index) => conceptFromArtifact(artifact, rawBundle, adapter, assetLibrary, index))
    : mockConcepts;
  const subjects = subjectArtifacts.length > 0
    ? subjectArtifacts.map((artifact, index) => modelAssetFromArtifact(artifact, rawBundle, adapter, index, '主体模型'))
    : [];
  const sceneAssets = buildSceneAssets(sceneArtifacts, rawBundle, adapter, previewImage);
  const entities = buildEntities(sceneSpec, referenceSlots, concepts, subjects, sceneAssets);
  const assetVersions = buildAssetVersions(concepts, subjects, sceneAssets);
  const approvedConceptSelection = buildApprovedConceptSelection(assetVersions);
  const finalScene = buildFinalScene(rawBundle, adapter, previewImage, sceneAssets);
  const sceneObjects = buildSceneObjects(rawBundle.scene_state);
  const cameraPresets = buildCameraPresets(rawBundle.scene_state);
  const activeObjectId = rawBundle.scene_state?.active_object_id ?? sceneObjects.find((object) => object.visible)?.id ?? null;
  const deliveryFiles = buildDeliveryFiles(files);
  const allAssets = [...concepts, ...subjects, ...sceneAssets];

  return {
    source: 'backend',
    error: null,
    runKey: rawBundle.project_key ?? rawBundle.run_key,
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
    referenceSlots,
    references,
    entities,
    assetVersions,
    approvedConceptSelection,
    concepts,
    subjects,
    sceneAssets,
    finalScene,
    assetMemory: { allAssets, concepts, references },
    deliveryFiles,
    sceneObjects,
    cameraPresets,
    activeObjectId,
    fileManifest: files,
    runtime: {
      runs,
      bundle: rawBundle,
      status: frontendStatus.status ?? null,
      progressLabel: frontendStatus.progress_label ?? null,
      missingFiles: rawBundle.missing_files ?? [],
      generationStatus: buildGenerationStatus(frontendStatus, phase),
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
  const selectedConceptIds = approvedConceptIdsFromState(bundle.state);
  const group = conceptGroupForArtifact(artifact);
  const entityId = conceptEntityIdForArtifact(artifact, group);
  const status = libraryItem?.review_status === 'rejected'
    ? '已拒绝'
    : selectedConceptIds.has(artifact.artifact_id) || libraryItem?.selection_status?.includes('selected')
      ? '已选用'
      : '候选';
  return {
    id: artifact.artifact_id,
    asset_id: artifact.artifact_id,
    entity_id: entityId,
    version_label: `v${conceptVersion(artifact, index)}`,
    title: conceptArtifactTitle(artifact, bundle, group, `概念图 ${index + 1}`),
    status,
    kind: artifact.artifact_type?.toLowerCase() ?? 'concept_image',
    group,
    roleLabel: conceptRoleLabel(group),
    image: artifactUrl(bundle, adapter, artifact) || mockConcepts[index % mockConcepts.length]?.image,
    createdAt: artifact.created_at,
    note: artifact.semantic_role || artifact.artifact_type || 'Runtime concept artifact',
  };
}

function modelAssetFromArtifact(artifact, bundle, adapter, index, modelType) {
  return {
    id: artifact.artifact_id,
    asset_id: artifact.artifact_id,
    entity_id: artifact.metadata?.entity_id || (modelType === '场景模型' || modelType === 'Blender 场景' ? 'scene_1' : `subject_${index + 1}`),
    version_id: artifact.metadata?.version_id || `${artifact.metadata?.entity_id || (modelType === '场景模型' ? 'scene_1' : `subject_${index + 1}`)}_model_v${artifact.version ?? 1}`,
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

function buildReferenceSlots(state, bundle, adapter) {
  const referenceImages = normalizeReferenceImages(state, bundle, adapter);
  const slots = mockReferenceSlots.map((slot) => ({ ...slot }));
  if (!Array.isArray(referenceImages) || referenceImages.length === 0) return slots;

  const nextSubjectIndex = { value: 0 };
  const nextSceneIndex = { value: 0 };
  referenceImages.slice(0, 6).forEach((reference, index) => {
    const kind = normalizeReferenceKind(reference.binding_role || reference.role || reference.target_type);
    const slotIndex = kind === 'scene' ? nextSceneIndex.value++ : nextSubjectIndex.value++;
    const slotId = reference.slot_id || (kind === 'scene' ? 'scene_slot_1' : `subject_slot_${slotIndex + 1}`);
    const slot = slots.find((item) => item.slot_id === slotId) || slots[index];
    if (!slot) return;
    slot.slot_kind = kind;
    slot.entity_id = reference.entity_id || slot.entity_id;
    slot.display_label = reference.display_label || slot.display_label || publicEntityLabel(slot.entity_id);
    slot.mention = reference.mention || slot.mention;
    slot.artifact_id = reference.image_id || reference.artifact_id || reference.id || slot.artifact_id;
    slot.image_url = reference.url || reference.uri || reference.image_url || slot.image_url;
    slot.status = slot.image_url ? 'uploaded' : 'empty';
    slot.resolved_name = reference.title || reference.resolved_name || reference.display_name || slot.resolved_name;
  });
  return slots;
}

function normalizeReferenceImages(state, bundle, adapter) {
  const explicitReferences = state.reference_images || state.references || [];
  if (Array.isArray(explicitReferences) && explicitReferences.length > 0) return explicitReferences;
  const inputImages = Array.isArray(state.input_images) ? state.input_images : [];
  if (inputImages.length === 0) return [];
  const artifacts = Array.isArray(state.artifacts) ? state.artifacts : [];
  const artifactsById = new Map(artifacts.map((artifact) => [artifact.artifact_id, artifact]));
  const referenceBinding = referenceBindingFromSceneSpec(state.scene_spec);
  return inputImages.map((image, index) => {
    const artifact = artifactsById.get(image.artifact_id);
    const metadata = artifact?.metadata || {};
    const binding = referenceBinding.get(image.image_id) || referenceBinding.get(image.artifact_id) || {};
    const kind = normalizeReferenceKind(metadata.binding_role || metadata.slot_kind || metadata.target_type || binding.binding_role);
    const url = artifactUrl(bundle, adapter, artifact || image) || image.uri || artifact?.uri;
    return {
      id: image.image_id,
      image_id: image.image_id,
      artifact_id: image.artifact_id,
      uri: url,
      image_url: url,
      binding_role: kind,
      slot_id: metadata.slot_id || binding.slot_id,
      entity_id: metadata.entity_id || binding.entity_id,
      mention: metadata.mention || binding.mention,
      display_label: metadata.display_label || binding.display_label,
      title: metadata.display_label || binding.resolved_name || image.user_declared_label || image.notes || `上传参考 ${index + 1}`,
      resolved_name: binding.resolved_name || metadata.original_filename || image.user_declared_label || `上传参考 ${index + 1}`,
    };
  });
}

function referenceBindingFromSceneSpec(sceneSpec = {}) {
  const binding = new Map();
  const subjects = Array.isArray(sceneSpec.subjects) ? sceneSpec.subjects : [];
  subjects.slice(0, 5).forEach((subject, index) => {
    const entityId = subject.subject_id || `subject_${index + 1}`;
    const imageIds = Array.isArray(subject.reference_image_ids) ? subject.reference_image_ids : [];
    imageIds.forEach((imageId) => {
      if (!imageId) return;
      binding.set(imageId, {
        binding_role: 'subject',
        slot_id: `subject_slot_${index + 1}`,
        entity_id: entityId,
        mention: `@主体${index + 1}`,
        display_label: `主体${index + 1}`,
        resolved_name: subject.display_name || subject.description || `主体${index + 1}`,
      });
    });
  });
  const sceneImageIds = Array.isArray(sceneSpec.environment?.scene_reference_image_ids)
    ? sceneSpec.environment.scene_reference_image_ids
    : [];
  sceneImageIds.forEach((imageId) => {
    if (!imageId) return;
    binding.set(imageId, {
      binding_role: 'scene',
      slot_id: 'scene_slot_1',
      entity_id: 'scene_1',
      mention: '@场景1',
      display_label: '场景1',
      resolved_name: sceneSpec.environment?.description || sceneSpec.title || '场景概念',
    });
  });
  return binding;
}

function referencesFromSlots(referenceSlots) {
  return referenceSlots.filter((slot) => slot.status === 'uploaded').map((slot) => ({
    id: slot.artifact_id || slot.slot_id,
    alias: slot.mention,
    title: slot.resolved_name || slot.display_label,
    role: slot.slot_kind === 'scene' ? '场景参考' : '主体参考',
    image: slot.image_url,
    bindingRole: slot.slot_kind,
    slotId: slot.slot_id,
    entityId: slot.entity_id,
  }));
}

function normalizeReferenceKind(value) {
  return String(value || '').toLowerCase().includes('scene') ? 'scene' : 'subject';
}

function buildEntities(sceneSpec, referenceSlots, concepts, subjects, sceneAssets) {
  const entityMap = new Map();
  entityMap.set('overall', {
    entity_id: 'overall',
    entity_type: 'overall',
    display_label: '整体图',
    resolved_name: sceneSpec.title || '整体概念',
    source_slot_ids: [],
  });
  const sceneSubjects = Array.isArray(sceneSpec.subjects) ? sceneSpec.subjects : [];
  sceneSubjects.forEach((subject, index) => {
    const entityId = subject.subject_id || `subject_${index + 1}`;
    entityMap.set(entityId, {
      entity_id: entityId,
      entity_type: 'subject',
      display_label: `主体${index + 1}`,
      resolved_name: subject.display_name || subject.description || publicEntityLabel(entityId),
      source_slot_ids: [],
    });
  });
  if (sceneSpec.scene_id || sceneSpec.environment?.description || concepts.some((asset) => asset.entity_id === 'scene_1')) {
    entityMap.set('scene_1', {
      entity_id: 'scene_1',
      entity_type: 'scene',
      display_label: '场景1',
      resolved_name: sceneSpec.environment?.description || sceneSpec.title || sceneSpec.scene_id || '场景概念',
      source_slot_ids: [],
    });
  }
  referenceSlots.forEach((slot) => {
    if (slot.status !== 'uploaded') return;
    const current = entityMap.get(slot.entity_id);
    entityMap.set(slot.entity_id, {
      ...current,
      entity_id: slot.entity_id,
      entity_type: slot.slot_kind,
      display_label: current?.display_label || slot.display_label,
      resolved_name: current?.resolved_name || slot.resolved_name,
      source_slot_ids: [...(current?.source_slot_ids || []), slot.slot_id],
    });
  });
  [...concepts, ...subjects, ...sceneAssets].forEach((asset) => {
    if (!asset.entity_id || entityMap.has(asset.entity_id)) return;
    entityMap.set(asset.entity_id, {
      entity_id: asset.entity_id,
      entity_type: asset.entity_id === 'overall' ? 'overall' : asset.entity_id.startsWith('scene') ? 'scene' : 'subject',
      display_label: publicEntityLabel(asset.entity_id),
      resolved_name: asset.title,
      source_slot_ids: [],
    });
  });
  return [...entityMap.values()].filter((entity) => (
    entity.entity_type === 'overall'
    || referenceSlots.some((slot) => slot.entity_id === entity.entity_id && slot.status === 'uploaded')
    || concepts.some((asset) => asset.entity_id === entity.entity_id)
    || subjects.some((asset) => asset.entity_id === entity.entity_id)
    || sceneAssets.some((asset) => asset.entity_id === entity.entity_id)
  ));
}

function buildAssetVersions(concepts, subjects, sceneAssets) {
  return [
    ...concepts.map((asset, index) => ({
      asset_id: asset.asset_id || asset.id,
      entity_id: asset.entity_id || conceptEntityId(asset),
      asset_kind: 'concept_image',
      version_label: asset.version_label || versionFromIndex(index),
      image_url: asset.image,
      status: statusToContract(asset.status),
      source_asset_ids: [],
      created_at: asset.createdAt,
      title: asset.title,
      note: asset.note,
    })),
    ...subjects.map((asset, index) => ({
      asset_id: asset.asset_id || asset.id,
      entity_id: asset.entity_id || `subject_${index + 1}`,
      asset_kind: 'subject_model',
      version_label: asset.version || versionFromIndex(index),
      version_id: asset.version_id || `${asset.entity_id || `subject_${index + 1}`}_model_${asset.version || versionFromIndex(index)}`,
      image_url: asset.image,
      glb_url: asset.url,
      status: statusToContract(asset.status),
      source_asset_ids: [asset.sourceConceptId].filter(Boolean),
      title: asset.title,
      size: asset.size,
    })),
    ...sceneAssets.map((asset, index) => ({
      asset_id: asset.asset_id || asset.id,
      entity_id: asset.entity_id || (asset.status === '最终场景' ? 'final_scene' : 'scene_1'),
      asset_kind: asset.status === '最终场景' ? 'final_scene' : 'scene_model',
      version_label: asset.version || versionFromIndex(index),
      version_id: asset.version_id || `${asset.entity_id || (asset.status === '最终场景' ? 'final_scene' : 'scene_1')}_${asset.version || versionFromIndex(index)}`,
      image_url: asset.image,
      glb_url: asset.url || asset.viewerSceneUrl,
      status: statusToContract(asset.status),
      source_asset_ids: [],
      title: asset.title,
    })),
  ];
}

function buildApprovedConceptSelection(assetVersions) {
  const selectedConcepts = assetVersions.filter((asset) => asset.asset_kind === 'concept_image' && ['selected', 'accepted'].includes(asset.status));
  const fallbackConcepts = assetVersions.filter((asset) => asset.asset_kind === 'concept_image');
  const byEntity = new Map();
  [...selectedConcepts, ...fallbackConcepts].forEach((asset) => {
    if (!byEntity.has(asset.entity_id)) byEntity.set(asset.entity_id, asset.asset_id);
  });
  const subject_concept_asset_ids = {};
  const scene_concept_asset_ids = {};
  for (const [entityId, assetId] of byEntity.entries()) {
    if (entityId?.startsWith('subject_')) subject_concept_asset_ids[entityId] = assetId;
    if (entityId?.startsWith('scene_')) scene_concept_asset_ids[entityId] = assetId;
  }
  return {
    overall_concept_asset_id: byEntity.get('overall') || fallbackConcepts[0]?.asset_id || null,
    subject_concept_asset_ids,
    scene_concept_asset_ids,
  };
}

function buildSceneAssets(sceneArtifacts, bundle, adapter, previewImage) {
  const runtimeAssets = sceneArtifacts.map((artifact, index) => ({
    ...modelAssetFromArtifact(artifact, bundle, adapter, index, artifact.artifact_type === 'BLENDER_SCENE' ? 'Blender 场景' : '场景模型'),
    fileFormat: fileFormatFromArtifact(artifact),
  }));
  if (runtimeAssets.length === 0 && !previewImage) return [];
  if (previewImage) {
    runtimeAssets.push({
      id: 'runtime_final_preview',
      asset_id: 'runtime_final_preview',
      entity_id: 'final_scene',
      version_id: 'final_scene_runtime',
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
  if (!Array.isArray(objects) || objects.length === 0) return [];
  return objects.slice(0, 24).map((object, index) => ({
    id: object.viewer_object_id || object.object_id || object.id || object.blender_object_id || `object_${index + 1}`,
    label: object.display_name || object.label || object.name || object.viewer_object_id || `场景对象 ${index + 1}`,
    type: object.object_type || object.type || object.semantic_role || 'object',
    visible: object.visible !== false,
    selectable: object.selectable !== false,
    highlighted: Boolean(object.highlighted),
    bounds: normalizeBounds(object.bounds),
    transform: object.transform ?? null,
    subjectId: object.subject_id ?? null,
    assetId: object.asset_id ?? null,
    blenderObjectId: object.blender_object_id ?? null,
  }));
}

function buildCameraPresets(sceneState) {
  const presets = sceneState?.camera_presets;
  if (!Array.isArray(presets) || presets.length === 0) {
    const camera = sceneState?.camera;
    if (camera?.transform?.location) {
      return [
        {
          id: 'scene_camera',
          label: camera.name || 'Scene Camera',
          orbit: null,
          target: null,
          source: 'scene_state.camera',
        },
        ...mockCameraPresets.slice(0, 5),
      ];
    }
    return mockCameraPresets;
  }
  return presets.slice(0, 12).map((preset, index) => ({
    id: preset.id || `camera_${index + 1}`,
    label: preset.label || preset.name || `镜头 ${index + 1}`,
    orbit: preset.orbit || preset.camera_orbit || preset.cameraOrbit || null,
    target: preset.target || preset.camera_target || preset.cameraTarget || null,
    exposure: preset.exposure ?? null,
  }));
}

function conceptGroupForArtifact(artifact) {
  const haystack = `${artifact.artifact_type || ''} ${artifact.semantic_role || ''} ${artifact.artifact_id || ''}`.toLowerCase();
  if (haystack.includes('subject')) return 'subject';
  if (haystack.includes('scene')) return 'scene';
  if (haystack.includes('target') || haystack.includes('final_preview')) return 'overall';
  return 'overall';
}

function conceptEntityIdForArtifact(artifact, group) {
  if (group === 'overall') return 'overall';
  if (group === 'scene') return 'scene_1';
  return artifact.metadata?.entity_id
    || artifact.linked_subject_id
    || artifact.metadata?.subject_id
    || subjectIdFromRequirement(artifact.metadata?.requirement_id)
    || artifact.metadata?.target_id
    || 'subject_1';
}

function subjectIdFromRequirement(requirementId) {
  const match = String(requirementId || '').match(/^subject_concept:(.+)$/);
  return match?.[1] || null;
}

function conceptVersion(artifact, index) {
  const version = artifact.metadata?.concept_version ?? artifact.version ?? index + 1;
  const parsed = Number(version);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : version;
}

function approvedConceptIdsFromState(state = {}) {
  const conceptBundle = state.concept_bundle || {};
  const ids = new Set();
  if (conceptBundle.final_preview_image_id) ids.add(conceptBundle.final_preview_image_id);
  const sceneIds = Array.isArray(conceptBundle.scene_concept_image_ids) ? conceptBundle.scene_concept_image_ids : [];
  sceneIds.forEach((id) => id && ids.add(id));
  const subjectMap = conceptBundle.subject_concept_images || {};
  Object.values(subjectMap).forEach((value) => {
    if (Array.isArray(value)) value.forEach((id) => id && ids.add(id));
    else if (value) ids.add(value);
  });
  return ids;
}

function conceptArtifactTitle(artifact, bundle, group, fallback) {
  if (group === 'overall') return bundle.state?.scene_spec?.title || '整体预览';
  if (group === 'scene') return bundle.state?.scene_spec?.environment?.description || bundle.state?.scene_spec?.title || '场景概念';
  const subjectId = conceptEntityIdForArtifact(artifact, group);
  const subject = (bundle.state?.scene_spec?.subjects || []).find((item) => item.subject_id === subjectId);
  if (subject?.display_name) return subject.display_name;
  const requirementId = artifact.metadata?.requirement_id;
  const requirements = bundle.state?.concept_bundle?.prompt_pack?.image_requirements;
  const requirement = Array.isArray(requirements)
    ? requirements.find((item) => item.requirement_id === requirementId)
    : null;
  if (requirement?.user_review_label) {
    return requirement.user_review_label
      .replace(/\s+subject concept$/i, '')
      .replace(/\s+scene concept$/i, '')
      .replace(/\s+target render$/i, '');
  }
  return readableArtifactTitle(artifact, fallback);
}

function conceptRoleLabel(group) {
  const labels = { overall: '整体图', subject: '主体图', scene: '场景图' };
  return labels[group] || '概念图';
}

function conceptEntityId(asset) {
  if (asset.entity_id) return asset.entity_id;
  if (asset.group === 'overall' || asset.kind?.includes('overall')) return 'overall';
  if (asset.group === 'scene' || asset.kind?.includes('scene')) return 'scene_1';
  return 'subject_1';
}

function publicEntityLabel(entityId = '') {
  if (entityId === 'overall') return '整体图';
  const subject = entityId.match(/^subject_(\d+)/);
  if (subject) return `主体${subject[1]}`;
  const scene = entityId.match(/^scene_(\d+)/);
  if (scene) return `场景${scene[1]}`;
  if (entityId.startsWith('subject_')) return '主体';
  if (entityId.startsWith('scene_')) return '场景';
  return entityId || '实体';
}

function versionFromIndex(index) {
  return `v${Math.max(1, index + 1)}`;
}

function statusToContract(status) {
  if (['selected', 'accepted', 'rejected', 'archived', 'generating', 'failed'].includes(status)) return status;
  if (status === '已拒绝') return 'rejected';
  if (status === '已选用' || status === '当前查看' || status === '最终场景') return 'selected';
  if (status === '已验收') return 'accepted';
  return 'candidate';
}

function normalizeBounds(bounds) {
  const min = bounds?.min;
  const max = bounds?.max;
  if (!Array.isArray(min) || !Array.isArray(max) || min.length !== 3 || max.length !== 3) return null;
  const nextMin = min.map(Number);
  const nextMax = max.map(Number);
  if ([...nextMin, ...nextMax].some((value) => !Number.isFinite(value))) return null;
  return { min: nextMin, max: nextMax };
}

function buildGenerationStatus(frontendStatus, phase) {
  const generatingPhases = new Set([
    'CONCEPT_GENERATION',
    'SUBJECT_ASSET_GENERATION',
    'SCENE_ASSET_GENERATION',
    'BLENDER_ASSEMBLY_EXECUTION',
  ]);
  if (!generatingPhases.has(phase)) return null;
  return {
    phase,
    label: PHASE_LABELS[phase] ?? '生成中',
    progressLabel: frontendStatus?.progress_label ?? null,
    status: frontendStatus?.status ?? null,
  };
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
  const caseLabel = round04dCaseLabel(run.relative_path || run.run_id);
  if (caseLabel) return caseLabel;
  return run.display_name || run.run_id || run.relative_path || 'Runtime Run';
}

function round04dCaseLabel(relativePath = '') {
  const match = String(relativePath).match(/^round04d_live_12_samples\/case_(\d+)_(.+)$/);
  if (!match) return null;
  return `Case ${match[1]} · ${titleCaseSlug(match[2])}`;
}

function titleCaseSlug(slug = '') {
  return slug
    .split('_')
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
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
