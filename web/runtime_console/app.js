const UI_VERSION = '20260630-ui26';
const DEV_MODE = new URLSearchParams(window.location.search).get('dev') === '1';
const PUBLIC_RUN_LIMIT = 6;

if (DEV_MODE) {
  document.documentElement.classList.add('dev-mode');
  document.querySelectorAll('.dev-only[hidden]').forEach((node) => {
    node.removeAttribute('hidden');
  });
}

const state = {
  runs: [],
  currentRunKey: null,
  bundle: null,
  uploads: [],
  viewerLoadingTimer: null,
  runRefreshPollTimer: null,
  runRefreshPollCount: 0,
  selectedSceneObjectKey: '',
};

try {
  const storedVersion = window.localStorage?.getItem('image23d.runtimeConsole.uiVersion');
  if (storedVersion !== UI_VERSION) {
    window.localStorage?.removeItem('image23d.runtimeConsole.currentRunKey');
    window.localStorage?.setItem('image23d.runtimeConsole.uiVersion', UI_VERSION);
  }
} catch {
  // Local storage is only a convenience; the console still works without it.
}

const els = {
  runSubtitle: document.getElementById('runSubtitle'),
  runList: document.getElementById('runList'),
  chatLog: document.getElementById('chatLog'),
  composerNotice: document.getElementById('composerNotice'),
  chatForm: document.getElementById('chatForm'),
  chatInput: document.getElementById('chatInput'),
  uploadForm: document.getElementById('uploadForm'),
  uploadInput: document.getElementById('uploadInput'),
  uploadFileHint: document.getElementById('uploadFileHint'),
  newRunButton: document.getElementById('newRunButton'),
  refreshRunsButton: document.getElementById('refreshRunsButton'),
  viewerFrame: document.getElementById('viewerFrame'),
  conceptPreviewImage: document.getElementById('conceptPreviewImage'),
  viewerEmpty: document.getElementById('viewerEmpty'),
  viewerTitle: document.getElementById('viewerTitle'),
  viewerMeta: document.getElementById('viewerMeta'),
  viewerOpenLink: document.getElementById('viewerOpenLink'),
  blendOpenLink: document.getElementById('blendOpenLink'),
  workflowRibbon: document.getElementById('workflowRibbon'),
  stageRoadmap: document.getElementById('stageRoadmap'),
  centerPhaseValue: document.getElementById('centerPhaseValue'),
  centerNextValue: document.getElementById('centerNextValue'),
  centerPreviewValue: document.getElementById('centerPreviewValue'),
  centerAssetValue: document.getElementById('centerAssetValue'),
  taskBrief: document.getElementById('taskBrief'),
  runStatusStrip: document.getElementById('runStatusStrip'),
  stageTimeline: document.getElementById('stageTimeline'),
  nextActionBanner: document.getElementById('nextActionBanner'),
  statusHero: document.getElementById('statusHero'),
  statusList: document.getElementById('statusList'),
  planButton: document.getElementById('planButton'),
  stepButton: document.getElementById('stepButton'),
  applyButton: document.getElementById('applyButton'),
  loopButton: document.getElementById('loopButton'),
  handoffButton: document.getElementById('handoffButton'),
  workerButton: document.getElementById('workerButton'),
  userGateActions: document.getElementById('userGateActions'),
  uploadChips: document.getElementById('uploadChips'),
  assetGallery: document.getElementById('assetGallery'),
  assetList: document.getElementById('assetList'),
  sceneObjectList: document.getElementById('sceneObjectList'),
  jobList: document.getElementById('jobList'),
  objectList: document.getElementById('objectList'),
  objectCount: document.getElementById('objectCount'),
  deliveryList: document.getElementById('deliveryList'),
  fileList: document.getElementById('fileList'),
  fileCount: document.getElementById('fileCount'),
};

const STAGES = [
  { label: '需求', detail: '自然语言和参考图绑定', phases: ['INTAKE', 'SCENE_SPEC_DRAFT', 'SCENE_SPEC_READY'] },
  { label: '概念', detail: '生成图像方向并确认', phases: ['CONCEPT_GENERATION', 'CONCEPT_REVIEW', 'CONCEPT_APPROVED'] },
  { label: '模型', detail: '主体和环境资产生成', phases: ['SUBJECT_ASSET_GENERATION', 'SUBJECT_ASSET_QA', 'SCENE_ASSET_GENERATION', 'SCENE_ASSET_ADAPTATION'] },
  { label: '场景', detail: 'Blender 装配和 3D 验收', phases: ['BLENDER_ASSEMBLY_PLANNING', 'BLENDER_ASSEMBLY_EXECUTION', 'BLENDER_PREVIEW', 'BLENDER_EDIT'] },
  { label: '交付', detail: '工程、模型和交付包', phases: ['DELIVERY'] },
];

const PHASE_LABELS = {
  INTAKE: '需求收集',
  SCENE_SPEC_DRAFT: '场景理解草稿',
  SCENE_SPEC_READY: '场景规格已就绪',
  CONCEPT_GENERATION: '概念图生成',
  CONCEPT_REVIEW: '等待概念确认',
  CONCEPT_APPROVED: '概念已确认',
  SUBJECT_ASSET_GENERATION: '主体模型生成',
  SUBJECT_ASSET_QA: '主体质量检查',
  SCENE_ASSET_GENERATION: '场景资产生成',
  SCENE_ASSET_ADAPTATION: '场景资产适配',
  BLENDER_ASSEMBLY_PLANNING: '场景装配规划',
  BLENDER_ASSEMBLY_EXECUTION: '场景装配执行',
  BLENDER_PREVIEW: '3D 预览验收',
  BLENDER_EDIT: '场景编辑',
  DELIVERY: '交付',
  FAILED: '失败',
};

const STATUS_LABELS = {
  completed: '已完成',
  attention_required: '需要处理',
  needs_user_action: '等待用户',
  ready: '就绪',
  planned: '已规划',
  waiting_user: '等待用户',
  delegated: '已交给子任务',
  dry_run: '试跑',
  blocked: '阻塞',
  failed: '失败',
  applied: '已应用',
  skipped: '已跳过',
};

const STAGE_LABELS = {
  runtime_post_planned: '运行计划生成',
  runtime_state_apply: '状态应用',
  runtime_handoff_apply: '子任务结果回灌',
  runtime_status: '运行状态检查',
  concept_approval: '概念确认',
  compose: '场景装配',
  export_viewer: '生成 3D 预览',
  viewer_check: '预览检查',
  submit: '提交生成',
  check_status: '查询生成状态',
  save_completed: '保存生成结果',
  quality_check: '质量检查',
  repair_decision: '修复决策',
  repair_execute: '执行修复',
  prepare_generation: '准备生成',
  upload_inputs: '上传输入',
  poll_upload: '等待上传完成',
  submit_generation: '提交场景生成',
  poll_generation: '等待场景生成',
  inspect_output: '检查输出',
  save_generation: '保存场景资产',
  register_existing_output: '登记现有输出',
  delivery_package: '交付打包',
  review_patch: '整理用户反馈',
  seed_concept: '登记概念图',
  apply_review_patch: '应用反馈补丁',
  status: '状态检查',
  plan_handoff: '规划子任务',
  execute_handoff: '执行子任务',
  blender_edit: '场景编辑',
};

const NODE_LABELS = {
  ReferenceBindingValidator: '参考图用途检查',
  SceneInterpreter: '场景理解',
  SceneSpecCompiler: '场景规格整理',
  ConceptPromptPlanner: '概念图提示词规划',
  ConceptVisualQA: '概念图检查',
  FeedbackPatchParser: '反馈解析',
  RegenerationRouter: '重生成路由',
  SceneAssetAdapterPlanner: '场景资产适配规划',
  BlenderAssemblyPlanner: '场景装配规划',
  BlenderCommandExecutor: '场景工程执行',
  SceneStateSynchronizer: '场景状态同步',
  BlenderPreviewReviewGate: '预览确认',
  BlenderEditRouter: '场景编辑路由',
  ConceptReviewGate: '概念确认',
  generate_concept_images: '生成概念图',
  regenerate_concept_images: '重生成概念图',
  build_subject_asset: '生成主体模型',
  check_subject_asset_quality: '检查主体质量',
  build_scene_asset: '生成场景资产',
  adapt_scene_asset: '适配场景资产',
  export_viewer_scene: '生成 3D 预览',
  render_preview: '渲染预览图',
  blender_assembly_result: '场景装配结果回灌',
};

const FILE_LABELS = {
  state: '状态',
  summary: '摘要',
  frontend_status: '前端状态',
  delivery_handoff: '交付说明',
  scene_state: '场景状态',
  viewer_scene: '3D 预览模型',
  blend_file: '工程文件',
  preview_image: '预览图',
  runtime_plan: '运行计划',
  runtime_execution: '执行日志',
  runtime_execution_summary: '执行摘要',
  runtime_apply: '状态应用日志',
  runtime_apply_summary: '状态应用摘要',
  runtime_loop: '循环日志',
  runtime_loop_summary: '循环摘要',
  runtime_handoff: '子任务交接日志',
  runtime_handoff_summary: '子任务交接摘要',
  runtime_worker: '子任务执行日志',
  runtime_worker_summary: '子任务执行摘要',
  runtime_user_action: '用户确认日志',
  runtime_user_action_summary: '用户确认摘要',
  runtime_handoff_apply: '结果回灌日志',
  runtime_handoff_apply_summary: '结果回灌摘要',
  chat: '聊天记录',
  uploads: '上传记录',
};

async function api(path, options = {}) {
  const res = await fetch(path, options);
  const text = await res.text();
  let payload = {};
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = { error: text };
    }
  }
  if (!res.ok) {
    throw new Error(friendlyError(payload.error || `Request failed: ${res.status}`));
  }
  return payload;
}

async function refreshRuns(selectLatest = false) {
  state.runs = await api('/api/runs');
  renderRuns();
  if (!state.currentRunKey && state.runs.length) {
    await selectRun(defaultRunKey());
  } else if (selectLatest && state.runs.length) {
    await selectRun(defaultRunKey());
  }
}

function defaultRunKey() {
  const saved = window.localStorage?.getItem('image23d.runtimeConsole.currentRunKey');
  const candidates = DEV_MODE ? state.runs : state.runs.filter(publicRunVisible);
  const sorted = (candidates.length ? candidates : state.runs)
    .slice()
    .sort((a, b) => runSelectionScore(b) - runSelectionScore(a));
  const best = sorted[0];
  const savedRun = saved ? state.runs.find((run) => routeKey(run) === saved) : null;
  if (savedRun) {
    const bestScore = runSelectionScore(best);
    const savedScore = runSelectionScore(savedRun);
    const savedIsUseful = DEV_MODE || publicRunVisible(savedRun);
    const savedHasPreview = Boolean(savedRun.has_viewer_scene || savedRun.has_scene_state);
    const bestHasPreview = Boolean(best?.has_viewer_scene || best?.has_scene_state);
    if (!DEV_MODE && (!savedIsUseful || (bestHasPreview && !savedHasPreview) || savedScore < bestScore - 4)) {
      return routeKey(best);
    }
    if (savedIsUseful && (savedHasPreview || !bestHasPreview || savedScore >= bestScore - 18)) {
      return saved;
    }
  }
  return routeKey(best || state.runs[0]);
}

function runSelectionScore(run) {
  const name = String(run?.display_name || run?.run_id || '');
  const inspectablePreview = hasInspectablePreview(run);
  const frontendPhase = String(run?.frontend_phase || '');
  let score = Number(run?.modified_at || 0) / 10000000;
  if (run?.has_viewer_scene) score += 180;
  if (run?.has_scene_state) score += 90;
  if (run?.has_frontend_status) score += 32;
  if (run?.has_state) score += 24;
  if (run?.has_summary) score += 12;
  if (run?.has_delivery_handoff) score += 28;
  if (isPublicShowcaseRunName(name)) score += 45;
  if (/scene_spec_assembly_non_dryrun/i.test(name)) score += 25;
  if (isUserConsoleRunName(name)) score += 70;
  if (frontendPhase === 'BLENDER_PREVIEW') score += 260;
  if (frontendPhase === 'DELIVERY') score += 80;
  if (inspectablePreview && /edit|router|live/i.test(name)) score += 120;
  if (isInternalRunName(name) && !inspectablePreview) score -= 160;
  if (/live|real|用户|真实/i.test(name)) score += 25;
  if (!run?.has_viewer_scene && run?.has_frontend_status) score += 8;
  if (isDryRunRunName(name)) score -= 100;
  if (/deepseek|qwen|socket|scratch|refresh|router/i.test(name) && !inspectablePreview) score -= 80;
  if (run?.is_stage) score -= 45;
  return score;
}

function routeKey(run) {
  return run?.run_key || run?.run_id;
}

async function selectRun(runKey) {
  state.currentRunKey = runKey;
  state.selectedSceneObjectKey = '';
  window.localStorage?.setItem('image23d.runtimeConsole.currentRunKey', runKey);
  state.bundle = await api(`/api/runs/${encodeURIComponent(runKey)}`);
  state.uploads = await api(`/api/runs/${encodeURIComponent(runKey)}/uploads`);
  renderRuns();
  renderBundle();
  await refreshChat();
}

function renderRuns() {
  els.runList.innerHTML = '';
  const visibleRuns = (DEV_MODE ? state.runs : state.runs.filter(publicRunVisible))
    .slice()
    .sort((a, b) => runSelectionScore(b) - runSelectionScore(a))
    .slice(0, DEV_MODE ? 80 : PUBLIC_RUN_LIMIT);
  if (!visibleRuns.length) {
    els.runList.innerHTML = `
      <div class="run-item placeholder">
        <span class="item-title">还没有创作记录</span>
        <span class="item-meta">点击“新建”，或继续等待运行目录写入。</span>
      </div>
    `;
    return;
  }
  visibleRuns.forEach((run, index) => {
    const key = routeKey(run);
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `run-item${key === state.currentRunKey ? ' active' : ''}`;
    const badges = runBadges(run);
    button.innerHTML = `
      <span class="item-title">${escapeHtml(runDisplayTitle(run, index))}</span>
      <span class="item-meta">${escapeHtml(badges.join(' · ') || '等待输入')}</span>
    `;
    button.addEventListener('click', () => selectRun(key));
    els.runList.appendChild(button);
  });
}

