export function HeroStage({ image, title, caption, children, className = '' }) {
  return (
    <section
      className={`hero-stage ${className}`.trim()}
      style={image ? { background: `url("${image}") center center / cover no-repeat` } : undefined}
    >
      {image && (
        <div
          className="hero-stage__backdrop"
          style={{ backgroundImage: `url("${image}")` }}
          aria-hidden="true"
        />
      )}
      <img className="hero-stage__image" src={image} alt={title || caption || 'preview'} />
      {caption && <div className="hero-stage__caption">“ {caption} ”</div>}
      {children}
    </section>
  );
}
