/**
 * Reusable UI Components
 */

// === Data Table Component ===
class DataTable {
    constructor(containerId, options = {}) {
        this.container = document.getElementById(containerId);
        this.options = {
            searchable: options.searchable || false,
            sortable: options.sortable || true,
            paginated: options.paginated || false,
            pageSize: options.pageSize || 20,
            hiddenColumns: options.hiddenColumns || [],
            columnOrder: options.columnOrder || null,
            compactControls: options.compactControls || false,
            columnLabels: options.columnLabels || null, // Function or object for custom labels
            ...options
        };
        this.data = [];
        this.filteredData = [];
        this.currentPage = 1;
        this.sortColumn = null;
        this.sortDirection = 'asc';
    }

    setData(data) {
        this.data = data;
        this.filteredData = [...data];
        this.render();
    }

    setColumnOrder(columnOrder) {
        this.options.columnOrder = columnOrder;
    }

    render() {
        if (!this.container) return;

        let html = '';

        // Controls
        if (this.options.searchable || this.options.exportable) {
            html += this.renderControls();
        }

        // Table
        html += this.renderTable();

        // Pagination
        if (this.options.paginated) {
            html += this.renderPagination();
        }

        this.container.innerHTML = html;
        this.attachEventListeners();
    }

    renderControls() {
        const compactClass = this.options.compactControls ? 'compact' : '';
        return `
            <div class="data-controls ${compactClass}">
                <div class="data-controls-left">
                    ${this.options.searchable ? `
                        <div class="search-box">
                            <span class="search-icon">🔍</span>
                            <input type="text"
                                   class="search-input"
                                   id="table-search"
                                   placeholder="Search...">
                        </div>
                    ` : ''}
                </div>
                <div class="data-controls-right">
                    ${this.options.exportable ? `
                        <button class="btn btn-secondary btn-icon-only"
                                id="export-csv"
                                title="Export to CSV">
                            📥
                        </button>
                    ` : ''}
                </div>
            </div>
        `;
    }

    getOrderedColumns() {
        if (this.filteredData.length === 0) return [];

        let columns = Object.keys(this.filteredData[0]);

        // Filter out hidden columns
        if (this.options.hiddenColumns.length > 0) {
            columns = columns.filter(col => !this.options.hiddenColumns.includes(col));
        }

        // Reorder columns if columnOrder is specified
        if (this.options.columnOrder && this.options.columnOrder.length > 0) {
            const orderedCols = [];
            // First add columns from columnOrder that exist in data
            this.options.columnOrder.forEach(col => {
                if (columns.includes(col)) {
                    orderedCols.push(col);
                }
            });
            // Then add remaining columns not in columnOrder
            columns.forEach(col => {
                if (!orderedCols.includes(col)) {
                    orderedCols.push(col);
                }
            });
            columns = orderedCols;
        }

        return columns;
    }

