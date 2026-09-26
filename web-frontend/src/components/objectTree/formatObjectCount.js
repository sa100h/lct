export function formatObjectCount(count) {
  const n10 = count % 10
  const n100 = count % 100
  if (n10 === 1 && n100 !== 11) {
    return `${count} объект`
  }
  if (n10 >= 2 && n10 <= 4 && (n100 < 12 || n100 > 14)) {
    return `${count} объекта`
  }
  return `${count} объектов`
}
