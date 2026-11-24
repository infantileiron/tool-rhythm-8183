import {api} from '../api/client.js';
import {badge, blank, heading, table} from '../components/common/board.js';
import {profileChart, vectorSummary} from '../components/profile.js';
import {demoPeriod, exceptionNotes, groupingBasis, runLabels, stationLabels} from '../constants/domain.js';
import {bindForm} from '../hooks/forms.js';
import {pollWhile} from '../hooks/poll.js';
import {go} from '../router/routes.js';
import {workbench} from '../stores/workbench.js';
import {isProcessing} from '../types/run.js';
import {band, esc, localDateTime, number} from '../utils/format.js';

export async function analysisPage(container, id) {
  if (id) return analysisDetail(container, id);
  const canRun = workbench.user.role === 'analyst';
  workbench.runs = await api.runs();
  container.innerHTML = `${heading('密度分型', '按每开放小时的归还节律寻找相近工具站；闭站时段的件数与小时同时剔除。')}
    <div class="analysis-layout">
      <section class="panel config"><div class="panel-heading"><div><span class="eyebrow">余弦距离 / DBSCAN · 开放小时口径</span><h2>分型参数</h2></div></div>
      ${canRun ? `<form id="run-form">
        <label>方案名称<input name="title" value="11 月第二周 · 归还节律" minlength="2" maxlength="80" required></label>
        <div class="field-grid two"><label>窗口起日<input name="start" type="date" value="${demoPeriod.start}" required></label>
        <label>窗口止日<input name="end" type="date" value="${demoPeriod.end}" required></label></div>
        <fieldset><legend>密度门槛</legend><div class="field-grid three">
          <label>邻域半径 ε<input name="eps" type="number" min="0" max="1" step="any" value="0.035" required></label>
          <label>最少邻居数<input name="min_points" type="number" min="2" max="20" value="3" required></label>
          <label>最少归还件数<input name="min_returns" type="number" min="1" max="9999" value="30" required></label></div>
          <p>邻居数含本站，仅统计共同开放时段上的距离。低于件数门槛的站点留待单独复核。</p></fieldset>
        <div class="form-hint basis-hint"><strong>分组口径</strong><p>${esc(groupingBasis.grouped)}</p><p>${esc(groupingBasis.ungrouped)}</p><p>${esc(groupingBasis.closure)}</p></div>
        <p class="error" role="alert"></p><button type="submit" class="primary">创建版本并计算 <span aria-hidden="true">→</span></button>
      </form>` : blank('参数由分析员提交', '打开右侧方案可查阅当前角色有权查看的版本。')}
      </section>
      <section class="panel"><div class="panel-heading"><div><span class="eyebrow">版本记录</span><h2>分型方案</h2></div></div>
        ${workbench.runs.length ? `<ul class="version-list">${workbench.runs.map(run => `
          <li><a href="#analysis/${run.id}"><span><small class="mono">V${run.id} · ${localDateTime(run.created_at)}</small><strong>${esc(run.title)}</strong></span>${badge(runLabels[run.status], run.status)}</a></li>`).join('')}</ul>` :
          blank('尚无可查阅版本', '计算将保存当时的站点向量与闭站登记，可在结果中核对输入指纹。')}
      </section>
    </div>`;
  if (canRun) bindForm(container.querySelector('#run-form'), async data => {
    const {id: runId} = await api.createRun({...data, eps: Number(data.eps), min_points: Number(data.min_points), min_returns: Number(data.min_returns)});
    go('analysis', runId);
  });
}

async function analysisDetail(container, id) {
  if (!/^\d+$/.test(id)) throw new Error('方案版本号无效');
  const run = await api.run(id);
  const render = data => {
    const {snapshot, result, status} = data;
    const {params, bands} = snapshot;
    const dutyLink = (status === 'published' || (status === 'ready' && workbench.user.role === 'admin'))
      ? `<a class="primary" href="#duty/${id}">${status === 'published' ? '查看值班单' : '进入值守复核'} →</a>` : '';
    container.innerHTML = `<a class="back" href="#analysis">← 分型方案</a>
      ${heading(data.title, `${params.start} 至 ${params.end} · ${runLabels[status]}`, dutyLink)}
      <div class="run-strip"><div><span>方案版本</span><strong>V${data.id}</strong></div>
        <div><span>半径 / 最少邻居</span><strong>${params.eps} / ${params.min_points}</strong></div>
        <div><span>纳入门槛</span><strong>${params.min_returns} 件（开放时段）</strong></div>
        <div><span>闭站登记</span><strong>${result ? number(result.diagnostics.closures ?? 0) : '—'} 段</strong></div>
        <div><span>输入指纹</span><strong class="mono" title="${esc(data.checksum)}">${data.checksum.slice(0, 12)}</strong></div></div>
      ${result ? resultBoard(result, bands, snapshot) : `<section class="panel">${blank(runLabels[status], isProcessing(data) ? '后台正在处理该版本。结果就绪后会自动显示。' : data.failure)}
        <p class="error poll-error" data-poll-error role="alert"></p></section>`}`;
  };
  render(run);
  if (isProcessing(run)) pollWhile(container, async () => {
    const next = await api.run(id);
    if (container.isConnected) render(next);
    return isProcessing(next);
  });
}

