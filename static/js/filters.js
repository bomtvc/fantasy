/**
 * Filters functionality
 * Handle filter validation and state management
 */

// === Filter Validation ===
function validateFilters(filters) {
    const errors = [];

    // League ID required
    if (!filters.league_id || filters.league_id <= 0) {
        errors.push('League ID is required and must be positive');
    }

    // Phase validation
    if (filters.phase && (filters.phase < 1 || filters.phase > 3)) {
        errors.push('Phase must be between 1 and 3');
    }

    // GW range validation
    if (filters.gw_start && filters.gw_end) {
        const start = parseInt(filters.gw_start);
        const end = parseInt(filters.gw_end);

        if (start < 1 || start > 38) {
            errors.push('GW start must be between 1 and 38');
        }

        if (end < 1 || end > 38) {
            errors.push('GW end must be between 1 and 38');
        }

        if (start > end) {
            errors.push('GW start cannot be greater than GW end');
        }
    }

    // Month mapping validation
    if (filters.month_mapping) {
        if (!isValidMonthMapping(filters.month_mapping)) {
            errors.push('Month mapping format is invalid (use format: 1-4,5-8,9-12)');
        }
    }

    return {
        valid: errors.length === 0,
        errors
    };
}

function isValidMonthMapping(mapping) {
    const pattern = /^(\d+(-\d+)?)(,\d+(-\d+)?)*$/;
    return pattern.test(mapping);
}

// === Get Current Filters ===
function getCurrentFilters() {
    return {
        league_id: document.getElementById('league-id')?.value,
        phase: document.getElementById('phase')?.value || 1,
        gw_start: document.getElementById('gw-start')?.value || 1,
        gw_end: document.getElementById('gw-end')?.value || 10,
        month_mapping: document.getElementById('month-mapping')?.value,
        max_entries: document.getElementById('max-entries')?.value || null
    };
}

// === Build Query String ===
function buildQueryString(filters) {
    const params = new URLSearchParams();

    Object.keys(filters).forEach(key => {
        if (filters[key] !== null && filters[key] !== '') {
            params.append(key, filters[key]);
        }
    });

    return params.toString();
}
