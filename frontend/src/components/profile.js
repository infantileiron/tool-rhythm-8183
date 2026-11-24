import {band, number, pct} from '../utils/format.js';

export function profileChart(profile, bands, peak) {
  // 组画像中 null 表示该时段不是各站共同开放时段，不参与峰段判定，只画占位行。
  return `<div class="profile" aria-label="分组时段画像（按共同开放时段）">${bands.map((range, index) => {
    const value = profile[index];
    return `
      <div class="profile-row ${peak === index ? 'peak' : ''} ${value === null ? 'muted-band' : ''}">
        <span>${band(range)}</span><div class="track">${value === null ? '<i class="closed-mark"></i>' : `<i style="width:${pct(value)}"></i>`}</div>
        <strong>${value === null ? '非共同开放' : pct(value)}</strong>
      </div>`;
  }).join('')}</div>`;
}

export function vectorSummary(member) {
  // 分时件数（剔除闭站冲突件数后），括注每开放小时件数与闭站剔除情况。
  const profile = member.profile ?? member.counts.map(() => null);
  const rateText = profile
    .map(v => (v === null ? '—' : number(Number(v.toFixed(2)))))
    .map(text => `<span>${text}</span>`)
    .join('');
  const closedHours = member.closed_total_hours ?? 0;
  const conflicts = member.conflict_returns ?? 0;
  return `<span class="vector" aria-label="六个时段开放时段归还件数">${member.counts.map(n => `<span>${number(n)}</span>`).join('')}</span>` +
    `<small class="rate-note">每开放小时：${rateText}</small>` +
    (closedHours ? `<small class="closure-note">闭站 ${number(closedHours)} 小时剔除${conflicts ? `，冲突凭据 ${number(conflicts)} 件保留` : ''}</small>` : '');
}
