export function formatNumber(value) {
  const rounded = Math.round((value + Number.EPSILON) * 100) / 100
  return Number.isInteger(rounded)
    ? String(rounded)
    : String(rounded).replace(/(?:\.0+|(?<=\..*?)0+)$/, '')
}