    renderTable() {
        if (this.filteredData.length === 0) {
            return this.renderEmptyState();
        }

        const columns = this.getOrderedColumns();
        const start = (this.currentPage - 1) * this.options.pageSize;
        const end = start + this.options.pageSize;
        const pageData = this.options.paginated ?
            this.filteredData.slice(start, end) :
            this.filteredData;

        return `
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            ${columns.map(col => `
                                <th class="${this.options.sortable ? 'sortable' : ''}"
                                    data-column="${col}">
                                    ${this.formatColumnName(col)}
                                    ${this.sortColumn === col ?
                (this.sortDirection === 'asc' ? '↑' : '↓') :
                ''}
                                </th>
                            `).join('')}
                        </tr>
                    </thead>
                    <tbody>
                        ${pageData.map((row, idx) => `
                            <tr>
                                ${columns.map(col => `
                                    <td>${this.formatCellValue(row[col], col, idx)}</td>
                                `).join('')}
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        `;
    }

    renderEmptyState() {
        return `
            <div class="empty-state">
                <div class="empty-icon">📊</div>
                <h3 class="empty-title">No Data Available</h3>
                <p class="empty-text">Try adjusting your filters or check back later.</p>
            </div>
        `;
    }

    renderPagination() {
        const totalPages = Math.ceil(this.filteredData.length / this.options.pageSize);

        if (totalPages <= 1) return '';

        return `
            <div class="pagination">
                <button class="btn btn-secondary" 
                        ${this.currentPage === 1 ? 'disabled' : ''}
                        data-page="prev">Previous</button>
                <span class="pagination-info">
                    Page ${this.currentPage} of ${totalPages}
                </span>
                <button class="btn btn-secondary" 
                        ${this.currentPage === totalPages ? 'disabled' : ''}
                        data-page="next">Next</button>
            </div>
        `;
    }

    formatColumnName(name) {
        // Check for custom label function
        if (typeof this.options.columnLabels === 'function') {
            const customLabel = this.options.columnLabels(name);
            if (customLabel !== null && customLabel !== undefined) {
                return customLabel;
            }
        }
        // Check for custom label object
        if (this.options.columnLabels && typeof this.options.columnLabels === 'object') {
            if (this.options.columnLabels[name]) {
                return this.options.columnLabels[name];
            }
        }
        // Default formatting
        return name.replace(/_/g, ' ')
            .replace(/\b\w/g, l => l.toUpperCase());
    }

    formatCellValue(value, column, rowIndex) {
        // Format rank with medal classes
        if (column.toLowerCase().includes('rank')) {
            const rankClass = rowIndex < 3 ? `rank-${rowIndex + 1}` : '';
            return `<span class="${rankClass}">${value}</span>`;
        }

        // Format numbers
        if (typeof value === 'number') {
            return formatNumber(value);
        }

        return value || '-';
    }

    attachEventListeners() {
        // Search
        const searchInput = document.getElementById('table-search');
        if (searchInput) {
            searchInput.addEventListener('input', debounce((e) => {
                this.handleSearch(e.target.value);
            }, 300));
        }

        // Sort
        if (this.options.sortable) {
            const headers = this.container.querySelectorAll('th.sortable');
            headers.forEach(header => {
                header.addEventListener('click', () => {
                    this.handleSort(header.dataset.column);
                });
            });
        }

        // Pagination
        const paginationBtns = this.container.querySelectorAll('[data-page]');
        paginationBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                this.handlePageChange(btn.dataset.page);
            });
        });

        // Export
        const exportBtn = document.getElementById('export-csv');
        if (exportBtn) {
            exportBtn.addEventListener('click', () => {
                this.handleExport();
            });
        }
    }

    handleSearch(query) {
        query = query.toLowerCase();
        this.filteredData = this.data.filter(row => {
            return Object.values(row).some(value =>
                String(value).toLowerCase().includes(query)
            );
        });
        this.currentPage = 1;
        this.render();
    }

    handleSort(column) {
        if (this.sortColumn === column) {
            this.sortDirection = this.sortDirection === 'asc' ? 'desc' : 'asc';
        } else {
            this.sortColumn = column;
            this.sortDirection = 'asc';
        }

        this.filteredData.sort((a, b) => {
            let valueA = a[column];
            let valueB = b[column];

            // Handle numbers
            if (typeof valueA === 'number' && typeof valueB === 'number') {
                return this.sortDirection === 'asc' ? valueA - valueB : valueB - valueA;
            }

            // Handle strings
            valueA = String(valueA).toLowerCase();
            valueB = String(valueB).toLowerCase();

            if (this.sortDirection === 'asc') {
                return valueA < valueB ? -1 : valueA > valueB ? 1 : 0;
            } else {
                return valueA > valueB ? -1 : valueA < valueB ? 1 : 0;
            }
        });

        this.render();
    }

    handlePageChange(direction) {
        if (direction === 'prev' && this.currentPage > 1) {
            this.currentPage--;
        } else if (direction === 'next') {
            const totalPages = Math.ceil(this.filteredData.length / this.options.pageSize);
            if (this.currentPage < totalPages) {
                this.currentPage++;
            }
        }
        this.render();
    }

    handleExport() {
        exportToCSV(this.filteredData, `fpl-data-${Date.now()}.csv`);
    }
}

// === Make DataTable globally available ===
window.DataTable = DataTable;