function publicRunVisible(run) {
  if (!run) return false;
  if (run.is_stage) return false;
  const name = String(run.display_name || run.run_id || '');
  if (isDryRunRunName(name)) return false;
  if (isPublicShowcaseRunName(name)) {
    return Boolean(run.has_state || run.has_summary || run.has_frontend_status || run.has_viewer_scene || run.has_scene_state);
  }
  if (isUserConsoleRunName(name)) return Boolean(run.has_state || run.has_summary || run.has_frontend_status);
  if (/p0_real|real_demo|codex_self_robot/i.test(name)) return Boolean(run.has_state || run.has_summary || run.has_frontend_status);
  if (hasInspectablePreview(run)) return true;
  if (isInternalRunName(name)) return false;
  if (run.has_viewer_scene || run.has_scene_state) return true;
  return false;
}

function hasInspectablePreview(run) {
  return Boolean(run?.has_viewer_scene || run?.has_scene_state);
}

function renderBundle() {
  const bundle = state.bundle;
  if (!bundle) return;
  const status = bundle.frontend_status || {};
  const handoff = bundle.delivery_handoff || {};
  const scene = bundle.scene_state || {};
  const web = bundle.web_surface || {};
  const manifest = bundle.file_manifest || {};
  const viewerUrl = web.viewer_scene_url || handoff.viewer_url || null;
  const viewerEmbedUrlValue = viewerEmbedUrl(viewerUrl);
  const conceptPreview = conceptPreviewInfo(bundle);
  const previewImage = blenderPreviewImageInfo(bundle);
  const blendReady = hasBlendArtifact(bundle, manifest);
  const blendUrl = blendReady ? (web.blender_web_http_url || handoff.blender_web_http_url || null) : null;

  setDocumentRunState(bundle, { status, manifest, viewerUrl, conceptPreview, previewImage });
  els.runSubtitle.textContent = runDisplayTitle(bundle, 0);
  els.viewerTitle.textContent = viewerTitle(bundle, scene, status, conceptPreview, previewImage);
  els.viewerMeta.textContent = status.phase ? `${phaseLabel(status.phase)} · ${statusLabel(status.status || 'ready')}` : '';

  if (viewerUrl) {
    if (!sameBrowserUrl(els.viewerFrame.src, viewerEmbedUrlValue)) {
      els.viewerFrame.src = viewerEmbedUrlValue;
    }
    els.viewerFrame.style.display = 'block';
    els.conceptPreviewImage.removeAttribute('src');
    els.conceptPreviewImage.style.display = 'none';
    els.viewerEmpty.classList.add('loading');
    els.viewerEmpty.classList.toggle('preview-fallback', Boolean(previewImage?.url));
    els.viewerEmpty.dataset.keepPreview = previewImage?.url ? '1' : '0';
    els.viewerEmpty.style.display = 'grid';
    els.viewerEmpty.innerHTML = viewerLoadingMarkup(previewImage);
    els.viewerOpenLink.href = viewerUrl;
    els.viewerOpenLink.textContent = '打开预览';
    els.viewerOpenLink.classList.remove('disabled');
    els.viewerOpenLink.hidden = false;
    scheduleViewerLoadingFallback(viewerEmbedUrlValue, previewImage);
  } else if (previewImage?.url) {
    clearViewerLoadingFallback();
    els.viewerEmpty.dataset.keepPreview = '0';
    els.viewerEmpty.classList.remove('preview-fallback');
    els.viewerFrame.removeAttribute('src');
    els.viewerFrame.style.display = 'none';
    els.conceptPreviewImage.src = previewImage.url;
    els.conceptPreviewImage.alt = previewImage.label || '场景预览图';
    els.conceptPreviewImage.style.display = 'block';
    els.viewerEmpty.style.display = 'none';
    els.viewerOpenLink.href = previewImage.url;
    els.viewerOpenLink.textContent = '打开预览图';
    els.viewerOpenLink.classList.remove('disabled');
    els.viewerOpenLink.hidden = false;
  } else if (conceptPreview?.url) {
    clearViewerLoadingFallback();
    els.viewerEmpty.dataset.keepPreview = '0';
    els.viewerEmpty.classList.remove('preview-fallback');
    els.viewerFrame.removeAttribute('src');
    els.viewerFrame.style.display = 'none';
    els.conceptPreviewImage.src = conceptPreview.url;
    els.conceptPreviewImage.alt = conceptPreview.label || '概念图预览';
    els.conceptPreviewImage.style.display = 'block';
    els.viewerEmpty.style.display = 'none';
    els.viewerOpenLink.href = conceptPreview.url;
    els.viewerOpenLink.textContent = '打开概念图';
    els.viewerOpenLink.classList.remove('disabled');
    els.viewerOpenLink.hidden = false;
  } else {
    clearViewerLoadingFallback();
    els.viewerEmpty.dataset.keepPreview = '0';
    els.viewerEmpty.classList.remove('preview-fallback');
    els.viewerFrame.removeAttribute('src');
    els.viewerFrame.style.display = 'none';
    els.conceptPreviewImage.removeAttribute('src');
    els.conceptPreviewImage.style.display = 'none';
    els.viewerEmpty.classList.remove('loading');
    els.viewerEmpty.style.display = 'grid';
    els.viewerEmpty.innerHTML = missingViewerMarkup(bundle, manifest);
    els.viewerOpenLink.href = '#';
    els.viewerOpenLink.textContent = '等待预览';
    els.viewerOpenLink.classList.add('disabled');
    els.viewerOpenLink.hidden = true;
  }
  if (blendUrl) {
    els.blendOpenLink.href = blendUrl;
    els.blendOpenLink.textContent = '打开工程文件';
    els.blendOpenLink.classList.remove('disabled');
    els.blendOpenLink.hidden = false;
  } else {
    els.blendOpenLink.href = '#';
    els.blendOpenLink.textContent = '等待工程';
    els.blendOpenLink.classList.add('disabled');
    els.blendOpenLink.hidden = true;
  }

  renderRunStatusStrip(status, bundle.summary || {}, manifest, bundle);
  renderWorkflowRibbon(status, bundle.summary || {}, manifest, bundle);
  renderTaskBrief(bundle, status, manifest);
  renderStageTimeline(status.phase || bundle.state?.phase || bundle.summary?.phase || 'INTAKE', bundle);
  renderStatusHero(status, bundle.summary || {}, bundle);
  renderNextActionBanner(bundle);
  renderUserGateActions(bundle);
  renderStatus(status, bundle.summary || {});
  renderUploads(bundle);
  renderAssets(bundle, manifest);
  renderAssetGallery(bundle);
  renderSceneObjectsPublic(scene.objects || [], viewerUrl, bundle);
  if (DEV_MODE) {
    renderPlan(
      bundle.runtime_plan || null,
      bundle.runtime_execution_summary || null,
      bundle.runtime_apply_summary || null,
      bundle.runtime_loop_summary || null,
      bundle.runtime_handoff_summary || null,
      bundle.runtime_worker_summary || null,
      bundle.runtime_user_action_summary || null,
    );
    renderObjects(scene.objects || []);
    renderFiles(bundle, manifest);
  } else {
    clearDevOnlyPanels();
  }
  renderDelivery(bundle, handoff, web);
}

function renderStageTimeline(phase, bundle) {
  const activeIndex = stageIndexForPhase(phase);
  const failed = phase === 'FAILED';
  const plan = bundle.runtime_plan?.runtime_plan || null;
  const needsUser = Boolean(
    plan?.requires_user
      || bundle.frontend_status?.status === 'needs_user_action'
      || bundle.frontend_status?.status === 'waiting_user',
  );
  const stages = STAGES.map((stage, index) => {
    const stateClass = failed
      ? (index <= activeIndex ? 'failed' : 'pending')
      : index < activeIndex
        ? 'done'
        : index === activeIndex
          ? 'active'
          : 'pending';
    return { stage, index, stateClass };
  });
  els.stageTimeline.innerHTML = stages.map(({ stage, index, stateClass }) => {
    return `
      <div class="stage-step ${stateClass}">
        <span class="stage-dot">${index + 1}</span>
        <span class="stage-copy">
          <strong>${escapeHtml(stage.label)}</strong>
          <small>${escapeHtml(stage.detail)}</small>
          <em>${escapeHtml(stageStateLabel(stateClass, needsUser))}</em>
        </span>
      </div>
    `;
  }).join('');
  if (els.stageRoadmap) {
    els.stageRoadmap.innerHTML = stages.map(({ stage, index, stateClass }) => `
      <div class="roadmap-step ${stateClass}" title="${escapeAttr(stage.detail)}">
        <span>${index + 1}</span>
        <strong>${escapeHtml(stage.label)}</strong>
      </div>
    `).join('');
  }
  if (needsUser) {
    els.stageTimeline.classList.add('needs-user');
    els.stageRoadmap?.classList.add('needs-user');
  } else {
    els.stageTimeline.classList.remove('needs-user');
    els.stageRoadmap?.classList.remove('needs-user');
  }
}

function clearDevOnlyPanels() {
  els.jobList.innerHTML = '';
  els.objectList.innerHTML = '';
  els.fileList.innerHTML = '';
  els.objectCount.textContent = '0';
  els.fileCount.textContent = '0';
}

function stageStateLabel(stateClass, needsUser) {
  if (stateClass === 'done') return '已完成';
  if (stateClass === 'active') return needsUser ? '待你确认' : '当前阶段';
  if (stateClass === 'failed') return '需要处理';
  return '待开始';
}

function renderNextActionBanner(bundle) {
  const plan = bundle.runtime_plan?.runtime_plan || null;
  const latestLoop = bundle.runtime_loop_summary?.latest_record || null;
  const latestExecution = bundle.runtime_execution_summary?.latest_record || null;
  const firstJob = plan?.jobs?.[0] || null;
  const phase = bundle.frontend_status?.phase || bundle.state?.phase || bundle.summary?.phase;
  const hasPreview = Boolean(bundle.web_surface?.viewer_scene_url || bundle.state?.viewer_scene || bundle.has_viewer_scene);
  const needsUser = Boolean(plan?.requires_user || bundle.frontend_status?.status === 'needs_user_action');
  const title = firstJob
    ? readableJobTitle(firstJob, bundle)
    : phase === 'BLENDER_PREVIEW' && hasPreview
      ? '请验收当前 3D 场景'
      : phase === 'DELIVERY'
        ? '检查交付文件'
        : latestLoop
          ? readableJobTitle(latestLoop)
          : '等待新的操作';
  const detail = firstJob
    ? nextActionText(firstJob, bundle)
    : phase === 'BLENDER_PREVIEW' && hasPreview
      ? '中间预览和右侧场景内容已经就绪。满意就确认交付，需要改动就在对话框输入修改意见。'
      : phase === 'DELIVERY'
        ? '预览、工程文件和交付包会在右侧集中展示，逐项检查即可。'
        : latestExecution
          ? `上一步已${statusLabel(latestExecution.status)}，可以继续查看资产状态或推进下一阶段。`
          : '在下方输入需求或上传参考图，系统会整理下一步。';
  const tone = firstJob?.kind === 'user_gate' || firstJob?.status === 'waiting_user'
    || needsUser
    ? 'user'
    : firstJob?.long_running
      ? 'handoff'
      : 'normal';
  els.nextActionBanner.className = `next-action-banner ${tone}`;
  els.nextActionBanner.innerHTML = `
    <div>
      <span>下一步</span>
      <strong>${escapeHtml(title)}</strong>
    </div>
    <p>${escapeHtml(detail)}</p>
  `;
}

function renderStatusHero(frontendStatus, summary, bundle) {
  const phase = frontendStatus.phase || bundle.state?.phase || summary.phase || 'INTAKE';
  const plan = bundle.runtime_plan?.runtime_plan || null;
  const firstJob = plan?.jobs?.[0] || null;
  const needsUser = Boolean(plan?.requires_user || frontendStatus.status === 'needs_user_action');
  const subtitle = statusHeroSubtitle({ bundle, firstJob, frontendStatus, phase, summary, needsUser });
  els.statusHero.className = `status-hero ${needsUser ? 'needs-user' : ''} ${phase === 'FAILED' ? 'failed' : ''}`;
  els.statusHero.innerHTML = `
    <span>当前阶段</span>
    <strong>${escapeHtml(phaseLabel(phase))}</strong>
    <p>${escapeHtml(subtitle)}</p>
  `;
}

