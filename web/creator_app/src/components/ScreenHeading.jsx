export function ScreenHeading({ title, subtitle }) {
  return (
    <header className="screen-heading">
      <h1>✦ {title} ✦</h1>
      {subtitle && <p>{subtitle}</p>}
    </header>
  );
}
