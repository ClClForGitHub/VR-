import { useState } from 'react';
import { AssetMemoryPanel } from '../components/AssetMemoryPanel.jsx';
import { ConceptSelectionBoard } from '../components/ConceptSelectionBoard.jsx';
import { FeedbackDrawer } from '../components/FeedbackDrawer.jsx';
import { Panel } from '../components/Panel.jsx';
import { ScreenHeading } from '../components/ScreenHeading.jsx';
import { Button } from '../components/Button.jsx';
import { VersionCompareModal } from '../components/VersionCompareModal.jsx';

export function ConceptReviewScreen({ onNavigate, viewModel, onStartGeneration }) {
  const { concepts, references, entities, assetVersions, approvedConceptSelection, referenceSlots } = viewModel;
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [compareOpen, setCompareOpen] = useState(false);
  const [activeSelection, setActiveSelection] = useState(null);

  function openFeedback(selection) {
    setActiveSelection(selection);
    setFeedbackOpen(true);
  }

  function openCompare(selection) {
    setActiveSelection(selection);
    setCompareOpen(true);
  }

  return (
    <>
      <ScreenHeading title="概念选择审稿" subtitle="整体图、主体图、场景图可以混选；同意后进入模型生成，不同意时打开反馈抽屉" />
      <div className="concept-review-shell">
        <ConceptSelectionBoard
          entities={entities}
          assetVersions={assetVersions}
          approvedSelection={approvedConceptSelection}
          onApprove={(selection) => {
            setActiveSelection(selection);
            onStartGeneration?.('model');
          }}
          onFeedback={openFeedback}
          onConfirmSelection={openCompare}
        />
        <aside className="stack concept-memory-column">
          <AssetMemoryPanel viewModel={viewModel} onOpen={() => onNavigate('asset-memory')} />
          <Panel title="快捷审稿标签">
            <div className="tag-row">
              {['保留整体', '重做主体', '替换场景', '强化光影', '优化构图'].map((tag) => <Button key={tag} variant="chip">{tag}</Button>)}
            </div>
          </Panel>
        </aside>
      </div>
      <FeedbackDrawer
        open={feedbackOpen}
        selection={activeSelection}
        entities={entities}
        referenceSlots={referenceSlots}
        references={references}
        onClose={() => setFeedbackOpen(false)}
        onOpenCompare={() => setCompareOpen(true)}
        onRegenerate={() => {
          setFeedbackOpen(false);
          onStartGeneration?.('concept-feedback');
        }}
      />
      <VersionCompareModal
        open={compareOpen}
        concepts={concepts}
        entities={entities}
        assetVersions={assetVersions}
        selection={activeSelection}
        onClose={() => setCompareOpen(false)}
      />
    </>
  );
}