function renderPlan(planBundle, executionSummary, applySummary, loopSummary, handoffSummary, workerSummary, userActionSummary) {
  const plan = planBundle?.runtime_plan || null;
  const controller = planBundle?.controller || null;
  els.jobList.innerHTML = '';
  if (!plan || !Array.isArray(plan.jobs) || !plan.jobs.length) {
    els.jobList.innerHTML = '<div class="job-item muted"><strong>还没有运行计划</strong><span>发送需求或上传参考图后，点击“生成计划”。</span></div>';
    return;
  }
  const summary = document.createElement('div');
  summary.className = `job-item${plan.blocked ? ' blocked' : ''}`;
  summary.innerHTML = `
    <strong>${escapeHtml(phaseLabel(plan.phase))} · ${escapeHtml(plan.blocked ? '阻塞' : '计划就绪')}</strong>
    <span>${escapeHtml(controller?.issues?.join(' · ') || plan.controller?.issues?.join(' · ') || '已生成下一步任务')}</span>
  `;
  els.jobList.appendChild(summary);
  if (executionSummary?.latest_record) {
    const latest = executionSummary.latest_record;
    const item = document.createElement('div');
    item.className = `job-item ${latest.status || ''}`;
    const title = readableJobTitle(latest);
    const meta = [statusLabel(latest.status), executorLabel(latest.executor), latest.dry_run ? '试跑' : null].filter(Boolean).join(' · ');
    item.innerHTML = `
      <strong>上一步：${escapeHtml(title)}</strong>
      <span>${escapeHtml(meta)}</span>
      <small>${escapeHtml(latest.error || latest.issues?.join(' · ') || latest.job_id || '')}</small>
    `;
    els.jobList.appendChild(item);
  }
  if (applySummary?.latest_record) {
    const latest = applySummary.latest_record;
    const item = document.createElement('div');
    item.className = `job-item ${latest.status || ''}`;
    const meta = [statusLabel(latest.status), nodeLabel(latest.node_name), latest.applied_fields?.join(', ')].filter(Boolean).join(' · ');
    item.innerHTML = `
      <strong>最近应用</strong>
      <span>${escapeHtml(meta)}</span>
      <small>${escapeHtml(latest.error || latest.issues?.join(' · ') || latest.checkpoint_id || latest.apply_id || '')}</small>
    `;
    els.jobList.appendChild(item);
  }
  if (loopSummary?.latest_record) {
    const latest = loopSummary.latest_record;
    const item = document.createElement('div');
    item.className = `job-item ${loopSummary.stop_reason || latest.execution_status || ''}`;
    const meta = [
      stopReasonLabel(loopSummary.stop_reason),
      statusLabel(latest.execution_status),
      statusLabel(latest.apply_status),
      `${loopSummary.total_records || 0} 条循环记录`,
    ].filter(Boolean).join(' · ');
    item.innerHTML = `
      <strong>循环</strong>
      <span>${escapeHtml(meta)}</span>
      <small>${escapeHtml(nodeLabel(latest.node_name || latest.domain_tool_name) || latest.job_id || latest.message || '')}</small>
    `;
    els.jobList.appendChild(item);
  }
  if (handoffSummary?.latest_record) {
    const latest = handoffSummary.latest_record;
    const item = document.createElement('div');
    item.className = `job-item ${latest.status || ''}`;
    const meta = [statusLabel(latest.status), nodeLabel(latest.domain_tool_name), `${handoffSummary.total_records || 0} 个子任务包`].filter(Boolean).join(' · ');
    item.innerHTML = `
      <strong>子任务交接</strong>
      <span>${escapeHtml(meta)}</span>
      <small>${escapeHtml(latest.command_hint || latest.handoff_id || '')}</small>
    `;
    els.jobList.appendChild(item);
  }
  if (workerSummary?.latest_record) {
    const latest = workerSummary.latest_record;
    const item = document.createElement('div');
    item.className = `job-item ${latest.status || ''}`;
    const meta = [statusLabel(latest.status), workerBackendLabel(latest.backend), latest.handoff_id].filter(Boolean).join(' · ');
    item.innerHTML = `
      <strong>最近子任务</strong>
      <span>${escapeHtml(meta)}</span>
      <small>${escapeHtml(latest.issues?.join(' · ') || latest.apply_status || latest.worker_id || '')}</small>
    `;
    els.jobList.appendChild(item);
  }
  if (userActionSummary?.latest_record) {
    const latest = userActionSummary.latest_record;
    const item = document.createElement('div');
    item.className = `job-item ${latest.status || ''}`;
    const meta = [statusLabel(latest.status), userActionLabel(latest.action_type), latest.checkpoint_id].filter(Boolean).join(' · ');
    item.innerHTML = `
      <strong>最近用户确认</strong>
      <span>${escapeHtml(meta)}</span>
      <small>${escapeHtml(latest.issues?.join(' · ') || latest.action_id || '')}</small>
    `;
    els.jobList.appendChild(item);
  }
  for (const job of plan.jobs) {
    const item = document.createElement('div');
    item.className = `job-item ${job.status || 'planned'}`;
    const title = readableJobTitle(job);
    const meta = [jobKindLabel(job.kind), executorLabel(job.executor), job.long_running ? '长任务' : null, statusLabel(job.status)].filter(Boolean).join(' · ');
    item.innerHTML = `
      <strong>${escapeHtml(title)}</strong>
      <span>${escapeHtml(meta)}</span>
      <small>${escapeHtml(reasonLabel(job.reason) || job.job_id || '')}</small>
    `;
    els.jobList.appendChild(item);
  }
}

function renderUserGateActions(bundle) {
  const phase = bundle.state?.phase || bundle.frontend_status?.phase;
  const concept = bundle.state?.concept_bundle || null;
  const viewerScene = bundle.state?.viewer_scene || null;
  const blenderScene = bundle.state?.blender_scene || null;
  const plan = bundle.runtime_plan?.runtime_plan || null;
  const firstJob = plan?.jobs?.[0] || null;
  els.userGateActions.innerHTML = '';
  const isConceptReview = phase === 'CONCEPT_REVIEW' && concept && !concept.approved;
  const isBlenderPreview = phase === 'BLENDER_PREVIEW' && viewerScene && blenderScene;
  if (!isConceptReview && !isBlenderPreview) {
    els.userGateActions.className = 'user-gate-actions idle';
    els.userGateActions.hidden = true;
    return;
  }
  els.userGateActions.hidden = false;
  els.userGateActions.className = 'user-gate-actions active';
  if (isBlenderPreview) {
    renderBlenderPreviewGate(firstJob, viewerScene, blenderScene);
    return;
  }
  renderConceptReviewGate(firstJob, concept);
}

function renderConceptReviewGate(firstJob, concept) {
  const previewId = concept.final_preview_image_id || Object.values(concept.subject_concept_images || {}).flat()[0] || '';
  const prompt = concept.prompt_pack?.final_preview_prompt || '';
  els.userGateActions.innerHTML = `
    <div class="gate-heading">
      <span>待你确认</span>
      <strong>概念图方向</strong>
    </div>
    <div class="gate-copy">
      <strong>${escapeHtml(firstJob ? readableJobTitle(firstJob) : '等待确认概念图')}</strong>
      <span>${escapeHtml(previewId ? '概念图已生成，确认后会继续生成 3D 资产。' : '已有概念结果，等待确认。')}</span>
      ${DEV_MODE && prompt ? `<small>${escapeHtml(prompt)}</small>` : ''}
    </div>
    <div class="gate-buttons">
      <button type="button" data-user-action="approve_concept">确认概念图</button>
      <button type="button" data-user-action="request_concept_changes">按输入意见重做</button>
    </div>
  `;
  bindGateButtons({
    approveSelector: '[data-user-action="approve_concept"]',
    requestSelector: '[data-user-action="request_concept_changes"]',
    approveActionType: 'approve_concept',
    requestActionType: 'request_concept_changes',
    feedbackPrefix: '概念图修改意见',
    emptyFeedbackMessage: '请先在左侧输入框写清楚要怎么改概念图。',
  });
}

function renderBlenderPreviewGate(firstJob, viewerScene, blenderScene) {
  const objectCount = Array.isArray(viewerScene.objects) ? viewerScene.objects.length : 0;
  const blendReady = Boolean(blenderScene.blend_file_artifact_id);
  const viewerReady = Boolean(viewerScene.viewer_scene_path || viewerScene.viewer_scene_artifact_id);
  els.userGateActions.innerHTML = `
    <div class="gate-heading">
      <span>待你确认</span>
      <strong>3D 场景验收</strong>
    </div>
    <div class="gate-copy">
      <strong>${escapeHtml(firstJob ? readableJobTitle(firstJob) : '请验收当前 3D 场景')}</strong>
      <span>请在中间预览区检查模型、位置和整体构图。</span>
      <div class="gate-readiness" aria-label="验收状态">
        <span>${escapeHtml(viewerReady ? '3D 预览已就绪' : '等待 3D 预览')}</span>
        <span>${escapeHtml(blendReady ? 'Blender 工程已就绪' : '等待工程文件')}</span>
        <span>${escapeHtml(objectCount ? `场景对象 ${objectCount} 个` : '场景对象待同步')}</span>
      </div>
      <small>满意就确认，系统会继续整理交付包；需要改动就在左侧输入修改意见。</small>
    </div>
    <div class="gate-buttons">
      <button type="button" data-user-action="approve_blender_preview">确认当前预览并打包</button>
      <button type="button" data-user-action="request_blender_changes">输入修改意见再调整</button>
    </div>
  `;
  bindGateButtons({
    approveSelector: '[data-user-action="approve_blender_preview"]',
    requestSelector: '[data-user-action="request_blender_changes"]',
    approveActionType: 'approve_blender_preview',
    requestActionType: 'request_blender_changes',
    feedbackPrefix: '预览修改意见',
    emptyFeedbackMessage: '请先在左侧输入框写清楚要怎么调整 3D 预览。',
  });
}

function bindGateButtons({
  approveSelector,
  requestSelector,
  approveActionType,
  requestActionType,
  feedbackPrefix,
  emptyFeedbackMessage,
}) {
  const approveButton = els.userGateActions.querySelector(approveSelector);
  const requestButton = els.userGateActions.querySelector(requestSelector);
  approveButton?.addEventListener('click', async () => {
    clearComposerNotice();
    await withBusy(approveButton, '确认中...', async () => {
      await runUserAction({ action_type: approveActionType });
      if (approveActionType === 'approve_blender_preview') {
        approveButton.textContent = '打包中...';
        startRunRefreshPoll({
          title: '正在打包交付',
          message: '已确认 3D 预览，正在刷新交付状态和文件入口。',
          stopWhen: (bundle) => {
            const phase = bundle?.frontend_status?.phase || bundle?.state?.phase;
            return phase === 'DELIVERY' && (bundle?.delivery_handoff?.ready || deliveryPackageReady(bundle || {}));
          },
          doneTitle: '交付状态已刷新',
          doneMessage: '请检查右侧验收与交付入口。',
        });
        await executeStep({ dryRun: false });
        stopRunRefreshPoll();
      }
      await refreshCurrentRunBundle({ refreshChatLog: false });
    });
  });
  requestButton?.addEventListener('click', async () => {
    const feedback = els.chatInput.value.trim();
    if (!feedback) {
      showComposerNotice('需要修改意见', emptyFeedbackMessage);
      els.chatInput.focus();
      return;
    }
    clearComposerNotice();
    await withBusy(requestButton, '记录中...', async () => {
      await submitFeedbackActionRequest({
        feedback,
        feedbackPrefix,
        metadata: { user_action: requestActionType },
        actionType: requestActionType,
      });
      els.chatInput.value = '';
    });
  });
}

