# v0.5.2 Reference / Entity / Version 数据契约

## 1. Reference slots

```ts
type ReferenceSlotKind = 'subject' | 'scene';

type ReferenceSlot = {
  slot_id: 'subject_slot_1' | 'subject_slot_2' | 'subject_slot_3' | 'subject_slot_4' | 'subject_slot_5' | 'scene_slot_1';
  slot_kind: ReferenceSlotKind;
  display_label: '主体 1' | '主体 2' | '主体 3' | '主体 4' | '主体 5' | '场景 1';
  entity_id: 'subject_1' | 'subject_2' | 'subject_3' | 'subject_4' | 'subject_5' | 'scene_1';
  artifact_id?: string;
  image_url?: string;
  status: 'empty' | 'uploaded' | 'replacing' | 'removed';
};
```

## 2. Entities

```ts
type CreativeEntityType = 'subject' | 'scene' | 'overall';

type CreativeEntity = {
  entity_id: string;              // subject_1 / scene_1 / overall
  entity_type: CreativeEntityType;
  display_label: string;          // 主体 1 / 场景 1 / 整体图
  resolved_name?: string;         // 机械灵兽·霜牙 / 古老遗迹
  source_slot_ids: string[];
  user_description?: string;
};
```

## 3. Asset versions

```ts
type AssetVersion = {
  asset_id: string;
  entity_id: string;              // subject_1 / scene_1 / overall
  asset_kind: 'concept_image' | 'subject_model' | 'scene_model' | 'final_scene';
  version_label: 'v1' | 'v2' | 'v3';
  image_url?: string;
  glb_url?: string;
  blend_url?: string;
  scene_state_url?: string;
  status: 'candidate' | 'selected' | 'accepted' | 'rejected' | 'archived' | 'generating' | 'failed';
  source_asset_ids: string[];
  created_at?: string;
};
```

## 4. Approved concept selection

```ts
type ApprovedConceptSelection = {
  overall_concept_asset_id: string;
  subject_concept_asset_ids: Record<string, string>; // entity_id -> asset_id
  scene_concept_asset_ids: Record<string, string>;   // entity_id -> asset_id
};
```

## 5. Model review selection

```ts
type ModelReviewSelection = {
  selected_entity_id: string;
  selected_model_asset_id: string;
};
```

## 6. Composition request

```ts
type CompositionRequest = {
  selected_subject_models: Record<string, string>; // subject_entity_id -> model_asset_id
  selected_scene_model: string;
  placement_hints: Record<string, {
    position_hint?: string;
    position?: [number, number, number];
    rotation_y_degrees?: number;
    scale?: number;
  }>;
  camera_intent?: string;
  user_feedback_text?: string;
};
```

## 7. Feedback target

```ts
type FeedbackTarget = {
  target_type: 'overall' | 'subject' | 'scene' | 'subject_model' | 'scene_model' | 'final_scene';
  entity_id?: string;
  asset_id?: string;
  feedback_text: string;
  new_reference_artifact_ids: string[];
};
```
