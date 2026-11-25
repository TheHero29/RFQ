export const triggerLabels = {
  bid_received: 'Bid received',
  rank_change: 'Supplier rank change',
  l1_change: 'Lowest bidder (L1) change',
};
export const money = (cents, currency = 'INR') => cents === null ? 'No bids yet' :
  new Intl.NumberFormat(undefined, { style: 'currency', currency }).format(cents / 100);
export const dateTime = value => new Date(value).toLocaleString(undefined,
  { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
export const serviceDate = value => new Date(`${value}T12:00:00`).toLocaleDateString();
export const localInput = date => new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);

export function countdown(value, now) {
  const seconds = Math.ceil((new Date(value).getTime() - now) / 1000);
  if (seconds <= 0) return 'Bidding ended';
  const minutes = Math.floor(seconds / 60);
  return minutes >= 60 ? `${Math.floor(minutes / 60)}h ${minutes % 60}m remaining` :
    `${minutes}m ${seconds % 60}s remaining`;
}
