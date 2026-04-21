/**
 * Global "hardcore vs softcore" display preference.
 * Stored in localStorage as 'ra_progress_mode' = 'softcore' | 'hardcore'.
 * Softcore is the default.
 */
const PROGRESS_MODE_KEY = 'ra_progress_mode';

function getProgressMode() {
    try {
        return localStorage.getItem(PROGRESS_MODE_KEY) || 'softcore';
    } catch {
        return 'softcore';
    }
}

function setProgressMode(mode) {
    try {
        localStorage.setItem(PROGRESS_MODE_KEY, mode);
    } catch {}
    // Notify any listeners on this page
    window.dispatchEvent(new CustomEvent('progressmodechange', {detail: {mode}}));
}

function isSoftcore() {
    return getProgressMode() === 'softcore';
}

window.getProgressMode = getProgressMode;
window.setProgressMode = setProgressMode;
window.isSoftcore = isSoftcore;

// Wire up the header toggle once DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    const toggle = document.getElementById('progress-mode-toggle');
    if (!toggle) return;
    // Reflect current state
    toggle.checked = !isSoftcore();  // checked = hardcore
    toggle.addEventListener('change', () => {
        setProgressMode(toggle.checked ? 'hardcore' : 'softcore');
    });
    // Update label text
    const updateLabel = () => {
        const label = document.getElementById('progress-mode-label');
        if (label) label.textContent = isSoftcore() ? 'Softcore' : 'Hardcore';
    };
    updateLabel();
    window.addEventListener('progressmodechange', updateLabel);
});

/**
 * Build a fully-qualified badge image URL from either a BadgeURL
 * (relative path like "/Badge/12345.png") or a bare BadgeName ("12345").
 * Returns empty string if neither is provided.
 */
function badgeImageUrl(badgeUrl, badgeName) {
    if (badgeUrl) {
        // Already absolute? Return as-is.
        if (/^https?:\/\//.test(badgeUrl)) return badgeUrl;
        // Otherwise it's a path like "/Badge/12345.png"
        return `https://media.retroachievements.org${badgeUrl}`;
    }
    if (badgeName) {
        return `https://media.retroachievements.org/Badge/${badgeName}.png`;
    }
    return '';
}
window.badgeImageUrl = badgeImageUrl;

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