function resultBoard(result, bands, snapshot) {
  const {groups, members, diagnostics} = result;
  const exceptions = members.filter(m => m.status in exceptionNotes);
  return `<section class="panel basis-panel"><div class="panel-heading"><div><span class="eyebrow">分组与暂不分组的依据</span><h2>口径说明</h2></div></div>
      <ul class="basis-list">
        <li><strong>可以分组：</strong>${esc(groupingBasis.grouped)}</li>
        <li><strong>暂不分组：</strong>${esc(groupingBasis.ungrouped)}</li>
        <li><strong>闭站处理：</strong>${esc(groupingBasis.closure)}</li>
      </ul>
      <p class="basis-foot">本版本窗口 ${number(snapshot.window_days ?? 0)} 天，闭站登记 ${number(diagnostics.closures ?? 0)} 段，
      闭站冲突凭据 ${number(diagnostics.conflict_returns ?? 0)} 件（保留原记录、不参与节律）；开放时段归还合计 ${number(diagnostics.returns)} 件。</p>
    </section>
    <section class="results-section"><div class="result-heading"><div><h2>分组画像</h2><p>每个站点先换算成每开放小时归还件数，组画像只在各站共同开放时段上等权平均。</p></div>
      <div class="result-summary"><strong>${groups.length} 组</strong><span>${diagnostics.eligible} / ${diagnostics.stations} 站参与 · ${number(diagnostics.returns)} 件开放时段归还</span></div></div>
    ${groups.length ? `<div class="profile-grid">${groups.map(group => `<article class="panel group-panel">
      <div class="group-title"><span class="letterpress">${group.key}</span><div><span class="eyebrow">主要归还时段（共同开放）</span><h3>${band(bands[group.peak])}</h3></div></div>
      ${profileChart(group.profile, bands, group.peak)}
      <p class="cohort">${group.station_codes.length} 站 · ${number(group.returns)} 件 · ${group.station_codes.join(' / ')}</p>
      <p class="common-bands">${group.common_bands ? `共同开放时段：${group.common_bands.map(i => band(bands[i])).join('、')}` : '共同开放时段：按全时段比较（历史版本）'}${group.conflict_returns ? ` · 闭站冲突凭据 ${number(group.conflict_returns)} 件` : ''}</p>
      <p class="group-advice">${esc(group.advice)}</p></article>`).join('')}</div>` :
      `<div class="panel">${blank('该版本未形成分组', '请复核逐站诊断，再判断是否扩大日期窗口或调整密度门槛。')}</div>`}
    </section>
    <section class="panel"><div class="panel-heading"><div><span class="eyebrow">单站复核</span><h2>例外站点 <span class="tally">${exceptions.length}</span></h2></div></div>
      ${exceptions.length ? table('例外站点', ['站点', '类型', '开放件数', '闭站 / 冲突', '建议复核'], exceptions.map(m => `<tr>
        <td><span class="key mono">${m.code}</span> · ${esc(m.name)}</td><td>${badge(stationLabels[m.status], m.status)}</td>
        <td class="mono">${number(m.total)}</td>
        <td class="mono">${number(m.closed_total_hours ?? 0)} 时 / ${number(m.conflict_returns ?? 0)} 件</td>
        <td>${esc(m.noise_reason || exceptionNotes[m.status])}</td></tr>`)) : blank('没有例外站点', '窗口内所有站点均已分型。')}</section>
    <section class="panel"><div class="panel-heading"><div><span class="eyebrow">邻域诊断</span><h2>逐站分型结果</h2></div></div>
      ${table('逐站分型结果', ['站点', '类型', '分组', '邻居', '分时件数与开放小时（按时段顺序）'], members.map(m => `<tr>
        <td><span class="key mono">${m.code}</span> · ${esc(m.name)}</td><td>${badge(stationLabels[m.status], m.status)}</td>
        <td>${m.group || '—'}</td><td>${m.neighbors ?? '—'}</td><td>${vectorSummary(m)}</td></tr>`))}</section>`;
}
