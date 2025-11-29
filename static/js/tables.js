/**
 * Table utilities
 * Helper functions for table rendering and manipulation
 */

// === Pivot Table Helper ===
function pivotData(data, rowKeys, colKey, valueKey) {
    const pivoted = {};
    const columns = new Set();

    data.forEach(row => {
        const rowKey = rowKeys.map(k => row[k]).join('|');
        const colValue = row[colKey];
        const value = row[valueKey];

        if (!pivoted[rowKey]) {
            pivoted[rowKey] = {};
            rowKeys.forEach(k => {
                pivoted[rowKey][k] = row[k];
            });
        }

        pivoted[rowKey][colValue] = value;
        columns.add(colValue);
    });

    return {
        data: Object.values(pivoted),
        columns: Array.from(columns).sort((a, b) => a - b)
    };
}

// === Create Rank Column ===
function addRankColumn(data, sortKey, ascending = false) {
    // Sort data
    const sorted = [...data].sort((a, b) => {
        if (ascending) {
            return a[sortKey] - b[sortKey];
        } else {
            return b[sortKey] - a[sortKey];
        }
    });

    // Add rank
    sorted.forEach((row, idx) => {
        row.Rank = idx + 1;
    });

    return sorted;
}

// === Calculate Summary Stats ===
function calculateSummary(data, column) {
    const values = data.map(row => parseFloat(row[column]) || 0);

    return {
        total: values.reduce((sum, val) => sum + val, 0),
        average: values.reduce((sum, val) => sum + val, 0) / values.length,
        max: Math.max(...values),
        min: Math.min(...values),
        count: values.length
    };
}

// === Group By ===
function groupBy(data, key) {
    return data.reduce((groups, item) => {
        const groupKey = item[key];
        if (!groups[groupKey]) {
            groups[groupKey] = [];
        }
        groups[groupKey].push(item);
        return groups;
    }, {});
}

// === Highlight Top Values ===
function highlightTopN(data, column, n = 3, className = 'highlight') {
    const sorted = [...data].sort((a, b) => b[column] - a[column]);
    const topValues = sorted.slice(0, n).map(row => row[column]);

    return data.map(row => ({
        ...row,
        [`${column}_class`]: topValues.includes(row[column]) ? className : ''
    }));
}

// === Format Table Data for Display ===
function formatTableData(data, formatters = {}) {
    return data.map(row => {
        const formatted = { ...row };

        Object.keys(formatters).forEach(key => {
            if (row.hasOwnProperty(key)) {
                formatted[key] = formatters[key](row[key], row);
            }
        });

        return formatted;
    });
}

// === Common Formatters ===
const TableFormatters = {
    number: (value) => formatNumber(value),

    points: (value) => {
        if (value > 0) {
            return `<span class="text-success">${value}</span>`;
        } else if (value < 0) {
            return `<span class="text-error">${value}</span>`;
        }
        return value;
    },

    rank: (value, row, index) => {
        const classes = ['rank-1', 'rank-2', 'rank-3'];
        const rankClass = index < 3 ? classes[index] : '';
        return `<span class="${rankClass}">${value}</span>`;
    },

    percentage: (value) => `${(value * 100).toFixed(1)}%`,

    chip: (value) => {
        if (!value || value === '-') return '-';
        return `<span class="chip-badge active">${value}</span>`;
    },

    transfer: (value) => {
        if (!value || value === '-') return '-';

        // Parse format like "3(-4)"
        const match = value.match(/(\d+)\((-?\d+)\)/);
        if (match) {
            const count = match[1];
            const cost = match[2];
            return `${count} <span class="text-muted">(${cost})</span>`;
        }

        return value;
    }
};

// === Export ===
window.TableUtils = {
    pivotData,
    addRankColumn,
    calculateSummary,
    groupBy,
    highlightTopN,
    formatTableData,
    TableFormatters
};
