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
