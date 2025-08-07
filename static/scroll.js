document.addEventListener('DOMContentLoaded', function() {
    const pos = localStorage.getItem('scrollpos');
    if (pos) {
        window.scrollTo(0, parseInt(pos, 10));
        localStorage.removeItem('scrollpos');
    }
});

window.addEventListener('beforeunload', function() {
    localStorage.setItem('scrollpos', window.scrollY);
});

