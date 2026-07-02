/**
 * Frontend-side domain vocabulary. These constants intentionally mirror the
 * runtime docs while keeping UI wording product-facing.
 */
export const WorkflowPhase = {
  INTAKE: 'INTAKE',
  SCENE_SPEC_DRAFT: 'SCENE_SPEC_DRAFT',
  SCENE_SPEC_READY: 'SCENE_SPEC_READY',
  CONCEPT_GENERATION: 'CONCEPT_GENERATION',
  CONCEPT_REVIEW: 'CONCEPT_REVIEW',
  CONCEPT_APPROVED: 'CONCEPT_APPROVED',
  SUBJECT_ASSET_GENERATION: 'SUBJECT_ASSET_GENERATION',
  SUBJECT_ASSET_QA: 'SUBJECT_ASSET_QA',
  SCENE_ASSET_GENERATION: 'SCENE_ASSET_GENERATION',
  SCENE_ASSET_ADAPTATION: 'SCENE_ASSET_ADAPTATION',
  BLENDER_ASSEMBLY_PLANNING: 'BLENDER_ASSEMBLY_PLANNING',
  BLENDER_ASSEMBLY_EXECUTION: 'BLENDER_ASSEMBLY_EXECUTION',
  BLENDER_PREVIEW: 'BLENDER_PREVIEW',
  BLENDER_EDIT: 'BLENDER_EDIT',
  DELIVERY: 'DELIVERY',
};

export const UserActionType = {
  APPROVE_CONCEPT: 'approve_concept',
  REQUEST_CONCEPT_CHANGES: 'request_concept_changes',
  APPROVE_BLENDER_PREVIEW: 'approve_blender_preview',
  REQUEST_BLENDER_CHANGES: 'request_blender_changes',
};

export const ReferenceBindingRole = {
  SUBJECT: 'subject',
  SCENE: 'scene',
  STYLE: 'style',
  LIGHTING: 'lighting',
  MATERIAL: 'material',
  OTHER: 'other',
};

export const MentionKind = {
  OVERALL_CONCEPT: 'overall_concept',
  SUBJECT_ENTITY: 'subject_entity',
  SUBJECT_CONCEPT_VERSION: 'subject_concept_version',
  SUBJECT_MODEL_VERSION: 'subject_model_version',
  SCENE_ENTITY: 'scene_entity',
  SCENE_CONCEPT_VERSION: 'scene_concept_version',
  SCENE_MODEL_VERSION: 'scene_model_version',
  REFERENCE_IMAGE: 'reference_image',
  FINAL_SCENE_OBJECT: 'final_scene_object',
  CAMERA_PRESET: 'camera_preset',
};

export function buildReferenceMentionPayload({ text, mentions, uploads }) {
  return {
    text,
    references: mentions.map((mention) => ({
      alias: mention.alias,
      image_id: mention.imageId,
      artifact_id: mention.artifactId,
      binding_role: mention.bindingRole,
    })),
    uploads,
  };
}

export function buildAssemblySelectionPayload({ subjects, scene, cameraIntent, feedbackText }) {
  return {
    selected_subject_assets: subjects,
    selected_scene_asset: scene,
    camera_intent: cameraIntent,
    feedback_text: feedbackText,
  };
}

export function buildFeedbackMentionOptions({
  mode = 'concept',
  entities = [],
  assetVersions = [],
  referenceSlots = [],
  selection = null,
  selectedModel = null,
  selectedEntity = null,
} = {}) {
  const options = [];
  const conceptVersions = assetVersions.filter((asset) => asset.asset_kind === 'concept_image');
  const modelVersions = assetVersions.filter((asset) => ['subject_model', 'scene_model'].includes(asset.asset_kind));

  if (mode === 'concept') {
    const overallVersionId = selection?.overall_concept_asset_id
      || conceptVersions.find((asset) => asset.entity_id === 'overall')?.asset_id;
    options.push({
      token: '@整体图',
      kind: MentionKind.OVERALL_CONCEPT,
      versionId: overallVersionId,
      displayLabel: '整体图',
    });
  }

  entities
    .filter((entity) => ['subject', 'scene'].includes(entity.entity_type))
    .forEach((entity) => {
      const number = entity.entity_id?.split('_')[1] || '1';
      const token = entity.entity_type === 'scene' ? `@场景${number}` : `@主体${number}`;
      options.push({
        token,
        kind: entity.entity_type === 'scene' ? MentionKind.SCENE_ENTITY : MentionKind.SUBJECT_ENTITY,
        entityId: entity.entity_id,
        displayLabel: `${token} · ${entity.resolved_name || entity.display_label}`,
      });
    });

  if (mode === 'model') {
    const source = selectedModel ? [selectedModel, ...modelVersions.filter((asset) => asset.asset_id !== selectedModel.asset_id)] : modelVersions;
    source.forEach((asset) => {
      const entity = entities.find((item) => item.entity_id === asset.entity_id) || selectedEntity;
      if (!entity) return;
      const number = entity.entity_id?.split('_')[1] || '1';
      const prefix = entity.entity_type === 'scene' ? `@场景${number}模型` : `@主体${number}模型`;
      const token = `${prefix}${asset.version_label || ''}`.replace(/\s+/g, '');
      options.push({
        token,
        kind: entity.entity_type === 'scene' ? MentionKind.SCENE_MODEL_VERSION : MentionKind.SUBJECT_MODEL_VERSION,
        entityId: asset.entity_id,
        versionId: asset.version_id || asset.asset_id,
        artifactId: asset.asset_id,
        displayLabel: `${entity.display_label} · 模型 ${asset.version_label || asset.asset_id}`,
      });
    });
  }

  referenceSlots
    .filter((slot) => slot.status === 'uploaded')
    .forEach((slot, index) => {
      options.push({
        token: `@参考图${index + 1}`,
        kind: MentionKind.REFERENCE_IMAGE,
        entityId: slot.entity_id,
        artifactId: slot.artifact_id,
        referenceId: slot.artifact_id || slot.slot_id,
        displayLabel: `${slot.display_label} · ${slot.resolved_name || '参考图'}`,
      });
    });

  return dedupeMentionOptions(options);
}

export function extractFeedbackMentions(feedbackText, options = []) {
  return options
    .filter((option) => feedbackText.includes(option.token))
    .map((option) => ({
      token: option.token,
      kind: option.kind,
      entityId: option.entityId,
      versionId: option.versionId,
      artifactId: option.artifactId,
      referenceId: option.referenceId,
      displayLabel: option.displayLabel,
    }));
}

export function buildConceptFeedbackPayload({
  feedbackText,
  mentionOptions,
  selectedConceptCombination,
  newReferenceUploadIds = [],
}) {
  return {
    action_type: UserActionType.REQUEST_CONCEPT_CHANGES,
    feedback_text: feedbackText,
    mentions: extractFeedbackMentions(feedbackText, mentionOptions),
    selected_concept_combination: selectedConceptCombination,
    new_reference_upload_ids: newReferenceUploadIds,
  };
}

export function buildModelFeedbackPayload({
  feedbackText,
  mentionOptions,
  selectedModelCombination,
  newReferenceUploadIds = [],
}) {
  return {
    action_type: 'request_model_changes',
    feedback_text: feedbackText,
    mentions: extractFeedbackMentions(feedbackText, mentionOptions),
    selected_model_combination: selectedModelCombination,
    new_reference_upload_ids: newReferenceUploadIds,
  };
}

function dedupeMentionOptions(options) {
  const seen = new Set();
  return options.filter((option) => {
    if (!option.token || seen.has(option.token)) return false;
    seen.add(option.token);
    return true;
  });
}
