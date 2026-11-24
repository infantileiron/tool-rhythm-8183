export const roles = Object.freeze({admin: '值班负责人', analyst: '分析员', observer: '观察员'});
export const runLabels = Object.freeze({queued: '待计算', running: '计算中', ready: '待复核', published: '已发布', failed: '计算失败'});
export const stationLabels = Object.freeze({core: '核心站', border: '边界站', noise: '失群', low_sample: '低样本', no_data: '无记录'});
export const exceptionNotes = Object.freeze({
  noise: '核对自助柜日志与登记小时，再决定是否单独排班。',
  low_sample: '延长采样窗口，归还量达门槛后重新计算。',
  no_data: '联系站点确认窗口内是否开放、是否漏传。',
});
export const demoPeriod = Object.freeze({start: '2026-11-09', end: '2026-11-15'});
// 分组依据写在分型页面，与后端口径保持一致。
export const groupingBasis = Object.freeze({
  grouped: '同组各站在至少一个共同开放时段上形状相近（余弦距离不超过 ε），组画像只按共同开放时段等权平均。',
  ungrouped: '暂不分组：邻域站点之间没有共同开放时段（闭站安排不重合），或闭邻域人数不足；逐站核实闭站登记后再决定。',
  closure: '闭站时段的件数与小时同时剔除，按每开放小时归还件数比较节律；闭站内的归还保留为冲突凭据，不删除原记录。',
});
