/**
 * CWMS - Worker Portal Global Theme Management
 * Handles anti-flash theme resolution, persistence, and state transitions.
 */
document.addEventListener('DOMContentLoaded', () => {
    const themeBtn = document.getElementById('theme-toggle');
    const iconLight = document.querySelector('.theme-icon-light');
    const iconDark = document.querySelector('.theme-icon-dark');
    const root = document.documentElement;

    function updateIcons(theme) {
        if (!iconLight || !iconDark) return;
        if (theme === 'dark') {
            iconLight.style.display = 'block'; // Sun icon
            iconDark.style.display = 'none';   // Moon icon
        } else {
            iconLight.style.display = 'none';  // Sun icon
            iconDark.style.display = 'block';  // Moon icon
        }
    }

    // Synchronize visual state on instantiation
    updateIcons(root.getAttribute('data-theme'));

    if (themeBtn) {
        themeBtn.addEventListener('click', () => {
            const currentTheme = root.getAttribute('data-theme');
            const newTheme = currentTheme === 'light' ? 'dark' : 'light';
            
            root.setAttribute('data-theme', newTheme);
            localStorage.setItem('cwms-theme', newTheme);
            updateIcons(newTheme);
        });
    }
});