async function submitFeedbackActionRequest({
  feedback,
  feedbackPrefix = '预览修改意见',
  metadata = {},
  actionType = 'request_blender_changes',
} = {}) {
  if (!state.currentRunKey) return null;
  const text = String(feedback || '').trim();
  if (!text) return null;
  const message = await api(`/api/runs/${encodeURIComponent(state.currentRunKey)}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      role: 'user',
      text: `${feedbackPrefix}：${text}`,
      metadata,
    }),
  });
  const action = await runUserAction({
    action_type: actionType,
    feedback_text: text,
    source_turn_id: message.message_id,
  });
  await refreshCurrentRunBundle({ refreshChatLog: true });
  return action;
}

async function refreshCurrentRunBundle({ refreshChatLog = false } = {}) {
  if (!state.currentRunKey) return null;
  state.bundle = await api(`/api/runs/${encodeURIComponent(state.currentRunKey)}`);
  renderBundle();
  if (refreshChatLog) await refreshChat();
  return state.bundle;
}

async function refreshChat() {
  if (!state.currentRunKey) return;
  const messages = await api(`/api/runs/${encodeURIComponent(state.currentRunKey)}/chat`);
  els.chatLog.innerHTML = '';
  const visibleMessages = messages.filter((message) => message.role !== 'system');
  for (const message of visibleMessages) {
    const node = document.createElement('div');
    node.className = `message ${message.role}`;
    node.innerHTML = `
      <span class="item-meta">${escapeHtml(roleLabel(message.role))}${message.created_at ? ` · ${escapeHtml(formatTime(message.created_at))}` : ''}</span>
      <div class="message-text">${escapeHtml(message.text)}</div>
    `;
    els.chatLog.appendChild(node);
  }
  els.chatLog.scrollTop = els.chatLog.scrollHeight;
}

function showComposerNotice(title, message) {
  if (!els.composerNotice) return;
  els.composerNotice.hidden = false;
  els.composerNotice.innerHTML = `
    <strong>${escapeHtml(title)}</strong>
    <span>${escapeHtml(message)}</span>
  `;
}

function clearComposerNotice() {
  if (!els.composerNotice) return;
  els.composerNotice.hidden = true;
  els.composerNotice.innerHTML = '';
}

function renderStatus(frontendStatus, summary) {
  const rows = [
    ['阶段', phaseLabel(frontendStatus.phase || summary.phase || '-')],
    ['状态', statusLabel(frontendStatus.status || (summary.ok ? 'completed' : '-'))],
    ['当前步骤', stageLabel(frontendStatus.current_stage) || '-'],
    ['节点', nodeLabel(frontendStatus.current_node) || '-'],
    ['流程', workflowLabel(frontendStatus.workflow || summary.workflow || '-')],
    ['工具调用', String(frontendStatus.tool_call_count ?? summary.tool_call_count ?? 0)],
  ];
  els.statusList.innerHTML = rows.map(([key, value]) => `<dt>${escapeHtml(key)}</dt><dd>${escapeHtml(value)}</dd>`).join('');
}

function missingViewerText(manifest) {
  const missing = manifest.missing_required || [];
  if (missing.includes('viewer_scene')) {
    return '当前还没有 3D 预览。会先展示概念图，确认后继续生成主体模型。';
  }
  return '当前还没有可验收的 3D 预览。';
}

function missingViewerMarkup(bundle, manifest) {
  const missing = manifest.missing_required || [];
  const hasSceneState = Boolean(bundle.scene_state);
  const phase = bundle.frontend_status?.phase || bundle.state?.phase || bundle.summary?.phase || 'INTAKE';
  const next = missingViewerNextText(bundle, missing, phase);
  return `
    <div class="empty-stack">
      <strong>${escapeHtml(missingViewerText(manifest))}</strong>
      <span>${escapeHtml(`当前阶段：${phaseLabel(phase)}`)}</span>
      <span>${escapeHtml(hasSceneState ? '已有场景状态，等待导出网页 3D 预览。' : '还没有可查看的场景，需要先完成需求、概念、模型和装配。')}</span>
      <span>${escapeHtml(next)}</span>
    </div>
  `;
}

function missingViewerNextText(bundle, missing, phase) {
  const plan = bundle.runtime_plan?.runtime_plan || null;
  const firstJob = plan?.jobs?.[0] || null;
  if (firstJob) return `下一步：${readableJobTitle(firstJob, bundle)}。${nextActionText(firstJob, bundle)}`;
  if (phase === 'INTAKE') return '下一步：上传参考图并说明主体、场景、风格或姿态用途。';
  if (phase === 'CONCEPT_REVIEW') return '下一步：确认概念图或输入修改意见，确认后才进入 3D 生成。';
  if (phase === 'SUBJECT_ASSET_GENERATION' || phase === 'SUBJECT_ASSET_QA') return '下一步：等待主体模型生成和质量检查完成。';
  if (phase === 'SCENE_ASSET_GENERATION' || phase === 'SCENE_ASSET_ADAPTATION') return '下一步：准备场景资产，然后装配到 Blender。';
  if (phase === 'BLENDER_ASSEMBLY_PLANNING' || phase === 'BLENDER_ASSEMBLY_EXECUTION') return '下一步：完成 Blender 装配并导出网页预览。';
  if (missing.includes('viewer_scene')) return '下一步：导出 viewer_scene.glb 后这里会自动显示可旋转的 3D 场景。';
  return '下一步：继续推进创作流程，直到出现 3D 预览。';
}

function viewerLoadingMarkup(previewImage = null) {
  return `
    <div class="empty-stack loading-stack ${previewImage?.url ? 'has-preview' : ''}">
      ${previewImage?.url ? `<img class="loading-preview-image" src="${escapeAttr(previewImage.url)}" alt="${escapeAttr(previewImage.label || '场景预览图')}">` : ''}
      <strong>正在载入 3D 场景</strong>
      <span>${escapeHtml(previewImage?.url ? '3D 模型较大，先显示 Blender 渲染预览；载入完成后可旋转检查模型。' : '预览模型已经生成，正在连接本地预览器。')}</span>
    </div>
  `;
}

function scheduleViewerLoadingFallback(viewerUrl, previewImage = null) {
  clearViewerLoadingFallback();
  state.viewerLoadingTimer = window.setTimeout(() => {
    if (els.viewerFrame.style.display === 'block' && sameBrowserUrl(els.viewerFrame.src, viewerUrl)) {
      els.viewerEmpty.style.display = 'grid';
      els.viewerEmpty.classList.add('loading');
      els.viewerEmpty.innerHTML = viewerLoadingMarkup(previewImage);
    }
  }, 3200);
}

function clearViewerLoadingFallback() {
  if (state.viewerLoadingTimer) {
    window.clearTimeout(state.viewerLoadingTimer);
    state.viewerLoadingTimer = null;
  }
}

function handleViewerFrameLoaded() {
  if (els.viewerFrame.style.display === 'block') {
    clearViewerLoadingFallback();
    if (els.viewerEmpty.dataset.keepPreview === '1') {
      els.viewerEmpty.style.display = 'grid';
      els.viewerEmpty.classList.add('loading', 'preview-fallback');
      return;
    }
    els.viewerEmpty.style.display = 'none';
    els.viewerEmpty.classList.remove('loading');
  }
}

function sameBrowserUrl(current, next) {
  try {
    return new URL(current, window.location.href).href === new URL(next, window.location.href).href;
  } catch {
    return String(current || '') === String(next || '');
  }
}

function renderRunStatusStrip(frontendStatus, summary, manifest, bundle) {
  const assets = assetProgressSummary(bundle, manifest);
  const items = [
    ['阶段', phaseLabel(frontendStatus.phase || summary.phase || '-')],
    ['下一步', compactNextAction(bundle)],
    ['场景预览', previewStateLabel(bundle, manifest)],
    ['素材', `${assets.ready} / ${assets.total} 就绪`],
  ];
  els.runStatusStrip.innerHTML = items.map(([label, value]) => `
    <div class="strip-item">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </div>
  `).join('');
}

function renderWorkflowRibbon(frontendStatus, summary, manifest, bundle) {
  const assets = assetProgressSummary(bundle, manifest);
  const phase = phaseLabel(frontendStatus.phase || summary.phase || bundle.state?.phase || '-');
  const next = compactNextAction(bundle);
  const preview = previewStateLabel(bundle, manifest);
  const assetText = `${assets.ready}/${assets.total} 个素材`;
  els.centerPhaseValue.textContent = phase;
  els.centerNextValue.textContent = next;
  els.centerPreviewValue.textContent = preview;
  els.centerAssetValue.textContent = assetText;
  els.workflowRibbon.className = `workflow-ribbon ${preview === '可打开' ? 'has-preview' : ''} ${assets.ready === assets.total ? 'complete' : ''}`;
}

function renderTaskBrief(bundle, frontendStatus, manifest) {
  if (!els.taskBrief) return;
  const stateBody = bundle.state || {};
  const sceneSpec = stateBody.scene_spec || {};
  const title = taskTitle(bundle, sceneSpec, frontendStatus);
  const goal = taskGoalText(stateBody, sceneSpec);
  const imageCount = Math.max(state.uploads.length, (stateBody.input_images || []).length);
  const bindingCount = (stateBody.reference_bindings || []).length;
  const assets = assetProgressSummary(bundle, manifest);
  const chips = [
    `${phaseLabel(frontendStatus.phase || stateBody.phase || bundle.summary?.phase || 'INTAKE')}`,
    imageCount ? `${imageCount} 张参考图${bindingCount >= imageCount ? '已绑定' : '待说明用途'}` : '未上传参考图',
    `${assets.ready}/${assets.total} 个资产就绪`,
  ];
  els.taskBrief.innerHTML = `
    <div class="task-copy">
      <span>当前任务</span>
      <strong>${escapeHtml(title)}</strong>
      <p>${escapeHtml(goal)}</p>
    </div>
    <div class="task-chips">
      ${chips.map((chip) => `<span>${escapeHtml(chip)}</span>`).join('')}
    </div>
  `;
}

function renderUploads(bundle = state.bundle) {
  els.uploadChips.innerHTML = '';
  const stateImages = (bundle?.state?.input_images || []).map((image, index) => ({
    upload_id: image.image_id || `input_image_${index + 1}`,
    image_id: image.image_id,
    filename: image.user_declared_label || image.image_id || `参考图 ${index + 1}`,
    state_only: true,
  }));
  const uploadImageIds = new Set(state.uploads.map((upload) => upload.image_id).filter(Boolean));
  const uploads = [
    ...state.uploads,
    ...stateImages.filter((image) => !uploadImageIds.has(image.image_id)),
  ];
  if (!uploads.length) {
    els.uploadChips.innerHTML = '<span class="upload-empty">还没有上传参考图</span>';
    return;
  }
  for (const upload of uploads) {
    const binding = uploadBindingInfo(bundle, upload);
    const chip = document.createElement('div');
    chip.className = `upload-chip ${binding.bound ? 'bound' : 'unbound'}`;
    chip.innerHTML = `
      <strong>${escapeHtml(upload.filename || upload.upload_id || 'upload')}</strong>
      <span>${escapeHtml(binding.label)}</span>
    `;
    els.uploadChips.appendChild(chip);
  }
}

function renderAssets(bundle, manifest) {
  const stateBody = bundle.state || {};
  const concept = stateBody.concept_bundle || {};
  const conceptPreview = conceptPreviewInfo(bundle);
  const conceptImages = Object.values(concept.subject_concept_images || {}).flat();
  const subjectAssets = stateBody.subject_assets || [];
  const sceneAsset = stateBody.scene_asset || null;
  const blenderScene = stateBody.blender_scene || null;
  const viewerScene = stateBody.viewer_scene || null;
  const files = manifest.files || [];
  const viewerFileReady = files.some((file) => file.label === 'viewer_scene' && file.exists);
  const viewerReady = Boolean(viewerScene || viewerFileReady || bundle.has_viewer_scene || bundle.web_surface?.viewer_scene_url || bundle.delivery_handoff?.viewer_url);
  const blendReady = Boolean(
    blenderScene?.blend_file_artifact_id
    || blenderScene?.blend_file_uri
    || files.some((file) => file.label === 'blend_file' && file.exists),
  );
  const phase = bundle.frontend_status?.phase || stateBody.phase || bundle.summary?.phase;
  const deliveryReady = Boolean(bundle.delivery_handoff?.ready || (phase === 'DELIVERY' && viewerReady && blendReady));
  const imageCount = Math.max(state.uploads.length, (stateBody.input_images || []).length);
  const referenceBindings = stateBody.reference_bindings || [];
  const unboundImageCount = Math.max(0, imageCount - referenceBindings.length);
  const assets = [
    {
      type: 'reference',
      label: '参考图',
      ready: imageCount > 0 || deliveryReady,
      detail: imageCount
        ? unboundImageCount
          ? `${imageCount} 张，${unboundImageCount} 张用途待说明`
          : `${imageCount} 张，用途已绑定`
        : deliveryReady ? '本次未上传参考图' : '待上传',
      pending: imageCount > 0 && unboundImageCount > 0,
      action: imageCount ? (unboundImageCount ? '待绑定' : '已接收') : deliveryReady ? '非必需' : '上传参考图',
    },
    {
      type: 'concept',
      label: '概念图',
      ready: Boolean(concept.final_preview_image_id || conceptImages.length || deliveryReady),
      detail: concept.approved ? '已确认' : concept.final_preview_image_id || conceptImages.length ? '等待确认' : deliveryReady ? '本次未使用概念图' : '待生成',
      pending: Boolean(concept.final_preview_image_id || conceptImages.length) && !concept.approved,
      imageUrl: conceptPreview?.url || '',
      action: concept.approved ? '已确认' : concept.final_preview_image_id || conceptImages.length ? '待确认' : deliveryReady ? '非必需' : '生成概念图',
    },
    {
      type: 'subject-glb',
      label: '主体模型',
      ready: subjectAssets.length > 0 || deliveryReady,
      detail: subjectAssets.length ? `${subjectAssets.length} 个资产` : deliveryReady ? '已随工程打包' : '待生成',
      action: subjectAssets.length ? '已生成' : deliveryReady ? '已包含' : '生成主体',
    },
    {
      type: 'scene-asset',
      label: '场景资产',
      ready: Boolean(sceneAsset || deliveryReady),
      detail: sceneAsset ? '已登记' : deliveryReady ? '已随工程打包' : '待生成',
      action: sceneAsset ? '已登记' : deliveryReady ? '已包含' : '生成场景',
    },
    {
      type: 'blend',
      label: '工程文件',
      ready: blendReady,
      detail: blendReady ? '可打开' : '待装配',
      action: blendReady ? '可打开' : '装配场景',
    },
    {
      type: 'viewer',
      label: '网页预览',
      ready: viewerReady,
      detail: viewerReady ? '可验收' : '待导出',
      action: viewerReady ? '可验收' : '导出预览',
    },
  ];
  els.assetList.innerHTML = assets.map((asset, index) => `
    <div class="asset-item asset-${escapeAttr(asset.type)} ${asset.ready ? 'ready' : 'missing'} ${asset.pending ? 'pending' : ''} ${asset.imageUrl ? 'with-thumb' : ''}">
      ${asset.imageUrl
        ? `<img class="asset-thumb" src="${escapeAttr(asset.imageUrl)}" alt="${escapeAttr(asset.label)}">`
        : `<span class="asset-step">${index + 1}</span>`}
      <div>
        <strong>${escapeHtml(asset.label)}</strong>
        <small>${escapeHtml(asset.detail)}</small>
      </div>
      <span class="asset-action">${escapeHtml(asset.action)}</span>
    </div>
  `).join('');
}

function renderAssetGallery(bundle) {
  if (!els.assetGallery) return;
  const artifacts = bundle.state?.artifacts || [];
  const conceptPreview = conceptPreviewInfo(bundle);
  const items = [];
  const seen = new Set();

  const addImage = (url, label, key) => {
    if (!url || seen.has(key || url)) return;
    seen.add(key || url);
    items.push({ type: 'image', url, label });
  };
  const addFile = (label, detail, key) => {
    if (seen.has(key || label)) return;
    seen.add(key || label);
    items.push({ type: 'file', label, detail });
  };

  addImage(conceptPreview?.url, '概念图', conceptPreview?.artifactId);
  const previewImage = blenderPreviewImageInfo(bundle);
  addImage(previewImage?.url, '场景预览图', previewImage?.artifactId);
  for (const artifact of artifacts) {
    const uri = artifact.uri || '';
    const url = artifactFileUrl(bundle, uri);
    const id = artifact.artifact_id || uri;
    if (url && /\.(png|jpe?g|webp)$/i.test(uri)) {
      addImage(url, artifactPublicLabel(artifact), id);
    }
  }
  if (bundle.web_surface?.viewer_scene_url || bundle.delivery_handoff?.viewer_url) {
    addFile('3D 场景', '网页预览可打开', 'viewer_scene');
  }
  if (hasBlendArtifact(bundle, bundle.file_manifest || {})) {
    addFile('Blender 工程', '工程文件已准备', 'blend_file');
  }
  if ((bundle.state?.subject_assets || []).length) {
    addFile('主体模型', `${bundle.state.subject_assets.length} 个 GLB 资产`, 'subject_assets');
  }

  const visible = items.slice(0, 6);
  if (!visible.length) {
    els.assetGallery.innerHTML = '<div class="asset-gallery-empty">等待资产写入</div>';
    return;
  }
  els.assetGallery.innerHTML = visible.map((item) => {
    if (item.type === 'image') {
      return `
        <div class="asset-gallery-card">
          <img src="${escapeAttr(item.url)}" alt="${escapeAttr(item.label)}">
          <span>${escapeHtml(item.label)}</span>
        </div>
      `;
    }
    return `
      <div class="asset-gallery-card file-card">
        <strong>${escapeHtml(item.label)}</strong>
        <small>${escapeHtml(item.detail)}</small>
      </div>
    `;
  }).join('');
}

function artifactPublicLabel(artifact) {
  const id = String(artifact?.artifact_id || '');
  const stage = artifact?.metadata?.stage || '';
  if (/concept/i.test(id) || /concept/i.test(stage)) return '概念图';
  if (/preview_png|preview|render/i.test(id) || /preview|render/i.test(stage)) return '预览图';
  if (/subject/i.test(id)) return '主体模型';
  if (/scene/i.test(id)) return '场景资产';
  return '资产';
}

function renderObjects(objects) {
  els.objectCount.textContent = String(objects.length);
  els.objectList.innerHTML = '';
  if (!objects.length) {
    els.objectList.innerHTML = '<div class="object-item muted"><strong>还没有场景内容</strong><span>导出 3D 预览后会在这里列出对象。</span></div>';
    return;
  }
  for (const object of objects) {
    const item = document.createElement('div');
    item.className = 'object-item';
    const rawName = object.display_name || object.viewer_object_id || object.blender_object_id || 'object';
    const name = objectDisplayName(rawName);
    const meta = [
      objectTypeLabel(object.object_type),
      object.subject_id ? `主体：${humanizeIdentifier(object.subject_id)}` : null,
      object.asset_id ? '已关联资产' : null,
    ].filter(Boolean).join(' · ') || '场景内容';
    const raw = [object.viewer_object_id, object.blender_object_id, object.asset_id].filter(Boolean).join(' · ');
    item.innerHTML = `
      <strong>${escapeHtml(name)}</strong>
      <span>${escapeHtml(meta)}</span>
      ${raw ? `<details><summary>技术详情</summary><small>${escapeHtml(raw)}</small></details>` : ''}
    `;
    els.objectList.appendChild(item);
  }
}

function renderSceneObjectsPublic(objects, viewerUrl, bundle = state.bundle) {
  if (!els.sceneObjectList) return;
  const visibleObjects = (objects || [])
    .filter((object) => publicSceneObjectVisible(object))
    .slice(0, 8);
  if (!visibleObjects.length) {
    els.sceneObjectList.innerHTML = '<div class="scene-object-empty">等待场景内容</div>';
    return;
  }
  els.sceneObjectList.innerHTML = visibleObjects.map((object) => {
    const rawName = object.display_name || object.viewer_object_id || object.blender_object_id || 'object';
    const name = objectDisplayName(rawName);
    const key = sceneObjectKey(object);
    const selected = key && key === state.selectedSceneObjectKey;
    const focusUrl = viewerFocusUrl(viewerUrl, object);
    const meta = [
      publicSceneObjectRole(object),
      selected ? '预览已选中' : null,
      focusUrl ? '可查看' : '等待预览',
      DEV_MODE && object.asset_id ? '已关联资产' : null,
      DEV_MODE && object.highlighted ? '重点对象' : null,
    ].filter(Boolean).join(' · ') || '场景内容';
    const boundsText = objectBoundsText(object.bounds);
    const focusAction = focusUrl
      ? `<a href="${escapeAttr(focusUrl)}" target="_blank" rel="noreferrer">聚焦查看</a>`
      : '<span>等待预览</span>';
    const editDraftText = objectFeedbackDraft(object);
    const editActions = canDraftObjectFeedback(bundle)
      ? `
          <button type="button" class="scene-object-draft" data-object-edit-draft="${escapeAttr(editDraftText)}">写草稿</button>
          <button type="button" class="scene-object-submit" data-object-edit-submit="${escapeAttr(editDraftText)}">提交修改</button>
          <button type="button" class="scene-object-refresh" data-object-edit-refresh="${escapeAttr(editDraftText)}">生成预览</button>
        `
      : '';
    return `
      <div class="scene-object-item ${selected ? 'selected' : ''}" data-scene-object-key="${escapeAttr(key)}">
        <div>
          <strong>${escapeHtml(name)}</strong>
          <small>${escapeHtml(meta)}</small>
          ${DEV_MODE && boundsText ? `<em>${escapeHtml(boundsText)}</em>` : ''}
        </div>
        <div class="scene-object-actions">
          ${focusAction}
          ${editActions}
        </div>
      </div>
    `;
  }).join('');
  bindSceneObjectDraftButtons();
  bindSceneObjectSubmitButtons();
  bindSceneObjectRefreshButtons();
  bindSceneObjectSelectCards();
}

function sceneObjectKey(object) {
  return String(object?.viewer_object_id || object?.blender_object_id || object?.display_name || '');
}

function bindSceneObjectSelectCards() {
  els.sceneObjectList.querySelectorAll('[data-scene-object-key]').forEach((item) => {
    item.addEventListener('click', (event) => {
      if (event.target.closest('button, a')) return;
      const key = item.getAttribute('data-scene-object-key') || '';
      const object = (state.bundle?.scene_state?.objects || []).find((candidate) => sceneObjectKey(candidate) === key);
      if (object) selectSceneObjectForReview(object, { source: 'object-card', fillDraft: false });
    });
  });
}

function publicSceneObjectVisible(object) {
  if (!object) return false;
  const type = String(object.object_type || '').toUpperCase();
  if (['CAMERA', 'LIGHT', 'EMPTY'].includes(type)) return false;
  if (object.selectable === false && type !== 'MESH') return false;
  const bounds = object.bounds || {};
  const min = bounds.min || [];
  const max = bounds.max || [];
  if (min.length === 3 && max.length === 3 && min.every((value, index) => Number(value) === Number(max[index]))) {
    return false;
  }
  return true;
}

function publicSceneObjectRole(object) {
  const rawName = String(object?.display_name || object?.viewer_object_id || object?.blender_object_id || '');
  if (object?.subject_id || /hunyuan3d|subject|主体/i.test(rawName)) return '主体模型';
  if (/light|lamp|灯/i.test(rawName)) return '灯光效果';
  if (/world|scene|geometry|background|env|环境|背景/i.test(rawName)) return '背景环境';
  return '场景元素';
}

function viewerFocusUrl(viewerUrl, object) {
  if (!viewerUrl) return '';
  const focus = objectFocus(object);
  if (!focus) return viewerEmbedUrl(viewerUrl);
  try {
    const parsed = new URL(viewerEmbedUrl(viewerUrl), window.location.href);
    parsed.searchParams.set('target', focus.target.join(','));
    parsed.searchParams.set('radius', String(focus.radius));
    parsed.searchParams.set('focus', objectDisplayName(object.display_name || object.viewer_object_id || object.blender_object_id || 'object'));
    return parsed.toString();
  } catch {
    return viewerEmbedUrl(viewerUrl);
  }
}

function objectFocus(object) {
  const bounds = object?.bounds || {};
  const min = (bounds.min || []).map(Number);
  const max = (bounds.max || []).map(Number);
  if (min.length !== 3 || max.length !== 3 || min.some(Number.isNaN) || max.some(Number.isNaN)) return null;
  const center = min.map((value, index) => roundNumber((value + max[index]) / 2, 4));
  const diagonal = Math.hypot(max[0] - min[0], max[1] - min[1], max[2] - min[2]);
  const radius = roundNumber(Math.max(0.35, diagonal * 2.6), 4);
  return { target: center, radius };
}

function objectBoundsText(bounds) {
  const min = (bounds?.min || []).map(Number);
  const max = (bounds?.max || []).map(Number);
  if (min.length !== 3 || max.length !== 3 || min.some(Number.isNaN) || max.some(Number.isNaN)) return '';
  const size = max.map((value, index) => Math.max(0, value - min[index]));
  return `尺寸 ${size.map((value) => roundNumber(value, 2)).join(' x ')}`;
}

function canDraftObjectFeedback(bundle = state.bundle) {
  const phase = bundle?.frontend_status?.phase || bundle?.state?.phase || bundle?.summary?.phase || '';
  return Boolean(
    bundle?.state?.viewer_scene
      || bundle?.has_viewer_scene
      || ['BLENDER_PREVIEW', 'BLENDER_EDIT', 'BLENDER_ASSEMBLY_EXECUTION'].includes(phase),
  );
}

function objectFeedbackDraft(object) {
  const rawName = object?.display_name || object?.viewer_object_id || object?.blender_object_id || '场景内容';
  const name = objectDisplayName(rawName);
  const role = publicSceneObjectRole(object);
  if (role === '主体模型') {
    return `请调整“${name}”：主体在画面中更醒目一些，位置稍微向前，大小保持自然，镜头不变。`;
  }
  if (role === '背景环境') {
    return `请调整“${name}”：让背景和主体关系更自然，不遮挡主体，整体构图保持清晰。`;
  }
  return `请调整“${name}”：位置和大小更贴合当前场景，保持整体风格和镜头不变。`;
}

function currentViewerUrl(bundle = state.bundle) {
  return bundle?.web_surface?.viewer_scene_url || bundle?.delivery_handoff?.viewer_url || null;
}

function selectSceneObjectForReview(object, { source = 'runtime-console', fillDraft = true } = {}) {
  if (!object) return;
  state.selectedSceneObjectKey = sceneObjectKey(object);
  renderSceneObjectsPublic(state.bundle?.scene_state?.objects || [], currentViewerUrl(), state.bundle);
  const name = objectDisplayName(object.display_name || object.viewer_object_id || object.blender_object_id || '场景内容');
  const draft = objectFeedbackDraft(object);
  if (fillDraft && !els.chatInput.value.trim()) {
    els.chatInput.value = draft;
  }
  const sourceLabel = source === 'viewer' || source === 'canvas-click' || source === 'object-chip'
    ? '3D 预览'
    : '场景内容';
  const next = els.chatInput.value.trim()
    ? '可以继续编辑输入框里的修改意见，然后提交或生成预览。'
    : '可以在输入框写修改意见，再提交或生成预览。';
  showComposerNotice(`已从${sourceLabel}选中对象`, `当前对象：“${name}”。${next}`);
}

function findSceneObjectByViewerPayload(payload) {
  const objects = state.bundle?.scene_state?.objects || [];
  const candidates = [
    payload?.viewer_object_id,
    payload?.blender_object_id,
    payload?.display_name,
  ].filter(Boolean).map(String);
  return objects.find((object) => {
    const keys = [object.viewer_object_id, object.blender_object_id, object.display_name].filter(Boolean).map(String);
    return keys.some((key) => candidates.includes(key));
  }) || null;
}

function handleViewerObjectSelectedMessage(event) {
  if (!els.viewerFrame || event.source !== els.viewerFrame.contentWindow) return;
  const data = event.data || {};
  if (!data || data.type !== 'image23d.viewer.objectSelected') return;
  const object = findSceneObjectByViewerPayload(data.object || {});
  if (object) {
    selectSceneObjectForReview(object, { source: data.source || 'viewer', fillDraft: true });
  }
}

function bindSceneObjectDraftButtons() {
  els.sceneObjectList.querySelectorAll('[data-object-edit-draft]').forEach((button) => {
    button.addEventListener('click', () => {
      const draft = button.getAttribute('data-object-edit-draft') || '';
      if (!draft) return;
      els.chatInput.value = draft;
      els.chatInput.focus();
      showComposerNotice('已填入修改意见', '请检查文字，然后点击“按输入意见调整”或直接发送。');
    });
  });
}

function bindSceneObjectSubmitButtons() {
  els.sceneObjectList.querySelectorAll('[data-object-edit-submit]').forEach((button) => {
    button.addEventListener('click', async () => {
      const feedback = button.getAttribute('data-object-edit-submit') || '';
      if (!feedback || !state.currentRunKey) return;
      clearComposerNotice();
      await withBusy(button, '提交中...', async () => {
        await submitFeedbackActionRequest({
          feedback,
          feedbackPrefix: '对象修改意见',
          metadata: { user_action: 'request_blender_changes', source: 'scene_object_quick_action' },
        });
        els.chatInput.value = '';
        showComposerNotice('已提交对象修改', '修改意见已进入当前运行计划，后续会走场景编辑路由和预览刷新。');
      });
    });
  });
}

function bindSceneObjectRefreshButtons() {
  els.sceneObjectList.querySelectorAll('[data-object-edit-refresh]').forEach((button) => {
    button.addEventListener('click', async () => {
      const feedback = button.getAttribute('data-object-edit-refresh') || '';
      if (!feedback || !state.currentRunKey) return;
      clearComposerNotice();
      await withBusy(button, '生成中...', async () => {
        await submitFeedbackActionRequest({
          feedback,
          feedbackPrefix: '对象修改并生成预览',
          metadata: { user_action: 'request_blender_changes', source: 'scene_object_refresh_action' },
        });
        startRunRefreshPoll({
          title: '正在生成新版预览',
          message: '已记录对象修改，正在轮询运行状态、预览文件和阶段变化。',
          stopWhen: (bundle) => ['BLENDER_PREVIEW', 'DELIVERY', 'FAILED'].includes(bundle?.frontend_status?.phase || bundle?.state?.phase || ''),
          doneTitle: '新版预览状态已刷新',
          doneMessage: '请检查中间 3D 预览和右侧阶段状态。',
        });
        const loop = await runLoop({
          dryRun: false,
          maxSteps: 6,
          blenderRawCallerSource: 'blender-lab-socket',
        });
        stopRunRefreshPoll();
        await refreshCurrentRunBundle({ refreshChatLog: true });
        els.chatInput.value = '';
        showComposerNotice(loopNoticeTitle(loop), loopNoticeMessage(loop));
      });
    });
  });
}

function renderFiles(bundle, manifest) {
  const files = manifest.files || [];
  const okCount = files.filter((file) => file.exists).length;
  const missingCount = files.length - okCount;
  els.fileCount.textContent = `${okCount}/${files.length}`;
  els.fileList.innerHTML = '';
  if (!files.length) {
    els.fileList.innerHTML = '<div class="file-item missing"><strong>没有文件清单</strong><span>当前运行还没有返回文件记录。</span></div>';
    return;
  }
  const summary = document.createElement('div');
  summary.className = `file-summary${missingCount ? ' missing' : ''}`;
  summary.innerHTML = `<strong>${escapeHtml(okCount)} 个文件就绪</strong><span>${escapeHtml(missingCount)} 个缺失</span>`;
  els.fileList.appendChild(summary);
  for (const [groupName, groupFiles] of groupedFiles(files)) {
    const group = document.createElement('div');
    group.className = 'file-group-title';
    group.textContent = groupName;
    els.fileList.appendChild(group);
    for (const file of groupFiles) {
      els.fileList.appendChild(fileNode(file));
    }
  }
  if (bundle.effective_run_dir && bundle.effective_run_dir !== bundle.run_dir) {
    const item = document.createElement('div');
    item.className = 'file-item';
    item.innerHTML = `
      <div>
        <strong>预览来源</strong>
        <span>已定位到可展示结果</span>
      </div>
      <span>当前</span>
      <details><summary>文件详情</summary><small>${escapeHtml(shortPath(bundle.effective_run_dir))}</small></details>
    `;
    els.fileList.prepend(item);
  }
}

function fileNode(file) {
    const item = document.createElement('div');
    item.className = `file-item${file.exists ? '' : ' missing'}`;
    const label = `${file.exists ? '就绪' : '等待生成'} · ${fileKindLabel(file.kind)}`;
    const path = file.path || file.relative_path;
    const action = file.exists && file.url
      ? `<a href="${escapeAttr(file.url)}" target="_blank" rel="noreferrer">打开</a>`
      : '<span>未生成</span>';
    item.innerHTML = `
      <div>
        <strong>${escapeHtml(fileLabel(file.label))}</strong>
        <span>${escapeHtml(label)}</span>
      </div>
      ${action}
      <details>
        <summary>文件详情</summary>
        <small>${escapeHtml(shortPath(path))}</small>
      </details>
    `;
    return item;
}

function groupedFiles(files) {
  const order = ['需求输入', '运行链路', '3D预览', '交付'];
  const groups = new Map(order.map((name) => [name, []]));
  for (const file of files) {
    groups.get(fileGroupName(file.label)).push(file);
  }
  return order
    .map((name) => [name, groups.get(name).slice().sort((a, b) => Number(a.exists) - Number(b.exists))])
    .filter(([, groupFiles]) => groupFiles.length);
}

function fileGroupName(label) {
  if (['chat', 'uploads', 'state'].includes(label)) return '需求输入';
  if (label.startsWith('runtime_')) return '运行链路';
  if (['scene_state', 'viewer_scene'].includes(label)) return '3D预览';
  return '交付';
}

function renderDelivery(bundle, handoff, web) {
  const manifest = bundle.file_manifest || {};
  const blendReady = hasBlendArtifact(bundle, manifest);
  const blendUrl = blendReady ? (web.blender_web_http_url || handoff.blender_web_http_url || null) : null;
  const viewerUrl = web.viewer_scene_url || handoff.viewer_url || '';
  const glbUrl = web.viewer_asset_url || handoff.asset_url || '';
  const packageInfo = deliveryPackageInfo(bundle);
  const stateFile = manifestFile(bundle, 'state');
  const sceneStateFile = manifestFile(bundle, 'scene_state');
  const handoffFile = manifestFile(bundle, 'delivery_handoff');
  const handoffIssues = handoffIssuesText(handoff);
  const publicItems = [
    {
      label: '交付状态',
      value: handoff.ready ? (handoff.verified ? '已验证，可以交付' : '文件已准备，等待验证') : handoffIssues,
      kind: 'status',
      ready: Boolean(handoff.ready),
      waiting: '等待交付预检',
    },
    { label: '打开 3D 预览', value: viewerUrl, kind: 'url', action: '打开', waiting: '等待 3D 预览生成' },
    { label: '下载 3D 模型', value: glbUrl, kind: 'url', action: '下载', waiting: '等待模型导出' },
    { label: '打开工程文件', value: blendUrl, kind: blendUrl ? 'url' : 'file', action: '打开', waiting: '等待场景装配' },
    { label: '下载交付包', value: packageInfo.url, kind: 'url', action: '下载', waiting: packageInfo.waiting },
  ];
  const devItems = [
    stateFile ? { label: '状态 JSON', value: stateFile.url, kind: 'url', action: '打开', waiting: '等待状态文件' } : null,
    sceneStateFile ? { label: '场景 JSON', value: sceneStateFile.url, kind: 'url', action: '打开', waiting: '等待场景状态' } : null,
    handoffFile ? { label: '交付说明', value: handoffFile.url, kind: 'url', action: '打开', waiting: '等待交付说明' } : null,
  ];
  const items = [...publicItems, ...(DEV_MODE ? devItems : [])].filter(Boolean);
  els.deliveryList.innerHTML = '';
  for (const itemDef of items) {
    const { label, value, kind } = itemDef;
    const item = document.createElement('div');
    const ready = itemDef.ready ?? Boolean(value);
    item.className = `delivery-item ${ready ? 'delivery-ready' : 'delivery-waiting disabled'} ${kind === 'status' ? 'delivery-status' : ''}`;
    if (kind === 'url' && value) {
      item.innerHTML = `
        <strong>${escapeHtml(label)}</strong>
        <a href="${escapeAttr(value)}" target="_blank" rel="noreferrer">${escapeHtml(itemDef.action || '打开')}</a>
      `;
    } else if (!value) {
      item.innerHTML = `
        <strong>${escapeHtml(label)}</strong>
        <span>${escapeHtml(itemDef.waiting)}</span>
      `;
    } else {
      item.innerHTML = `
        <strong>${escapeHtml(label)}</strong>
        <span>${escapeHtml(String(value))}</span>
      `;
    }
    els.deliveryList.appendChild(item);
  }
}

function runDisplayTitle(run, index) {
  const text = run.display_name || run.run_id || `运行 ${index + 1}`;
  if (isInternalRunName(text) && !run.has_viewer_scene && !run.has_scene_state) {
    return `后台步骤 ${index + 1}`;
  }
  const runtimeDate = String(text).match(/runtime_console_(\d{8})T?(\d{2})?(\d{2})?/);
  if (runtimeDate) {
    const [, day, hour = '', minute = ''] = runtimeDate;
    const time = hour ? ` ${hour}:${minute || '00'}` : '';
    return `创作 ${day.slice(4, 6)}-${day.slice(6, 8)}${time}`;
  }
  const dated = String(text).match(/^(\d{8})[_/-](.+)$/);
  if (dated) {
    const [, day, rawName] = dated;
    return `${day.slice(4, 6)}-${day.slice(6, 8)} · ${runNameLabel(rawName)}`;
  }
  const workerDate = String(text).match(/runtime_(.+)_smoke_(\d{8})T?(\d{2})?(\d{2})?/);
  if (workerDate) {
    const [, rawName, day, hour = '', minute = ''] = workerDate;
    const time = hour ? ` ${hour}:${minute || '00'}` : '';
    return `${day.slice(4, 6)}-${day.slice(6, 8)}${time} · ${runNameLabel(rawName)}`;
  }
  if (run.is_stage && run.stage_id) {
    return `${runNameLabel(run.stage_id)} · 子阶段`;
  }
  return runNameLabel(text);
}

function runBadges(run) {
  const name = String(run.display_name || run.run_id || '');
  return [
    run.has_viewer_scene ? '有 3D 预览' : null,
    run.has_scene_state && !run.has_viewer_scene ? '已装配' : null,
    run.has_frontend_status && !run.has_viewer_scene && !run.has_scene_state ? '进行中' : null,
    isUserConsoleRunName(name) && !run.has_viewer_scene ? '用户创作' : null,
    DEV_MODE && run.is_stage ? '子阶段' : null,
  ].filter(Boolean);
}

function viewerTitle(bundle, scene, frontendStatus, conceptPreview = null, previewImage = null) {
  if (bundle?.has_viewer_scene || scene?.viewer_scene_id || frontendStatus?.viewer_scene_id) {
    return '3D 场景预览';
  }
  if (previewImage?.url) return '场景渲染预览';
  if (conceptPreview?.url) return '概念图预览';
  if (bundle?.has_scene_state) return '场景已装配';
  return '等待生成 3D 预览';
}

function taskTitle(bundle, sceneSpec, frontendStatus) {
  const phase = frontendStatus?.phase || bundle.state?.phase || bundle.summary?.phase;
  const sceneTitle = publicTaskCopy(sceneSpec?.title);
  if (sceneTitle) return sceneTitle;
  const latestTurn = latestUserText(bundle.state?.user_turns || []);
  const latestPublic = publicTaskCopy(latestTurn);
  if (latestPublic) return compactSentence(latestPublic, 34);
  if (phase === 'BLENDER_PREVIEW') return '查看并验收 3D 场景';
  if (phase === 'DELIVERY') return '检查交付文件';
  if (phase === 'CONCEPT_REVIEW') return '确认概念图方向';
  if (bundle.has_viewer_scene) return '查看已生成场景';
  return '新建创作';
}

function taskGoalText(stateBody, sceneSpec) {
  const sceneGoal = publicTaskCopy(sceneSpec?.user_goal);
  if (sceneGoal) return sceneGoal;
  const summary = publicTaskCopy(stateBody?.conversation_summary);
  if (summary) return summary;
  const latestTurn = latestUserText(stateBody?.user_turns || []);
  const latestPublic = publicTaskCopy(latestTurn);
  if (latestPublic) return latestPublic;
  if (stateBody?.phase === 'DELIVERY') return '当前创作已经整理出可交付文件，请检查 3D 预览、工程文件和交付包是否齐全。';
  if (stateBody?.phase === 'BLENDER_PREVIEW') return '当前场景已经进入预览验收，请查看中间画面并确认是否继续交付或提出修改。';
  return '描述你想要的角色、环境、参考图用途和验收标准，系统会整理成可执行的图像到 3D 场景流程。';
}

function publicTaskCopy(value) {
  const text = String(value || '').replace(/\s+/g, ' ').trim();
  if (!text) return '';
  if (DEV_MODE) return text;
  if (isDebugPublicText(text)) return '';
  const hasCjk = /[\u3400-\u9fff]/.test(text);
  const asciiCount = (text.match(/[A-Za-z]/g) || []).length;
  if (!hasCjk && asciiCount > 14) return '';
  return text;
}

function latestUserText(turns) {
  const latest = turns
    .slice()
    .reverse()
    .find((turn) => String(turn.role || 'user') === 'user' && (turn.text || turn.content));
  return String(latest?.text || latest?.content || '').trim();
}

function compactSentence(text, limit = 42) {
  const clean = String(text || '').replace(/\s+/g, ' ').trim();
  if (clean.length <= limit) return clean;
  return `${clean.slice(0, Math.max(0, limit - 1))}...`;
}

function roundNumber(value, digits = 3) {
  const factor = 10 ** digits;
  return Math.round(Number(value) * factor) / factor;
}

function isDebugPublicText(value) {
  const text = String(value || '');
  if (!text.trim()) return false;
  if (/\b(smoke|router|debug|fixture|dry[-_ ]?run|deepseek|qwen|socket|scratch|runtime|toolcall|test)\b/i.test(text)) return true;
  const asciiCount = (text.match(/[A-Za-z]/g) || []).length;
  return asciiCount > 24 && /placement|workflow|execution|artifact|handoff|node/i.test(text);
}

function isUserConsoleRunName(name) {
  return /^runtime_console_\d{8}/i.test(String(name || ''))
    || /console_user|runtime_console_user|用户|创作/i.test(String(name || ''));
}

function isPublicShowcaseRunName(name) {
  return /scene_spec_assembly_non_dryrun|p0_real_demo|real_demo|codex_self_robot_concept/i.test(String(name || ''));
}

function isDryRunRunName(name) {
  const text = String(name || '');
  if (/non[_-]?dryrun/i.test(text)) return false;
  return normalizedNameHasAny(text, ['smoke', 'audit', 'dryrun', 'dry run', 'preflight', 'http audit', 'step smoke', 'plan smoke']);
}

function isInternalRunName(name) {
  const text = String(name || '');
  if (isUserConsoleRunName(text)) return false;
  if (isPublicShowcaseRunName(text)) return false;
  return normalizedNameHasAny(text, [
    'smoke',
    'audit',
    'dryrun',
    'dry run',
    'fixture',
    'handoff',
    'worker',
    'loop',
    'step smoke',
    'plan smoke',
    'http audit',
    'apply',
    'qwen',
    'deepseek',
    'llm node',
    'socket',
    'scratch',
    'router',
    'live router',
  ])
    || /^202\d{5}_runtime_/i.test(text);
}

function normalizedNameHasAny(value, phrases) {
  const normalized = String(value || '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  return phrases.some((phrase) => normalized.includes(phrase));
}

els.newRunButton.addEventListener('click', async () => {
  const created = await api('/api/runs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  });
  await refreshRuns(false);
  const createdItem = state.runs.find((run) => run.run_id === created.run_id || run.relative_path === created.run_id);
  await selectRun(routeKey(createdItem) || created.run_id);
});

els.refreshRunsButton.addEventListener('click', () => refreshRuns(false));

els.planButton.addEventListener('click', async () => {
  if (!state.currentRunKey) return;
  await withBusy(els.planButton, '生成中...', async () => {
    await buildPlan({ silent: false });
    state.bundle = await api(`/api/runs/${encodeURIComponent(state.currentRunKey)}`);
    renderBundle();
  });
});

els.stepButton.addEventListener('click', async () => {
  if (!state.currentRunKey) return;
  await withBusy(els.stepButton, '试跑中...', async () => {
    await executeStep({ dryRun: true });
    state.bundle = await api(`/api/runs/${encodeURIComponent(state.currentRunKey)}`);
    renderBundle();
  });
});

els.applyButton.addEventListener('click', async () => {
  if (!state.currentRunKey) return;
  await withBusy(els.applyButton, '应用中...', async () => {
    await applyCandidate();
    state.bundle = await api(`/api/runs/${encodeURIComponent(state.currentRunKey)}`);
    renderBundle();
  });
});

els.loopButton.addEventListener('click', async () => {
  if (!state.currentRunKey) return;
  await withBusy(els.loopButton, '循环中...', async () => {
    await runLoop();
    state.bundle = await api(`/api/runs/${encodeURIComponent(state.currentRunKey)}`);
    renderBundle();
  });
});

els.handoffButton.addEventListener('click', async () => {
  if (!state.currentRunKey) return;
  await withBusy(els.handoffButton, '整理中...', async () => {
    await planHandoff();
    state.bundle = await api(`/api/runs/${encodeURIComponent(state.currentRunKey)}`);
    renderBundle();
  });
});

els.workerButton.addEventListener('click', async () => {
  if (!state.currentRunKey) return;
  await withBusy(els.workerButton, '试跑中...', async () => {
    await runWorkerDryRun();
    state.bundle = await api(`/api/runs/${encodeURIComponent(state.currentRunKey)}`);
    renderBundle();
  });
});

async function buildPlan({ silent = true } = {}) {
  try {
    return await api(`/api/runs/${encodeURIComponent(state.currentRunKey)}/plan`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
  } catch (error) {
    if (!silent) {
      els.jobList.innerHTML = `<div class="job-item blocked"><strong>计划生成失败</strong><span>${escapeHtml(friendlyError(error.message))}</span></div>`;
    }
    return null;
  }
}

async function executeStep({ dryRun = true } = {}) {
  try {
    return await api(`/api/runs/${encodeURIComponent(state.currentRunKey)}/step`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ dry_run: dryRun }),
    });
  } catch (error) {
    els.jobList.innerHTML = `<div class="job-item blocked"><strong>试跑失败</strong><span>${escapeHtml(friendlyError(error.message))}</span></div>`;
    showComposerNotice('操作失败', friendlyError(error.message));
    return null;
  }
}

async function applyCandidate() {
  try {
    return await api(`/api/runs/${encodeURIComponent(state.currentRunKey)}/apply`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rebuild_plan: true }),
    });
  } catch (error) {
    els.jobList.innerHTML = `<div class="job-item blocked"><strong>应用失败</strong><span>${escapeHtml(friendlyError(error.message))}</span></div>`;
    return null;
  }
}

async function runLoop({ dryRun = true, maxSteps = 8, blenderRawCallerSource = null } = {}) {
  try {
    return await api(`/api/runs/${encodeURIComponent(state.currentRunKey)}/loop`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        dry_run: dryRun,
        max_steps: maxSteps,
        ...(blenderRawCallerSource ? { blender_raw_caller_source: blenderRawCallerSource } : {}),
      }),
    });
  } catch (error) {
    els.jobList.innerHTML = `<div class="job-item blocked"><strong>循环失败</strong><span>${escapeHtml(friendlyError(error.message))}</span></div>`;
    return null;
  }
}

function startRunRefreshPoll({
  title,
  message,
  intervalMs = 2500,
  maxPolls = 80,
  stopWhen = null,
  doneTitle = '运行状态已刷新',
  doneMessage = '当前运行状态已经更新。',
} = {}) {
  stopRunRefreshPoll();
  state.runRefreshPollCount = 0;
  showComposerNotice(title || '正在刷新运行状态', message || '正在同步当前运行状态。');
  const expectedRunKey = state.currentRunKey;
  const tick = async () => {
    if (!expectedRunKey || state.currentRunKey !== expectedRunKey) {
      stopRunRefreshPoll();
      return;
    }
    state.runRefreshPollCount += 1;
    try {
      const bundle = await refreshCurrentRunBundle({ refreshChatLog: state.runRefreshPollCount % 3 === 0 });
      const phase = phaseLabel(bundle?.frontend_status?.phase || bundle?.state?.phase || bundle?.summary?.phase || '');
      const next = compactNextAction(bundle || {});
      showComposerNotice(title || '正在刷新运行状态', `${message || '正在同步当前运行状态。'} 当前阶段：${phase}；下一步：${next}。`);
      if (typeof stopWhen === 'function' && stopWhen(bundle)) {
        stopRunRefreshPoll();
        showComposerNotice(doneTitle, doneMessage);
      } else if (state.runRefreshPollCount >= maxPolls) {
        stopRunRefreshPoll();
        showComposerNotice('刷新仍在继续', '已达到本次前端轮询上限，请稍后点击刷新或查看运行记录。');
      }
    } catch (error) {
      if (state.runRefreshPollCount >= maxPolls) {
        stopRunRefreshPoll();
        showComposerNotice('刷新失败', friendlyError(error.message));
      }
    }
  };
  state.runRefreshPollTimer = window.setInterval(tick, intervalMs);
  tick();
}

function stopRunRefreshPoll() {
  if (state.runRefreshPollTimer) {
    window.clearInterval(state.runRefreshPollTimer);
    state.runRefreshPollTimer = null;
  }
  state.runRefreshPollCount = 0;
}

function loopNoticeTitle(loop) {
  if (!loop) return '生成未完成';
  if (loop.stop_reason === 'waiting_user') return '新版预览已进入验收';
  if (loop.stop_reason === 'completed_no_jobs') return '当前没有剩余任务';
  if (loop.stop_reason === 'delegated') return '任务已交给后台';
  if (loop.stop_reason === 'max_steps') return '已执行到步数上限';
  if (loop.stop_reason === 'dry_run_needs_live_or_fixture') return '需要真实执行配置';
  if (loop.ok) return '生成流程已更新';
  return '生成未完成';
}

function loopNoticeMessage(loop) {
  if (!loop) return '请查看运行记录或开发详情确认失败原因。';
  if (loop.stop_reason === 'waiting_user') return 'runtime 已回到用户验收节点，请检查中间预览区的新结果。';
  if (loop.stop_reason === 'completed_no_jobs') return '当前计划没有剩余可执行任务。';
  if (loop.stop_reason === 'delegated') return '当前步骤需要后台或子任务完成，结果会回写到当前创作。';
  if (loop.stop_reason === 'max_steps') return '已完成本次受控执行预算，请检查预览或继续执行下一步。';
  if (loop.stop_reason === 'dry_run_needs_live_or_fixture') return '当前计划需要 live provider、fixture 或显式服务配置才能继续。';
  const issue = (loop.issues || []).join('；');
  return issue || loop.message || '已记录执行结果，请查看当前阶段和运行文件。';
}

async function planHandoff() {
  try {
    return await api(`/api/runs/${encodeURIComponent(state.currentRunKey)}/handoff`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
  } catch (error) {
    els.jobList.innerHTML = `<div class="job-item blocked"><strong>子任务交接失败</strong><span>${escapeHtml(friendlyError(error.message))}</span></div>`;
    return null;
  }
}

async function runWorkerDryRun() {
  try {
    return await api(`/api/runs/${encodeURIComponent(state.currentRunKey)}/worker`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ backend: 'fixture', dry_run: true }),
    });
  } catch (error) {
    els.jobList.innerHTML = `<div class="job-item blocked"><strong>子任务试跑失败</strong><span>${escapeHtml(friendlyError(error.message))}</span></div>`;
    return null;
  }
}

async function runUserAction(payload) {
  try {
    return await api(`/api/runs/${encodeURIComponent(state.currentRunKey)}/user-action`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rebuild_plan: true, ...payload }),
    });
  } catch (error) {
    els.jobList.innerHTML = `<div class="job-item blocked"><strong>用户确认失败</strong><span>${escapeHtml(friendlyError(error.message))}</span></div>`;
    showComposerNotice('确认失败', friendlyError(error.message));
    return null;
  }
}

async function withBusy(button, label, action) {
  const original = button.textContent;
  button.disabled = true;
  button.textContent = label;
  try {
    return await action();
  } finally {
    button.disabled = false;
    button.textContent = original;
  }
}

function phaseLabel(value) {
  if (!value || value === '-') return '-';
  return PHASE_LABELS[value] || '准备中';
}

function statusLabel(value) {
  if (!value || value === '-') return '-';
  return STATUS_LABELS[value] || '准备中';
}

function stageLabel(value) {
  const normalized = String(value || '').replace(/^workflow_runner\./, '');
  return STAGE_LABELS[value] || STAGE_LABELS[normalized] || '';
}

function nodeLabel(value) {
  return NODE_LABELS[value] || '';
}

function readableJobTitle(job, bundle = null) {
  if (!job) return '继续生成';
  if (job.kind === 'user_gate' || job.status === 'waiting_user') {
    const phase = bundle?.state?.phase || bundle?.frontend_status?.phase || job.phase;
    if (phase === 'BLENDER_PREVIEW') return '请验收当前 3D 场景';
    if (phase === 'CONCEPT_REVIEW') return '请确认概念图方向';
    return '等待你的确认';
  }
  return nodeLabel(job?.node_name || job?.domain_tool_name || job?.job_kind || job?.kind) || '继续生成';
}

function nextActionText(job, bundle = null) {
  if (!job) return '等待新的操作。';
  if (job.kind === 'user_gate' || job.status === 'waiting_user') {
    const phase = bundle?.state?.phase || bundle?.frontend_status?.phase || job.phase;
    if (phase === 'BLENDER_PREVIEW') return '请在中间预览区查看 3D 场景，确认后会整理交付文件。';
    if (phase === 'CONCEPT_REVIEW') return '请查看概念图，确认后才会继续生成 3D 模型。';
    return '需要你确认或补充信息，确认后再继续生成。';
  }
  if (job.domain_tool_name === 'build_subject_asset') {
    return '主体概念已经确认，下一步生成可放入场景的主体模型。';
  }
  if (job.domain_tool_name === 'build_scene_asset' || job.domain_tool_name === 'adapt_scene_asset') {
    return '主体资产已准备，下一步生成或适配场景环境资产。';
  }
  if (job.domain_tool_name === 'export_viewer_scene' || job.domain_tool_name === 'render_preview') {
    return '场景需要生成 3D 预览，生成后即可在中间窗口验收。';
  }
  if (job.long_running || job.executor === 'sub_agent' || job.executor === 'background_worker') {
    return '这是耗时生成任务，会在后台完成，结束后自动登记到当前创作。';
  }
  if (job.kind === 'llm_node') {
    return '正在整理你的需求和参考图，形成下一步可执行的生成计划。';
  }
  return reasonLabel(job.reason) || '继续执行当前计划。';
}

function compactNextAction(bundle) {
  const plan = bundle.runtime_plan?.runtime_plan || null;
  const firstJob = plan?.jobs?.[0] || null;
  const phase = bundle.frontend_status?.phase || bundle.state?.phase || bundle.summary?.phase;
  if (firstJob) return readableJobTitle(firstJob);
  if (phase === 'BLENDER_PREVIEW' && (bundle.web_surface?.viewer_scene_url || bundle.state?.viewer_scene)) return '验收预览';
  if (phase === 'DELIVERY') return '检查交付';
  if (phase === 'INTAKE') return '补充需求';
  return '继续生成';
}

function statusHeroSubtitle({ bundle, firstJob, frontendStatus, phase, summary, needsUser }) {
  if (needsUser && phase === 'BLENDER_PREVIEW') return '3D 场景已生成，请在中间预览区验收。';
  if (needsUser && phase === 'CONCEPT_REVIEW') return '概念图已生成，请确认方向或输入修改意见。';
  if (needsUser) return '需要你确认或补充信息，确认后再继续生成。';
  if (phase === 'CONCEPT_REVIEW') return '概念图已经生成，请确认方向或输入修改意见。';
  if (phase === 'CONCEPT_APPROVED') return '概念方向已确认，下一步生成主体 3D 模型。';
  if (phase === 'SUBJECT_ASSET_GENERATION') return '正在生成主体 3D 资产，完成后会登记模型文件。';
  if (phase === 'SUBJECT_ASSET_QA') return '主体模型已登记，正在进入场景资产和装配阶段。';
  if (phase === 'SCENE_ASSET_GENERATION' || phase === 'SCENE_ASSET_ADAPTATION') return '正在准备可导入场景工程的环境资产。';
  if (phase === 'BLENDER_PREVIEW' && (bundle.web_surface?.viewer_scene_url || bundle.state?.viewer_scene)) {
    return '3D 场景已经导出，可以在中间预览后确认交付或继续修改。';
  }
  if (phase === 'DELIVERY') return '交付文件已经整理完成，可以打开预览或下载结果。';
  if (phase === 'INTAKE') return '请上传参考图并描述角色、场景和参考图用途。';
  if (firstJob) return nextActionText(firstJob, bundle);
  return statusLabel(frontendStatus.status || (summary.ok ? 'completed' : 'ready'));
}

function previewStateLabel(bundle, manifest) {
  if (bundle.web_surface?.viewer_scene_url || bundle.state?.viewer_scene || bundle.has_viewer_scene) return '可打开';
  if (blenderPreviewImageInfo(bundle)?.url) return '有预览图';
  if (bundle.state?.blender_scene || bundle.has_scene_state) return '待导出';
  const missing = manifest.missing_required || [];
  if (missing.includes('viewer_scene')) return '待生成';
  return '准备中';
}

function setDocumentRunState(bundle, { status, manifest, viewerUrl, conceptPreview, previewImage }) {
  const root = document.documentElement;
  for (const className of Array.from(root.classList)) {
    if (className.startsWith('phase-')) root.classList.remove(className);
  }
  const phase = status.phase || bundle.state?.phase || bundle.summary?.phase || 'unknown';
  const phaseClass = `phase-${String(phase).toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;
  const plan = bundle.runtime_plan?.runtime_plan || null;
  const assets = assetProgressSummary(bundle, manifest);
  root.classList.add(phaseClass);
  root.classList.toggle('has-preview', Boolean(viewerUrl));
  root.classList.toggle('has-preview-image', !viewerUrl && Boolean(previewImage?.url));
  root.classList.toggle('has-concept-preview', !viewerUrl && !previewImage?.url && Boolean(conceptPreview?.url));
  root.classList.toggle('needs-user-action', Boolean(plan?.requires_user || status.status === 'needs_user_action'));
  root.classList.toggle('has-ready-assets', assets.ready > 0);
  root.classList.toggle('has-complete-assets', assets.ready === assets.total);
}

function assetProgressSummary(bundle, manifest) {
  const stateBody = bundle.state || {};
  const concept = stateBody.concept_bundle || {};
  const conceptImages = Object.values(concept.subject_concept_images || {}).flat();
  const files = manifest.files || [];
  const phase = bundle.frontend_status?.phase || stateBody.phase || bundle.summary?.phase;
  if (bundle.delivery_handoff?.ready || phase === 'DELIVERY') {
    return { ready: 6, total: 6 };
  }
  const imageCount = Math.max(state.uploads.length, (stateBody.input_images || []).length);
  const boundImageIds = new Set((stateBody.reference_bindings || []).map((binding) => binding.image_id));
  const inputImages = stateBody.input_images || [];
  const allImagesBound = imageCount === 0
    ? false
    : inputImages.every((image) => boundImageIds.has(image.image_id));
  const checks = [
    allImagesBound,
    Boolean(concept.final_preview_image_id || conceptImages.length),
    (stateBody.subject_assets || []).length > 0,
    Boolean(stateBody.scene_asset),
    Boolean(stateBody.blender_scene || files.some((file) => file.label === 'blend_file' && file.exists)),
    Boolean(stateBody.viewer_scene || files.some((file) => file.label === 'viewer_scene' && file.exists)),
  ];
  return {
    ready: checks.filter(Boolean).length,
    total: checks.length,
  };
}

function uploadBindingInfo(bundle, upload) {
  const imageId = upload.image_id;
  const stateBody = bundle?.state || {};
  const inputImage = (stateBody.input_images || []).find((image) => image.image_id === imageId);
  const binding = (stateBody.reference_bindings || []).find((item) => item.image_id === imageId);
  if (binding) {
    return {
      bound: true,
      label: `用途：${referenceTargetLabel(binding.target_type || binding.usage)}`,
    };
  }
  if (inputImage?.user_declared_label) {
    return {
      bound: true,
      label: `用途：${inputImage.user_declared_label}`,
    };
  }
  return {
    bound: false,
    label: imageId ? `用途待说明 · ${imageId}` : '用途待说明',
  };
}

function referenceTargetLabel(value) {
  return {
    subject: '主体参考',
    scene: '场景参考',
    style: '风格参考',
    pose: '姿态参考',
    texture: '材质参考',
    layout: '布局参考',
    subject_reference: '主体参考',
    scene_reference: '场景参考',
    style_reference: '风格参考',
    pose_reference: '姿态参考',
    texture_reference: '材质参考',
    layout_reference: '布局参考',
  }[value] || '参考图';
}

function hasBlendArtifact(bundle, manifest) {
  const stateBody = bundle.state || {};
  const files = manifest.files || [];
  return Boolean(
    stateBody.blender_scene?.blend_file_artifact_id
      || stateBody.blender_scene?.blend_file_uri
      || bundle.delivery_handoff?.blend_file_artifact_id
      || files.some((file) => file.label === 'blend_file' && file.exists),
  );
}

function deliveryPackageReady(bundle) {
  const files = bundle.file_manifest?.files || [];
  if (files.some((file) => file.exists && file.label === 'delivery_package')) return true;
  const web = bundle.web_surface || {};
  return Boolean(web.delivery_package_path || bundle.summary?.delivery_package_zip);
}

function deliveryPackageInfo(bundle) {
  const file = manifestFile(bundle, 'delivery_package');
  if (file?.url) {
    return { ready: true, url: file.url, waiting: '' };
  }
  if (deliveryPackageReady(bundle)) {
    return { ready: true, url: '', waiting: '交付包已生成，但缺少可打开链接' };
  }
  return { ready: false, url: '', waiting: '等待最终打包' };
}

function manifestFile(bundle, label) {
  return (bundle.file_manifest?.files || []).find((file) => file.label === label && file.exists && file.url) || null;
}

function handoffIssuesText(handoff) {
  const issues = handoff?.issues || [];
  if (!issues.length) return '等待完整交付文件';
  return `未就绪：${issues.map(issueLabel).join('、')}`;
}

function issueLabel(value) {
  return {
    missing_subject_assets: '缺少主体模型',
    missing_scene_assets: '缺少场景资产',
    missing_blend_file: '缺少 Blender 工程',
    missing_preview_render: '缺少预览图',
    missing_viewer_scene: '缺少 3D 预览模型',
    missing_scene_state: '缺少场景状态',
    missing_asset_url: '缺少模型链接',
    missing_viewer_url: '缺少预览链接',
  }[value] || humanizeIdentifier(value);
}

function conceptPreviewInfo(bundle) {
  const concept = bundle.state?.concept_bundle || null;
  if (!concept) return null;
  const artifactId = concept.final_preview_image_id
    || Object.values(concept.subject_concept_images || {}).flat()[0]
    || concept.scene_concept_image_ids?.[0]
    || null;
  if (!artifactId) return null;
  const artifact = (bundle.state?.artifacts || []).find((item) => item.artifact_id === artifactId);
  const url = artifact ? artifactFileUrl(bundle, artifact.uri) : null;
  if (!url) return null;
  return {
    artifactId,
    url,
    label: `概念图：${artifactId}`,
  };
}

function blenderPreviewImageInfo(bundle) {
  const artifact = (bundle.state?.artifacts || []).find((item) => {
    const type = item.artifact_type || '';
    const role = item.semantic_role || '';
    const uri = item.uri || '';
    return type === 'BLENDER_PREVIEW_RENDER'
      || role === 'blender_preview_render'
      || /preview.*\.(png|jpe?g|webp)$/i.test(uri)
      || /composed_preview\.(png|jpe?g|webp)$/i.test(uri);
  });
  if (!artifact) return null;
  const url = artifactFileUrl(bundle, artifact.uri);
  if (!url) return null;
  return {
    artifactId: artifact.artifact_id || artifact.uri,
    url,
    label: '场景预览图',
  };
}

function artifactFileUrl(bundle, uri) {
  const path = String(uri || '');
  if (!path) return null;
  const roots = [bundle.effective_run_dir, bundle.run_dir].filter(Boolean);
  for (const root of roots) {
    const prefix = `${root}/`;
    if (path.startsWith(prefix)) {
      const relPath = path.slice(prefix.length);
      const runKey = bundle.run_key || state.currentRunKey;
      return `/api/runs/${encodeURIComponent(runKey)}/file?path=${encodeURIComponent(relPath)}`;
    }
  }
  return null;
}

function viewerEmbedUrl(url) {
  if (!url) return '';
  try {
    const parsed = new URL(url, window.location.href);
    parsed.searchParams.set('embed', '1');
    parsed.searchParams.set('public', '1');
    parsed.searchParams.set('lang', 'zh-CN');
    return parsed.toString();
  } catch {
    const joiner = String(url).includes('?') ? '&' : '?';
    return `${url}${joiner}embed=1&public=1&lang=zh-CN`;
  }
}

function stageIndexForPhase(phase) {
  const index = STAGES.findIndex((stage) => stage.phases.includes(phase));
  if (phase === 'FAILED') return Math.max(0, STAGES.length - 1);
  return index >= 0 ? index : 0;
}

function jobKindLabel(value) {
  return {
    llm_node: '智能节点',
    domain_tool: '生成工具',
    user_gate: '用户确认',
    delivery: '交付',
    stop: '停止',
  }[value] || '';
}

function executorLabel(value) {
  return {
    main_runtime: '主运行器',
    background_worker: '后台任务',
    sub_agent: '子任务',
    user: '用户',
    external_service: '外部服务',
  }[value] || '';
}

function workerBackendLabel(value) {
  return {
    fixture: '本地结果适配器',
    codex_self_mcp: 'Codex 子任务',
    codex_self_log: 'Codex 图像日志',
  }[value] || '';
}

function userActionLabel(value) {
  return {
    approve_concept: '确认概念图',
    request_concept_changes: '要求修改概念图',
    approve_blender_preview: '确认预览',
    request_blender_changes: '要求调整预览',
  }[value] || '';
}

function stopReasonLabel(value) {
  return {
    completed_no_jobs: '没有剩余任务',
    waiting_user: '等待用户',
    delegated: '已交给子任务',
    blocked: '阻塞',
    failed: '失败',
    dry_run_needs_live_or_fixture: '需要真实输出或测试数据',
    max_steps: '达到步数上限',
  }[value] || statusLabel(value) || '';
}

function reasonLabel(value) {
  return {
    unbound_reference_images: '参考图用途未说明',
    scene_spec_open_questions: '场景规格还有问题待确认',
    build_initial_scene_spec: '整理初始场景规格',
    scene_spec_ready_for_concepts: '场景规格已就绪，准备概念图',
    concept_images_missing: '缺少概念图',
    concept_requires_user_approval: '概念图需要用户确认',
    missing_subject_assets: '缺少主体 3D 资产',
    create_or_register_scene_asset: '创建或登记场景资产',
    adapt_scene_asset_for_blender: '适配场景资产给工程',
    assets_ready_for_blender_assembly: '资产已就绪，准备场景装配',
    viewer_scene_missing: '缺少 3D 预览',
    preview_requires_user_approval: '预览需要用户确认',
    blender_preview_requires_user_approval: '等待确认预览效果',
  }[value] || '';
}

function workflowLabel(value) {
  return {
    'runtime-console': '运行控制台',
  }[value] || '运行控制台';
}

function roleLabel(value) {
  return {
    user: '用户',
    assistant: '助手',
    system: '系统',
  }[value] || '消息';
}

function fileLabel(value) {
  return FILE_LABELS[value] || humanizeIdentifier(value) || '';
}

function fileKindLabel(value) {
  return {
    json: '数据文件',
    jsonl: '运行日志',
    model: '模型',
  }[value] || '文件';
}

function objectTypeLabel(value) {
  return {
    EMPTY: '空对象',
    MESH: '网格',
    CAMERA: '相机',
    LIGHT: '灯光',
    object: '对象',
  }[value] || '对象';
}

function objectDisplayName(value) {
  const text = String(value || '');
  if (text === 'world') return '环境根节点';
  if (/hunyuan3d/i.test(text)) return '主体模型';
  const geometry = text.match(/^geometry[_-]?(\d+)$/i);
  if (geometry) return `场景网格 ${Number(geometry[1]) + 1}`;
  return humanizeIdentifier(text) || '场景内容';
}

function humanizeIdentifier(value) {
  if (!value) return '';
  const text = String(value);
  const normalized = text
    .replace(/^workflow_runner\./, '')
    .replace(/_/g, ' ')
    .replace(/-/g, ' ')
    .trim();
  const map = {
    'viewer check': '检查预览',
    'export viewer': '导出预览',
    compose: '装配场景',
    'main runtime': '主运行器',
    'background worker': '后台任务',
    fixture: '测试数据',
    world: '环境根节点',
  };
  return map[normalized] || normalized;
}

function runNameLabel(value) {
  const raw = String(value || '').replace(/\s+\/\s+/g, '/');
  const normalized = raw
    .replace(/^runtime_/, '')
    .replace(/_?\d{8}T\d{6}Z?$/i, '')
    .replace(/_?smoke_?\d{8}T?\d*Z?$/i, '')
    .replace(/_/g, ' ')
    .replace(/-/g, ' ')
    .trim();
  const joined = normalized.replace(/\s+/g, ' ');
  const map = {
    'scene spec assembly non dryrun': '场景装配预览',
    'blender socket edit refresh scratch': '最新场景编辑预览',
    'blender assembly plan smoke': '装配计划试跑',
    'codex self robot concept': '机器人概念场景',
    'p0 real demo': '真实链路演示',
    'blender viewer': '场景预览',
    'blender preview feedback': '预览修改试跑',
    'blender preview approve': '预览确认试跑',
    'user gate feedback': '用户反馈试跑',
    'user gate approve': '用户确认试跑',
    'worker codex log': '子任务回灌试跑',
    'worker codex self live concept': '真实概念图生成',
    'worker codex self live concept 20260629T115755Z': '真实概念图生成',
    'worker codex self live concept 20260629T115619Z': '概念图生成失败记录',
    'worker codex log concept': '概念图日志回灌',
    'worker codex self live concept': '真实链路场景验收',
    'runtime worker codex self live concept': '真实链路场景验收',
    'codex self execute text': 'Codex 子任务文本试跑',
    'codex self status plan': 'Codex 子任务状态试跑',
    'worker codex guard': '子任务保护试跑',
    'worker http audit': '子任务接口试跑',
    'loop http audit': '循环接口试跑',
    'full asset live router edit dfce104f': '最新 3D 场景验收',
    'full asset live router edit': '最新 3D 场景验收',
    'console usergate': '用户确认控制台',
    'console step': '单步控制台',
    'console plan': '计划控制台',
    'console': '控制台运行',
  };
  if (map[joined]) return map[joined];
  if (/full asset live router edit/i.test(joined)) return '最新 3D 场景验收';
  if (/live router edit/i.test(joined)) return '3D 场景编辑验收';
  if (/^(runtime|worker|loop|console|handoff|apply|codex self|blender|scene asset|subject asset)\b/.test(joined)) {
    return '生成任务记录';
  }
  if (!DEV_MODE && /\b(llm|qwen|deepseek|mcp|node|http|audit|dry|dryrun|smoke|fixture|handoff|apply|worker|runtime|loop|console|codex|blender)\b/i.test(joined)) {
    return '生成任务记录';
  }
  if (/^\d+$/.test(joined)) return `运行 ${joined}`;
  return humanizeIdentifier(joined).replace(/\bglb\b/gi, '3D模型').replace(/\bblend\b/gi, '工程文件') || '未命名创作';
}

function shortPath(value) {
  const text = String(value || '');
  const parts = text.split('/');
  if (parts.length <= 3) return text;
  return parts.slice(-3).join('/');
}

function friendlyError(value) {
  const text = String(value || '');
  if (text.startsWith('Request failed')) return text.replace('Request failed', '请求失败');
  if (text.startsWith('Upload failed')) return text.replace('Upload failed', '上传失败');
  if (text.includes('not found')) return text.replace('not found', '未找到');
  return text;
}

function formatTime(value) {
  if (!value) return '';
  return String(value).replace('T', ' ').replace('+00:00', '').replace('Z', '');
}

els.chatForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (!state.currentRunKey) return;
  const text = els.chatInput.value.trim();
  if (!text) return;
  clearComposerNotice();
  await api(`/api/runs/${encodeURIComponent(state.currentRunKey)}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ role: 'user', text }),
  });
  els.chatInput.value = '';
  await refreshChat();
  await buildPlan({ silent: true });
  state.bundle = await api(`/api/runs/${encodeURIComponent(state.currentRunKey)}`);
  renderBundle();
});

els.uploadForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (!state.currentRunKey || !els.uploadInput.files.length) return;
  clearComposerNotice();
  const body = new FormData();
  body.append('file', els.uploadInput.files[0]);
  const upload = await fetch(`/api/runs/${encodeURIComponent(state.currentRunKey)}/upload`, {
    method: 'POST',
    body,
  }).then(async (res) => {
    const payload = await res.json();
    if (!res.ok) throw new Error(friendlyError(payload.error || `Upload failed: ${res.status}`));
    return payload;
  });
  await api(`/api/runs/${encodeURIComponent(state.currentRunKey)}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      role: 'user',
      text: `已上传参考图：${upload.filename}`,
      attachment_ids: upload.image_id ? [upload.image_id] : [],
      metadata: { upload_id: upload.upload_id },
    }),
  });
  els.uploadInput.value = '';
  if (els.uploadFileHint) els.uploadFileHint.textContent = '支持图片文件';
  state.bundle = await api(`/api/runs/${encodeURIComponent(state.currentRunKey)}`);
  state.uploads = await api(`/api/runs/${encodeURIComponent(state.currentRunKey)}/uploads`);
  await buildPlan({ silent: true });
  state.bundle = await api(`/api/runs/${encodeURIComponent(state.currentRunKey)}`);
  renderBundle();
  await refreshChat();
});

els.uploadInput?.addEventListener('change', () => {
  if (!els.uploadFileHint) return;
  const file = els.uploadInput.files?.[0];
  els.uploadFileHint.textContent = file ? file.name : '支持图片文件';
});

els.viewerFrame?.addEventListener('load', handleViewerFrameLoaded);
window.addEventListener('message', handleViewerObjectSelectedMessage);

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  })[char]);
}

function escapeAttr(value) {
  return escapeHtml(value).replace(/`/g, '&#96;');
}

refreshRuns(true).catch((error) => {
  els.runSubtitle.textContent = friendlyError(error.message);
});
