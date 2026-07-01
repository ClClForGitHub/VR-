export function HeroStage({ image, title, caption, children, className = '' }) {
  return (
    <section className={`hero-stage ${className}`.trim()}>
      <img className="hero-stage__image" src={image} alt={title || caption || 'preview'} />
      {caption && <div className="hero-stage__caption">“ {caption} ”</div>}
      {children}
    </section>
  );
}
