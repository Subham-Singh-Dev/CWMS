// Global Theme Handler - Robust Version
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initTheme);
} else {
    initTheme();
}

function initTheme() {
    const theme = localStorage.getItem('theme');
    if (theme === 'dark') {
        document.body.setAttribute('data-theme', 'dark');
    }
}

function toggleTheme() {
    const isDark = document.body.hasAttribute('data-theme');
    if (isDark) {
        document.body.removeAttribute('data-theme');
        localStorage.theme = 'light';
        updateThemeIcons('🌙');
    } else {
        document.body.setAttribute('data-theme', 'dark');
        localStorage.theme = 'dark';
        updateThemeIcons('☀️');
    }
}

function updateThemeIcons(icon) {
    document.querySelectorAll('.theme-toggle').forEach(btn => {
        btn.textContent = icon;
    });
}

// Set icon on load
window.addEventListener('DOMContentLoaded', () => {
    const icon = localStorage.theme === 'dark' ? '☀️' : '🌙';
    updateThemeIcons(icon);
});