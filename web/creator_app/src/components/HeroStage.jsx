import { useState } from 'react';

export function HeroStage({ image, title, caption, children, className = '' }) {
  const [fitMode, setFitMode] = useState('fit');
  const [detailOpen, setDetailOpen] = useState(false);
  const modeClass = fitMode === 'fill' ? 'hero-stage--fill' : 'hero-stage--fit';
  return (
    <>
      <section
        className={`hero-stage ${modeClass} ${className}`.trim()}
        style={image ? { background: `url("${image}") center center / cover no-repeat` } : undefined}
      >
        {image && (
          <div
            className="hero-stage__backdrop"
            style={{ backgroundImage: `url("${image}")` }}
            aria-hidden="true"
          />
        )}
        {image && <img className="hero-stage__image" src={image} alt={title || caption || 'preview'} />}
        {image && (
          <div className="hero-stage__controls">
            <button type="button" className={fitMode === 'fit' ? 'is-active' : ''} onClick={() => setFitMode('fit')}>适配</button>
            <button type="button" className={fitMode === 'fill' ? 'is-active' : ''} onClick={() => setFitMode('fill')}>填充</button>
            <button type="button" onClick={() => setDetailOpen(true)}>原图</button>
          </div>
        )}
        {caption && <div className="hero-stage__caption">“ {caption} ”</div>}
        {children}
      </section>
      {detailOpen && image && (
        <div className="hero-image-modal" role="dialog" aria-modal="true" aria-label={title || '原图查看'}>
          <div className="hero-image-modal__bar">
            <strong>{title || '原图'}</strong>
            <button type="button" onClick={() => setDetailOpen(false)}>关闭</button>
          </div>
          <div className="hero-image-modal__viewport">
            <img src={image} alt={title || caption || 'preview'} />
          </div>
        </div>
      )}
    </>
  );
}
