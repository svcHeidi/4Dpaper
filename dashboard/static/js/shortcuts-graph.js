/**
 * Shortcuts connection graph visualization for 4DPapers dashboard.
 *
 * Displays a simple SVG visualization showing how shortcut names
 * map to their external folder paths.
 *
 * Allows users to:
 * - See all configured shortcuts
 * - Click a shortcut to copy @name/ to clipboard
 * - Hover to see full paths
 * - Refresh shortcuts list
 */

/**
 * Render the shortcuts graph visualization.
 * Fetches shortcuts from /api/shortcuts and draws an SVG.
 */
async function renderShortcutsGraph() {
  const container = document.getElementById('shortcutsGraph');
  if (!container) {
    console.warn('[shortcuts-graph] Container #shortcutsGraph not found');
    return;
  }

  try {
    const res = await fetch('/api/shortcuts');
    if (!res.ok) {
      throw new Error(`API error: ${res.status}`);
    }
    const data = await res.json();

    container.innerHTML = '';

    if (!data.shortcuts || data.shortcuts.length === 0) {
      container.innerHTML =
        '<p style="color:#64748b;font-size:12px;padding:8px;">No shortcuts configured</p>';
      return;
    }

    // Create SVG visualization
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    const itemHeight = 50;
    const totalHeight = 40 + data.shortcuts.length * itemHeight;

    svg.setAttribute('viewBox', `0 0 400 ${totalHeight}`);
    svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
    svg.setAttribute('style', 'width:100%;height:auto;');

    let y = 20;

    for (const name of data.shortcuts) {
      const desc = data.descriptions[name] || '';

      // === LEFT: Shortcut name (blue circle) ===
      const circle1 = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      circle1.setAttribute('cx', '40');
      circle1.setAttribute('cy', String(y));
      circle1.setAttribute('r', '8');
      circle1.setAttribute('fill', '#3b82f6');
      circle1.style.transition = 'fill 0.2s';
      svg.appendChild(circle1);

      // Shortcut label
      const text1 = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      text1.setAttribute('x', '60');
      text1.setAttribute('y', String(y + 4));
      text1.setAttribute('font-size', '12');
      text1.setAttribute('fill', '#e2e8f0');
      text1.setAttribute('font-family', 'monospace');
      text1.setAttribute('font-weight', 'bold');
      text1.textContent = `@${name}`;
      svg.appendChild(text1);

      // === MIDDLE: Connection arrow ===
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', '180');
      line.setAttribute('y1', String(y));
      line.setAttribute('x2', '200');
      line.setAttribute('y2', String(y));
      line.setAttribute('stroke', '#64748b');
      line.setAttribute('stroke-width', '1.5');
      svg.appendChild(line);

      // Arrow head (triangle)
      const polygon = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
      polygon.setAttribute('points', `200,${y} 195,${y - 3} 195,${y + 3}`);
      polygon.setAttribute('fill', '#64748b');
      svg.appendChild(polygon);

      // === RIGHT: Folder path (rounded rect + text) ===
      const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      rect.setAttribute('x', '220');
      rect.setAttribute('y', String(y - 8));
      rect.setAttribute('width', '160');
      rect.setAttribute('height', '16');
      rect.setAttribute('rx', '2');
      rect.setAttribute('fill', '#1e293b');
      rect.setAttribute('stroke', '#475569');
      rect.setAttribute('stroke-width', '1');
      rect.style.cursor = 'pointer';
      rect.style.transition = 'all 0.2s';
      svg.appendChild(rect);

      // Path text (truncated if too long)
      const pathText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      pathText.setAttribute('x', '225');
      pathText.setAttribute('y', String(y + 3));
      pathText.setAttribute('font-size', '11');
      pathText.setAttribute('fill', '#94a3b8');
      pathText.setAttribute('font-family', 'monospace');
      pathText.setAttribute('pointer-events', 'none');
      const displayPath = desc.length > 30 ? desc.substring(0, 27) + '…' : desc;
      pathText.textContent = displayPath;
      if (desc.length > 30) {
        pathText.setAttribute('title', desc);
      }
      svg.appendChild(pathText);

      // === INTERACTION: Click to copy, hover feedback ===
      const clickGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      clickGroup.style.cursor = 'pointer';

      // Invisible hit area for easier clicking
      const hitBox = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      hitBox.setAttribute('x', '20');
      hitBox.setAttribute('y', String(y - 15));
      hitBox.setAttribute('width', '360');
      hitBox.setAttribute('height', '30');
      hitBox.setAttribute('fill', 'transparent');
      clickGroup.appendChild(hitBox);

      clickGroup.addEventListener('click', (e) => {
        e.stopPropagation();
        copyToClipboard(`@${name}/`);
        // Visual feedback: circle flashes green
        circle1.style.fill = '#10b981';
        setTimeout(() => {
          circle1.style.fill = '#3b82f6';
        }, 200);
      });

      clickGroup.addEventListener('mouseenter', () => {
        circle1.style.fill = '#60a5fa'; // Lighter blue on hover
        rect.style.fill = '#334155';
        rect.style.stroke = '#64748b';
      });

      clickGroup.addEventListener('mouseleave', () => {
        circle1.style.fill = '#3b82f6';
        rect.style.fill = '#1e293b';
        rect.style.stroke = '#475569';
      });

      svg.appendChild(clickGroup);

      y += itemHeight;
    }

    container.appendChild(svg);
  } catch (error) {
    console.error('[shortcuts-graph] Error rendering graph:', error);
    container.innerHTML =
      '<p style="color:#ef4444;font-size:12px;padding:8px;">Error loading shortcuts</p>';
  }
}

/**
 * Copy text to clipboard and show brief feedback.
 */
function copyToClipboard(text) {
  navigator.clipboard.writeText(text).then(() => {
    // Show brief toast-like notification
    const toast = document.createElement('div');
    toast.style.cssText = `
      position: fixed;
      bottom: 20px;
      right: 20px;
      background: #10b981;
      color: white;
      padding: 10px 16px;
      border-radius: 6px;
      font-size: 12px;
      z-index: 10000;
      animation: slideIn 0.3s ease;
    `;
    toast.textContent = `Copied: ${text}`;
    document.body.appendChild(toast);

    setTimeout(() => {
      toast.style.animation = 'slideOut 0.3s ease forwards';
      setTimeout(() => toast.remove(), 300);
    }, 2000);
  }).catch((err) => {
    console.error('[shortcuts-graph] Copy failed:', err);
  });
}

// ─ Animation styles ──────────────────────────────────────────────
const style = document.createElement('style');
style.textContent = `
  @keyframes slideIn {
    from {
      transform: translateX(400px);
      opacity: 0;
    }
    to {
      transform: translateX(0);
      opacity: 1;
    }
  }
  @keyframes slideOut {
    from {
      transform: translateX(0);
      opacity: 1;
    }
    to {
      transform: translateX(400px);
      opacity: 0;
    }
  }
`;
document.head.appendChild(style);

// ─ Wire up refresh button ─────────────────────────────────────────
document.getElementById('refreshShortcutsBtn')?.addEventListener('click', () => {
  renderShortcutsGraph();
});

// ─ Load graph on page load ───────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  renderShortcutsGraph();
});

// Also render if script loaded after DOM is ready
if (document.readyState === 'interactive' || document.readyState === 'complete') {
  renderShortcutsGraph();
}
