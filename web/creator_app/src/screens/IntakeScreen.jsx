import { useLayoutEffect, useMemo, useRef, useState } from 'react';
import { ScreenHeading } from '../components/ScreenHeading.jsx';
import { Composer } from '../components/Composer.jsx';
import { Button } from '../components/Button.jsx';
import { ReferenceTray } from '../components/ReferenceTray.jsx';

export function IntakeScreen({ viewModel, onStartGeneration, onUploadReference, onSendRuntimeChat }) {
  const { referenceSlots, intake } = viewModel;
  const [submittedTurns, setSubmittedTurns] = useState([]);
  const [pendingAttachmentIds, setPendingAttachmentIds] = useState([]);
  const conversationScrollRef = useRef(null);
  const uploadedSubjectSlots = useMemo(
    () => referenceSlots.filter((slot) => slot.slot_kind === 'subject' && slot.status === 'uploaded'),
    [referenceSlots],
  );
  const uploadedSceneSlots = useMemo(
    () => referenceSlots.filter((slot) => slot.slot_kind === 'scene' && slot.status === 'uploaded'),
    [referenceSlots],
  );
  const activeMentions = useMemo(
    () => [...uploadedSubjectSlots, ...uploadedSceneSlots].map((slot) => slot.mention),
    [uploadedSubjectSlots, uploadedSceneSlots],
  );
  const backendTurns = intake?.userTurns || [];
  const taskTitle = taskTitleForPhase(viewModel.phase);
  const taskText = taskTextForPhase(viewModel.phase, intake);
  const conversationTurns = useMemo(() => [
    {
      id: 'assistant-intake',
      role: 'assistant',
      label: 'image23D Agent',
      meta: viewModel.publicPhaseLabel || '项目上下文',
      text: `当前项目「${viewModel.project.title}」已加载后端上下文：${intake?.subjectNames?.length || uploadedSubjectSlots.length} 个主体，${intake?.environment ? '1 个场景' : `${uploadedSceneSlots.length} 个场景参考`}。`,
      tags: [
        `${uploadedSubjectSlots.length}/5 主体参考`,
        `${uploadedSceneSlots.length}/1 场景参考`,
        ...(intake?.styleKeywords?.slice(0, 2) || []),
      ],
    },
    {
      id: 'backend-task',
      role: 'backend',
      label: 'Runtime',
      meta: '后端任务状态',
      title: taskTitle,
      text: taskText,
      tags: [viewModel.phase || 'runtime', viewModel.runtime?.status || '等待后端状态'],
      compact: true,
    },
    ...backendTurns.map((turn) => ({
      ...turn,
      mentions: turn.mentions?.length > 0 ? turn.mentions : activeMentionsForTurn(turn, activeMentions),
    })),
    ...submittedTurns,
  ], [
    activeMentions,
    backendTurns,
    intake,
    submittedTurns,
    taskText,
    taskTitle,
    uploadedSceneSlots.length,
    uploadedSubjectSlots.length,
    viewModel.phase,
    viewModel.project.title,
    viewModel.publicPhaseLabel,
    viewModel.runtime?.status,
  ]);

  useLayoutEffect(() => {
    const scrollNode = conversationScrollRef.current;
    if (!scrollNode) return;
    scrollNode.scrollTop = scrollNode.scrollHeight;
  }, [conversationTurns.length]);

  async function handleSend(payload) {
    const mentionedTokens = payload.reference_mentions?.map((mention) => mention.mention) ?? [];
    const attachmentIds = [...pendingAttachmentIds];
    setSubmittedTurns((current) => [
      ...current,
      {
        id: `user-${Date.now()}`,
        role: 'user',
        label: '用户',
        meta: '追加消息',
        text: payload.message,
        mentions: mentionedTokens,
        tags: attachmentIds.length > 0 ? [`附件 ${attachmentIds.length} 个`] : undefined,
      },
      {
        id: `backend-${Date.now()}`,
        role: 'backend',
        label: 'Runtime',
        meta: '已接收',
        title: '已把追加消息写入本轮需求上下文',
        text: '后台会把这条对话、右侧资源槽和显式 @ 引用一起交给概念生成任务。',
        tags: [...mentionedTokens, ...attachmentIds].length > 0 ? [...mentionedTokens, ...attachmentIds] : ['无新增引用'],
      },
    ]);
    setPendingAttachmentIds([]);
    await onSendRuntimeChat?.({
      ...payload,
      attachment_ids: attachmentIds,
    });
    onStartGeneration?.('concept', {
      source: 'chat',
      message: payload.message,
      reference_mentions: payload.reference_mentions,
      attachment_ids: attachmentIds,
    });
  }

  async function handleComposerUpload(file) {
    const fallbackSlot = referenceSlots.find((slot) => slot.slot_kind === 'subject' && slot.status !== 'uploaded')
      || referenceSlots.find((slot) => slot.slot_kind === 'scene' && slot.status !== 'uploaded')
      || referenceSlots.find((slot) => slot.slot_kind === 'subject')
      || referenceSlots[0];
    const result = await onUploadReference?.({ file, slot: fallbackSlot });
    if (result?.image_id) {
      setPendingAttachmentIds((current) => [...current, result.image_id]);
    }
  }

  return (
    <>
      <ScreenHeading title="输入创作需求" subtitle="把对话、主体槽和场景槽一起整理成可执行的概念生成任务" />
      <div className="intake-layout intake-layout--studio">
        <section className="intake-command-panel intake-chat-workbench">
          <div className="intake-command-panel__header">
            <div>
              <span className="eyebrow">LLM Chat Workspace</span>
              <h2>创作对话</h2>
            </div>
            <div className="intake-command-panel__badges">
              <span>最多 5 主体</span>
              <span>1 个场景槽</span>
              <span>@ 精准引用</span>
            </div>
          </div>

          <div className="conversation-window" aria-label="创作需求对话">
            <div className="conversation-window__topline">
              <span>历史对话</span>
              <strong>{conversationTurns.length} 条上下文</strong>
            </div>
            <div className="conversation-scroll" ref={conversationScrollRef}>
              {conversationTurns.map((turn) => (
                <article key={turn.id} className={`chat-turn chat-turn--${turn.role} ${turn.compact ? 'chat-turn--compact' : ''}`}>
                  <header>
                    <strong>{turn.label}</strong>
                    <span>{turn.meta}</span>
                  </header>
                  {turn.title && <h3>{turn.title}</h3>}
                  <p>{turn.text}</p>
                  {turn.mentions?.length > 0 && (
                    <div className="chat-token-row">
                      {turn.mentions.map((mention) => <span key={mention}>{mention}</span>)}
                    </div>
                  )}
                  {turn.tags?.length > 0 && (
                    <div className="chat-meta-row">
                      {turn.tags.map((tag) => <span key={tag}>{tag}</span>)}
                    </div>
                  )}
                </article>
              ))}
            </div>
          </div>

          <Composer
            className="composer--chat"
            referenceSlots={referenceSlots}
            placeholder="输入这次的新信息，或点击 @ 引用主体/场景..."
            onSend={handleSend}
            onUpload={handleComposerUpload}
          />

          <div className="generation-launch-strip">
            <div>
              <strong>生成任务</strong>
              <span>{taskText}</span>
            </div>
            <Button variant="primary" className="big-action" onClick={() => onStartGeneration?.('concept')}>
              {viewModel.source === 'backend' ? '提交当前上下文' : '开始生成概念图'}
            </Button>
          </div>
        </section>
        <ReferenceTray referenceSlots={referenceSlots} onUploadReference={onUploadReference} />
      </div>
    </>
  );
}

