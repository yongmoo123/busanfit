// Group only labels that overlap on screen; route coordinates stay unchanged.
export function groupMapMarkers(points) {
  const groups = points.map((point, index) => ({ x: point.x, y: point.y, indices: [index] }))
  let merged = true
  while (merged) {
    merged = false
    for (let a = 0; a < groups.length && !merged; a += 1) {
      for (let b = a + 1; b < groups.length; b += 1) {
        const first = groups[a]
        const second = groups[b]
        const widthA = Math.max(28, first.indices.length * 22)
        const widthB = Math.max(28, second.indices.length * 22)
        if (Math.abs(first.x - second.x) >= (widthA + widthB) / 2 + 6
          || Math.abs(first.y - second.y) >= 34) continue
        const indices = [...first.indices, ...second.indices].sort((x, y) => x - y)
        groups[a] = {
          indices,
          x: indices.reduce((sum, index) => sum + points[index].x, 0) / indices.length,
          y: indices.reduce((sum, index) => sum + points[index].y, 0) / indices.length,
        }
        groups.splice(b, 1)
        merged = true
        break
      }
    }
  }
  return groups
}
