import { Button } from './Button.jsx';

export function Composer({ placeholder = '描述你的想法，或通过 @ 引用参考图...', compact = false }) {
  return (
    <div className={`composer ${compact ? 'composer--compact' : ''}`}>
      <textarea placeholder={placeholder} />
      <Button variant="chip">@ 图片1</Button>
      <Button variant="chip">+ 参考</Button>
      <button className="send-button" aria-label="发送">↗</button>
    </div>
  );
}
