/* TikTok Factory — Mission Control interactivity */

/* ── Sidebar toggle ────────────────────────── */

function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const spacer = document.getElementById('sidebar-spacer');
    const header = document.getElementById('mobile-header');
    const label = document.getElementById('collapse-label');
    const collapsed = sidebar.classList.contains('-translate-x-full');

    if (collapsed) {
        sidebar.classList.remove('-translate-x-full');
        spacer.classList.remove('w-0');
        spacer.classList.add('w-64');
        header.classList.add('hidden');
        label.textContent = 'Collapse';
        localStorage.setItem('sidebar-collapsed', 'false');
    } else {
        sidebar.classList.add('-translate-x-full');
        spacer.classList.remove('w-64');
        spacer.classList.add('w-0');
        header.classList.remove('hidden');
        header.classList.add('flex');
        label.textContent = 'Expand';
        localStorage.setItem('sidebar-collapsed', 'true');
    }
}

// Restore sidebar state on load
document.addEventListener('DOMContentLoaded', () => {
    if (localStorage.getItem('sidebar-collapsed') === 'true') {
        toggleSidebar();
    }
});


/* ── Account switcher ──────────────────────── */

function switchAccount(accountId) {
    document.cookie = `account_id=${accountId};path=/;max-age=31536000`;
    window.location.reload();
}


/* ── Toast auto-dismiss ────────────────────── */

function dismissToast(el) {
    el.classList.add('fade-out');
    setTimeout(() => el.remove(), 400);
}

document.body.addEventListener('htmx:afterSwap', () => {
    document.querySelectorAll('.toast:not(.fade-out)').forEach(toast => {
        setTimeout(() => dismissToast(toast), 4000);
    });
});


/* ── Publish page helpers ─────────────────── */

function copyFromTextarea(textareaId, feedbackId) {
    const textarea = document.getElementById(textareaId);
    const feedback = document.getElementById(feedbackId);
    if (!textarea) return;

    navigator.clipboard.writeText(textarea.value).then(() => {
        if (feedback) {
            feedback.classList.remove('hidden');
            setTimeout(() => feedback.classList.add('hidden'), 2000);
        }
    }).catch(() => {
        textarea.select();
        document.execCommand('copy');
        if (feedback) {
            feedback.classList.remove('hidden');
            setTimeout(() => feedback.classList.add('hidden'), 2000);
        }
    });
}

function syncCaption(button) {
    const form = button.closest('form');
    const hidden = form.querySelector('.caption-sync');
    if (hidden && hidden.dataset.source) {
        const textarea = document.getElementById(hidden.dataset.source);
        if (textarea) hidden.value = textarea.value;
    }
}

function updateCharCount(textarea, counter) {
    if (textarea && counter) {
        counter.textContent = textarea.value.length;
    }
}


/* ── Video click handler ───────────────────── */

document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.video-card video').forEach(video => {
        video.addEventListener('click', (e) => {
            e.stopPropagation();
            if (video.paused) {
                video.play();
            } else {
                video.pause();
            }
        });
    });
});
