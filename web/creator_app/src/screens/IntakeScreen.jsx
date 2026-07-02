import { useLayoutEffect, useMemo, useRef, useState } from 'react';
import { ScreenHeading } from '../components/ScreenHeading.jsx';
import { Composer } from '../components/Composer.jsx';
import { Button } from '../components/Button.jsx';
import { ReferenceTray } from '../components/ReferenceTray.jsx';

const initialUserPrompt = '创建一个古老遗迹中的机械巨兽守护者，场景在日落时分，光线穿透破损的拱门，地面有反射水洼，氛围史诗、神秘、宏大。';

export function IntakeScreen({ viewModel, onStartGeneration, onUploadReference, onSendRuntimeChat }) {
  const { referenceSlots } = viewModel;
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
  const conversationTurns = useMemo(() => [
    {
      id: 'assistant-intake',
      role: 'assistant',
      label: 'image23D Agent',
      meta: '初始需求整理',
      text: `我已经进入输入/绑定阶段。右侧资源库会作为本轮对话上下文：已绑定 ${uploadedSubjectSlots.length} 个主体参考和 ${uploadedSceneSlots.length} 个场景参考。`,
      tags: ['等待用户确认', '可继续补充描述', '@ 可插入语义引用'],
    },
    {
      id: 'backend-task',
      role: 'backend',
      label: 'Runtime',
      meta: '后端任务提示',
      title: '建议任务：生成第一轮概念图',
      text: '当前信息足够形成 ConceptPromptPack；提交后在本页显示后台进度，完成后弹出揭幕 Overlay。',
      tags: ['concept_generation', '95%-99% 等待后端完成'],
      compact: true,
    },
    {
      id: 'user-initial',
      role: 'user',
      label: '用户',
      meta: '本轮新信息',
      text: initialUserPrompt,
      mentions: activeMentions,
    },
    ...submittedTurns,
  ], [activeMentions, submittedTurns, uploadedSceneSlots.length, uploadedSubjectSlots.length]);

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
              <span>当前对话会作为本轮概念图生成上下文；启动后仍停留在本页显示后台进度。</span>
            </div>
            <Button variant="primary" className="big-action" onClick={() => onStartGeneration?.('concept')}>
              开始生成概念图
            </Button>
          </div>
        </section>
        <ReferenceTray referenceSlots={referenceSlots} onUploadReference={onUploadReference} />
      </div>
    </>
  );
}
