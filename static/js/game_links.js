/**
 * Wire up any element with data-game-id to navigate to the Hunt tracker
 * for that game. Call this after rendering any HTML that contains game cards.
 */
function wireGameLinks(root) {
    if (!root) root = document;
    const els = root.querySelectorAll('[data-game-id]');
    els.forEach(el => {
        // Skip elements already wired
        if (el.dataset.wired === '1') return;
        el.dataset.wired = '1';
        el.style.cursor = 'pointer';
        el.addEventListener('click', (e) => {
            // Don't hijack actual anchor tags inside the card (if any)
            if (e.target.tagName === 'A') return;
            const gid = el.dataset.gameId;
            if (gid) {
                window.location.href = `/hunt?game_id=${encodeURIComponent(gid)}`;
            }
        });
    });
}

// Make it globally available
window.wireGameLinks = wireGameLinks;
