import {api} from '../api/client.js';
import {badge, blank, heading, table} from '../components/common/board.js';
import {bindForm} from '../hooks/forms.js';
import {workbench} from '../stores/workbench.js';
import {esc, number, pad} from '../utils/format.js';

export async function ledgerPage(container, selected) {
  const canEdit = workbench.user.role === 'analyst';
  workbench.stations = await api.stations();
  const view = workbench.ledger;
  if (selected && workbench.stations.some(s => s.code === selected)) {
    view.station = selected;
    view.page = 1;
  }
  const options = workbench.stations.map(site => `<option value="${site.code}">${site.code} · ${esc(site.name)}</option>`).join('');
  container.innerHTML = `${heading('归还时段', '按北京时间登记每个站点每小时的归还件数；闭站时段可补登，闭站内归还保留为冲突凭据。',
    canEdit ? '<button class="primary" id="new-record">补录归还</button>' : '')}
    <section class="panel"><form id="ledger-filter" class="filters">
      <label>起日<input name="start" type="date" value="${esc(view.start)}" required></label>
      <label>止日<input name="end" type="date" value="${esc(view.end)}" required></label>
      <label>站点<select name="station"><option value="">全部站点</option>${options}</select></label>
      <button class="secondary" type="submit">查询台账</button><p role="alert" class="error"></p>
    </form></section>
    <form id="record-form" class="entry panel" hidden>
      <h2>补录归还</h2><div class="field-grid">
        <label>站点<select name="station_code" required>${options}</select></label>
        <label>归还日期<input name="day" type="date" value="${esc(view.end)}" required></label>
        <label>起始小时<input name="hour" type="number" min="0" max="23" value="10" required></label>
        <label>件数<input name="quantity" type="number" min="1" max="9999" required></label>
        <label>来源联单<input name="source" minlength="2" maxlength="80" placeholder="回收联_1115补记.csv" required></label>
      </div>
      <p class="form-hint">闭站时段也允许补登：记录原样保存，并在台账与分型中标注为闭站冲突凭据，不会被删除。</p>
      <p role="alert" class="error"></p><button type="submit" class="primary">保存归还</button>
    </form>
    ${canEdit ? `<form id="closure-form" class="entry panel closure-entry">
      <h2>闭站登记</h2>
      <p class="form-hint">登记临时关门的半开时段（含起始时点、不含结束时点）。同站时段不得交叠；分型时闭站小时与该时段件数一并剔除，闭站内归还仍留作冲突凭据。</p>
      <div class="field-grid">
        <label>站点<select name="station_code" required>${options}</select></label>
        <label>起始日期<input name="start_date" type="date" value="${esc(view.start)}" required></label>
        <label>起始小时<input name="start_hour" type="number" min="0" max="23" value="14" required></label>
        <label>结束日期<input name="end_date" type="date" value="${esc(view.start)}" required></label>
        <label>结束小时（不含）<input name="end_hour" type="number" min="0" max="23" value="17" required></label>
        <label>闭站原因<input name="reason" minlength="2" maxlength="120" placeholder="例：停电关门、场地检修" required></label>
      </div><p role="alert" class="error"></p><button type="submit" class="primary">保存闭站登记</button>
    </form>` : ''}
    <section class="panel" id="closure-list"><p class="loading">正在读取闭站登记…</p></section>
    <section class="panel" id="ledger-list"><p class="loading">正在读取台账…</p></section>
    <dialog id="correction"><form class="entry"><h2>校正归还记录</h2><p id="record-meta"></p>
      <label>件数<input name="quantity" type="number" min="1" max="9999" required></label>
      <label>来源联单<input name="source" minlength="2" maxlength="80" required></label>
      <p role="alert" class="error"></p><div class="actions"><button type="submit" class="primary">保存校正</button><button type="button" class="secondary" data-close>取消</button></div>
    </form></dialog>`;
  const filters = container.querySelector('#ledger-filter');
  filters.elements.station.value = view.station;
  const ledger = container.querySelector('#ledger-list');
  const closurePanel = container.querySelector('#closure-list');
  const dialog = container.querySelector('#correction');
  let editing;
  const periodOf = query => ({start: query.start, end: query.end});
  const loadClosures = async (query = view) => {
    const items = await api.closures(periodOf(query), query.station);
    if (!container.isConnected) return;
    closurePanel.innerHTML = `<div class="panel-heading"><div><span class="eyebrow">闭站时段</span><h2>闭站登记 <span class="tally">${number(items.length)}</span></h2></div></div>` +
      (items.length ? table('闭站登记', ['站点', '闭站半开时段', '原因', ...(canEdit ? ['操作'] : [])], items.map(row => `
        <tr><td>${esc(row.name)} <small>${row.station_code}</small></td>
        <td class="mono">${row.start_date} ${pad(row.start_hour)}:00 → ${row.end_date} ${pad(row.end_hour)}:00</td>
        <td>${esc(row.reason)}</td>
        ${canEdit ? `<td><button class="text-button" data-closure="${row.id}">删除登记</button></td>` : ''}</tr>`)) :
        blank('窗口内没有闭站登记', '临时关门时在此补登；闭站时段的归还节律会按开放小时重算。'));
    for (const button of closurePanel.querySelectorAll('[data-closure]')) {
      button.onclick = async () => {
        try {
          await api.deleteClosure(Number(button.dataset.closure));
          await Promise.all([loadClosures(), load()]);
        } catch (error) {
          filters.querySelector('[role=alert]').textContent = error.message;
        }
      };
    }
  };
  const load = async (query = view) => {
    const {start, end, station, page} = query;
    const {total, quantity, items} = await api.records({start, end}, station, page);
    if (!container.isConnected) return;
    Object.assign(view, query);
    const conflictCount = items.filter(row => row.during_closure).length;
    ledger.innerHTML = `<div class="panel-heading"><div><span class="eyebrow">小时归还联</span><h2>归还记录 <span class="tally">${number(total)} 笔</span></h2></div>
        <strong class="key">${number(quantity)} 件${conflictCount ? ` · <span class="closure-flag">本页 ${number(conflictCount)} 笔闭站冲突凭据</span>` : ''}</strong></div>` +
      (items.length ? table('归还记录', ['日期 / 小时', '站点', '件数', '联单', '修订', ...(canEdit ? ['操作'] : [])], items.map(row => `
        <tr class="${row.during_closure ? 'conflict-row' : ''}"><td class="mono">${row.day} <strong>${pad(row.hour)}:00</strong>${row.during_closure ? '<br><span class="closure-flag">闭站冲突凭据</span>' : ''}</td>
        <td>${esc(row.name)} <small>${row.station_code}</small></td>
        <td><strong>${row.quantity}</strong></td><td>${esc(row.source)}</td><td>${badge(`R${row.revision}`)}</td>
        ${canEdit ? `<td><button class="text-button" data-edit="${row.id}">校正</button></td>` : ''}</tr>`)) : blank('窗口内没有记录', '可扩大日期窗口，或请分析员检查是否漏录。')) +
      `<div class="pager"><button class="secondary" type="button" data-page="${page - 1}" ${page === 1 ? 'disabled' : ''}>上一页</button>
      <span>第 ${page} / ${Math.max(1, Math.ceil(total / 12))} 页</span>
      <button class="secondary" type="button" data-page="${page + 1}" ${page * 12 >= total ? 'disabled' : ''}>下一页</button></div>`;
    for (const button of ledger.querySelectorAll('[data-page]')) {
      button.onclick = () => load({...view, page: Number(button.dataset.page)}).catch(showError);
    }
    for (const button of ledger.querySelectorAll('[data-edit]')) {
      button.onclick = () => {
        editing = items.find(row => String(row.id) === button.dataset.edit);
        dialog.querySelector('#record-meta').textContent = `${editing.name} · ${editing.day} ${pad(editing.hour)}:00 · R${editing.revision}`;
        dialog.querySelector('[role=alert]').textContent = '';
        dialog.querySelector('[name=quantity]').value = editing.quantity;
        dialog.querySelector('[name=source]').value = editing.source;
        dialog.showModal();
      };
    }
  };
  const showError = error => filters.querySelector('[role=alert]').textContent = error.message;
  bindForm(filters, data => Promise.all([load({...data, page: 1}), loadClosures({...data, page: 1})]));
  dialog.querySelector('[data-close]').onclick = () => dialog.close();
  bindForm(dialog.querySelector('form'), async data => {
    await api.correctRecord(editing.id, {...data, quantity: Number(data.quantity), revision: editing.revision});
    dialog.close();
    await load().catch(showError);
  });
  if (canEdit) {
    const form = container.querySelector('#record-form');
    container.querySelector('#new-record').onclick = () => {
      form.hidden = !form.hidden;
      if (!form.hidden && view.station) form.elements.station_code.value = view.station;
    };
    bindForm(form, async data => {
      await api.addRecord({...data, hour: Number(data.hour), quantity: Number(data.quantity)});
      for (const [name, value] of Object.entries({start: data.day, end: data.day, station: data.station_code})) {
        filters.elements[name].value = value;
      }
      form.elements.quantity.value = '';
      form.hidden = true;
      await Promise.all([load({start: data.day, end: data.day, station: data.station_code, page: 1}),
                         loadClosures({start: data.day, end: data.day, station: data.station_code})]).catch(showError);
    });
    const closureForm = container.querySelector('#closure-form');
    if (view.station) closureForm.elements.station_code.value = view.station;
    bindForm(closureForm, async data => {
      await api.addClosure({...data, start_hour: Number(data.start_hour), end_hour: Number(data.end_hour)});
      await Promise.all([loadClosures(view), load()]).catch(showError);
      closureForm.elements.reason.value = '';
    });
  }
  await Promise.all([load(), loadClosures()]);
}
