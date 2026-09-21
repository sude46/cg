import dayjs from 'dayjs'

/** 阅读型时间显示：刚刚 / n分钟前 / n小时前 / 昨天 / M月D日 / YYYY年M月D日 */
export function fromNow(iso: string): string {
  if (!iso) return ''
  const t = dayjs(iso)
  if (!t.isValid()) return ''
  const now = dayjs()
  const minutes = now.diff(t, 'minute')
  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes} 分钟前`
  const hours = now.diff(t, 'hour')
  if (hours < 24 && t.isSame(now, 'day')) return `${hours} 小时前`
  if (t.isSame(now.subtract(1, 'day'), 'day')) return `昨天 ${t.format('HH:mm')}`
  if (t.isSame(now, 'year')) return t.format('M月D日')
  return t.format('YYYY年M月D日')
}

export function fullTime(iso: string): string {
  const t = dayjs(iso)
  return t.isValid() ? t.format('YYYY-MM-DD HH:mm') : ''
}
