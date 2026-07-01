import { Button } from './Button.jsx';
import { ModelViewerStage } from './ModelViewerStage.jsx';

export function ModelCompareModal({ open, model, concept, entity, onClose, onFeedback }) {
  if (!open) return null;
  return (
    <div className="version-modal" role="dialog" aria-modal="true" aria-label="概念图与模型对比">
      <div className="version-modal__panel model-compare-modal">
        <header>
          <div>
            <span className="eyebrow">Concept / Model Compare</span>
            <h2>{entity?.display_label || '模型'} 对比</h2>
          </div>
          <Button variant="icon" onClick={onClose}>×</Button>
        </header>
        <div className="model-compare-grid">
          <section>
            <h3>对应概念图</h3>
            {concept?.image_url ? <img src={concept.image_url} alt={concept.title} /> : <div className="empty-state">暂无对应概念图</div>}
            <p>{concept?.title}</p>
          </section>
          <section>
            <h3>当前模型版本</h3>
            <ModelViewerStage
              src={model?.glb_url}
              poster={model?.image_url}
              title={model?.title}
              fallbackLabel={`等待 ${entity?.display_label || '模型'} ${model?.version_label || ''} GLB 生成`}
            />
          </section>
        </div>
        <div className="split-actions">
          <Button onClick={onClose}>返回检查</Button>
          <Button variant="primary" onClick={onFeedback}>提出模型反馈</Button>
        </div>
      </div>
    </div>
  );
}
