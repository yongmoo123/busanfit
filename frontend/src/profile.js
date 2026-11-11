function unsetCondition(strength) {
  return {
    value: null,
    source: 'UNSET',
    strength,
  }
}

export function createEmptyProfile() {
  return {
    area: unsetCondition('HARD'),
    timeWindow: unsetCondition('HARD'),
    transport: unsetCondition('SOFT'),
    mobility: unsetCondition('HARD'),
    budget: unsetCondition('HARD'),
    indoorPreference: unsetCondition('SOFT'),
    companions: unsetCondition('SOFT'),
    excludedCategories: unsetCondition('HARD'),
    preferenceTags: unsetCondition('SOFT'),
    includeUnknownAccessibility: false,
  }
}