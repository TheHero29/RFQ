import React from 'react';

export function Status({ value }) {
  return <span className={`status ${value.toLowerCase().replaceAll(' ', '-')}`}>{value}</span>;
}
export function Empty({ title, children }) {
  return <div className="empty"><strong>{title}</strong>{children}</div>;
}
export function Stats({ items }) {
  return <div className="stats">{items.map(([label, value, caption]) =>
    <div className="stat" key={label}><span className="stat-label">{label}</span>
      <strong>{value}</strong><small>{caption}</small></div>)}</div>;
}
