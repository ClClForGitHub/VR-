import { useState } from 'react';
import { ConceptSelectionBoard } from '../components/ConceptSelectionBoard.jsx';
import { FeedbackDrawer } from '../components/FeedbackDrawer.jsx';
import { ScreenHeading } from '../components/ScreenHeading.jsx';
import { VersionCompareModal } from '../components/VersionCompareModal.jsx';

export function ConceptReviewScreen({ viewModel, onStartGeneration }) {
  const { concepts, entities, assetVersions, approvedConceptSelection, referenceSlots } = viewModel;
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
      </div>
      <FeedbackDrawer
        open={feedbackOpen}
        mode="concept"
        selection={activeSelection}
        entities={entities}
        assetVersions={assetVersions}
        referenceSlots={referenceSlots}
        onClose={() => setFeedbackOpen(false)}
        onOpenCompare={() => setCompareOpen(true)}
        onSubmit={() => {
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
