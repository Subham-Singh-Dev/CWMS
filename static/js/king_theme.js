// King Dashboard Theme Handler (Isolated)
(function() {
    const kingTheme = localStorage.getItem('king_theme') || 'dark';
    document.documentElement.dataset.kingTheme = kingTheme;
    updateKingThemeIcon(kingTheme);
})();

function toggleKingTheme() {
    const isDark = document.documentElement.dataset.kingTheme === 'dark';
    const newTheme = isDark ? 'light' : 'dark';
    
    document.documentElement.dataset.kingTheme = newTheme;
    localStorage.setItem('king_theme', newTheme);
    updateKingThemeIcon(newTheme);
    updateChartsTheme(newTheme);
}

function updateKingThemeIcon(theme) {
    const icon = theme === 'dark' ? '🌙' : '☀️';
    const btn = document.querySelector('.king-theme-toggle');
    if (btn) {
        btn.textContent = icon + ' ' + btn.getAttribute('data-label');
    }
}

function updateChartsTheme(theme) {
    const isDark = theme === 'dark';
    const gridColor  = isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.08)';
    const tickColor  = isDark ? '#6b7294' : '#565b80';
    const legendColor = isDark ? '#a8b0c8' : '#3d4266';
    
    // Update all chart defaults
    Chart.defaults.color = legendColor;
    Chart.defaults.borderColor = gridColor;
    
    // Update each chart instance
    if (typeof financialChart !== 'undefined') {
        financialChart.options.plugins.legend.labels.color = legendColor;
        if (financialChart.options.scales.x) {
            financialChart.options.scales.x.grid.color = gridColor;
            financialChart.options.scales.x.ticks.color = tickColor;
        }
        if (financialChart.options.scales.y) {
            financialChart.options.scales.y.grid.color = gridColor;
            financialChart.options.scales.y.ticks.color = tickColor;
        }
        financialChart.update('none');
    }
}

window.addEventListener('DOMContentLoaded', () => {
    const theme = localStorage.getItem('king_theme') || 'dark';
    updateKingThemeIcon(theme);
});
