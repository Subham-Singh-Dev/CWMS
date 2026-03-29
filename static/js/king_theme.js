// King Dashboard Theme Handler (Robust Version)
// Safer initialization that waits for DOM to be ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initKingTheme);
} else {
    // DOM already loaded
    initKingTheme();
}

function initKingTheme() {
    const kingTheme = localStorage.getItem('king_theme') || 'light';
    document.documentElement.setAttribute('data-kingTheme', kingTheme);
    updateKingThemeIcon(kingTheme);
}

function toggleKingTheme() {
    const currentTheme = document.documentElement.getAttribute('data-kingTheme') || 'light';
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    
    // Set using setAttribute for consistency
    document.documentElement.setAttribute('data-kingTheme', newTheme);
    
    // Store in localStorage
    localStorage.setItem('king_theme', newTheme);
    
    // Force repaint by triggering reflow
    void document.documentElement.offsetHeight;
    
    // Update UI elements
    updateKingThemeIcon(newTheme);
    updateChartsTheme(newTheme);
}

function updateKingThemeIcon(theme) {
    const icon = theme === 'dark' ? '🌙' : '☀️';
    const btn = document.querySelector('.king-theme-toggle');
    if (btn) {
        btn.textContent = icon;
        btn.setAttribute('title', theme === 'dark' ? 'Switch to Light Mode' : 'Switch to Dark Mode');
    }
}

function updateChartsTheme(theme) {
    const isDark = theme === 'dark';
    const gridColor  = isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.08)';
    const tickColor  = isDark ? '#6b7294' : '#6b7280';
    const legendColor = isDark ? '#a8b0c8' : '#6b7280';
    
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
    
    // Update donut charts
    if (typeof expenseCatChart !== 'undefined') {
        expenseCatChart.options.plugins.legend.labels.color = legendColor;
        expenseCatChart.update('none');
    }
    
    if (typeof roleChart !== 'undefined') {
        roleChart.options.plugins.legend.labels.color = legendColor;
        roleChart.update('none');
    }
}

window.addEventListener('DOMContentLoaded', () => {
    const theme = localStorage.getItem('king_theme') || 'light';
    updateKingThemeIcon(theme);
});
