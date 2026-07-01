import { Button } from './Button.jsx';

export function ReviewDock({ negativeLabel = '提出修改意见', positiveLabel = '接受并进入下一步', onNegative, onPositive }) {
  return (
    <div className="review-dock">
      <Button onClick={onNegative}>{negativeLabel}</Button>
      <Button variant="primary" onClick={onPositive}>{positiveLabel} →</Button>
    </div>
  );
}