function taskTitleForPhase(phase) {
  if (phase === 'SUBJECT_ASSET_GENERATION' || phase === 'SCENE_ASSET_GENERATION') return '当前任务：生成主体/场景模型';
  if (phase === 'CONCEPT_REVIEW' || phase === 'CONCEPT_APPROVED') return '当前任务：确认概念组合';
  if (phase === 'BLENDER_ASSEMBLY_EXECUTION') return '当前任务：组装 Blender 场景';
  return '建议任务：整理需求并生成概念图';
}

function taskTextForPhase(phase, intake) {
  if (phase === 'SUBJECT_ASSET_GENERATION' || phase === 'SCENE_ASSET_GENERATION') {
    return '概念组合已经确认，后端正在生成主体和场景资产；你仍可以追加对话或上传参考图进入下一轮反馈。';
  }
  if (phase === 'CONCEPT_REVIEW' || phase === 'CONCEPT_APPROVED') {
    return '后端已经产出概念候选；本页对话、资源槽和显式 @ 引用会继续作为后续反馈上下文。';
  }
  if (intake?.conversationSummary) return intake.conversationSummary;
  return '当前对话会作为本轮概念图生成上下文；启动后仍停留在本页显示后台进度。';
}

function activeMentionsForTurn(turn, activeMentions) {
  if (turn.attachmentIds?.length > 0) return [];
  return turn.id === 'scene-spec-fallback' ? activeMentions : [];
}
