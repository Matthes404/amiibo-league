document.addEventListener('DOMContentLoaded', function() {
    const toggle = document.getElementById('theme-toggle');
    if (!toggle) return;
    const saved = localStorage.getItem('darkmode');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    if (saved === 'true' || (saved === null && prefersDark)) {
        document.body.classList.add('dark-mode');
    }
    toggle.addEventListener('click', function() {
        document.body.classList.toggle('dark-mode');
        localStorage.setItem('darkmode', document.body.classList.contains('dark-mode'));
    });
});
