export const REPORT_CATALOG = [
  { code: 'summary', title: 'Оперативная сводка', stem: 'svodka' },
  { code: 'alarms', title: 'Журнал тревог', stem: 'trevogi' },
  { code: 'requests', title: 'Заявки за период', stem: 'zayavki' },
  { code: 'technicians', title: 'Нагрузка техников', stem: 'tehniki' },
  { code: 'forecasts', title: 'Прогнозы за период', stem: 'prognozy' },
]

export function reportFileName(stem, from, to) {
  return `${stem}_${from}_${to}.pdf`
}
