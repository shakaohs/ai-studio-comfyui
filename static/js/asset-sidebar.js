/* ============================================================
 * 素材库侧栏（可复用）
 * 用法：
 *   AssetSidebar.mount({ onUse: (item, file) => Promise, hint: '说明文字' })
 * 说明：侧栏挂在 <html> 下，避免 body 上有 transform 时 fixed 退化成跟随滚动
 * ============================================================ */
(function () {
    if (window.AssetSidebar) return;

    const CSS = `
    .as-lib-toggle{position:fixed;right:0;top:34%;transform:translateY(-50%);z-index:6000;
        background:#111;color:#fff;border-radius:14px 0 0 14px;padding:16px 9px;
        font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
        font-size:10px;font-weight:800;letter-spacing:.3em;line-height:1.1;writing-mode:vertical-rl;
        cursor:grab;box-shadow:-6px 0 24px rgba(0,0,0,.16);transition:background .2s;
        user-select:none;touch-action:none}
    .as-lib-toggle:hover{background:#000}
    .as-lib-toggle:active{cursor:grabbing}
    .as-lib-panel{position:fixed;right:0;top:0;height:100vh;width:308px;background:#fff;z-index:6001;
        border-left:1px solid rgba(0,0,0,.06);box-shadow:-18px 0 50px rgba(0,0,0,.10);
        display:flex;flex-direction:column;transform:translateX(105%);
        transition:transform .28s cubic-bezier(.4,0,.2,1);
        font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif}
    .as-lib-panel.open{transform:translateX(0)}
    .as-lib-head{display:flex;align-items:center;justify-content:space-between;padding:18px 16px 10px}
    .as-lib-title{font-size:10px;font-weight:900;letter-spacing:.3em;text-transform:uppercase}
    .as-lib-head button{width:26px;height:26px;border:0;background:transparent;border-radius:8px;
        cursor:pointer;color:#6b7280;font-size:14px;line-height:1;display:flex;align-items:center;justify-content:center}
    .as-lib-head button:hover{background:#f3f4f6;color:#111}
    .as-lib-hint{padding:0 16px 10px;font-size:9px;line-height:1.6;color:#9ca3af}
    .as-lib-body{flex:1;overflow-y:auto;padding:0 14px 24px}
    .as-lib-cat{font-size:9px;font-weight:800;letter-spacing:.22em;color:#9ca3af;text-transform:uppercase;margin:14px 2px 8px}
    .as-lib-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:8px}
    .as-lib-item{position:relative;border-radius:10px;overflow:hidden;background:#f3f4f6;cursor:pointer;
        aspect-ratio:1/1;transition:transform .16s}
    .as-lib-item:hover{transform:translateY(-2px)}
    .as-lib-item img{width:100%;height:100%;object-fit:cover;display:block}
    .as-lib-name{position:absolute;left:0;right:0;bottom:0;padding:12px 5px 4px;font-size:8px;font-weight:600;
        color:#fff;background:linear-gradient(to top,rgba(0,0,0,.72),transparent);
        white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .as-lib-empty{padding:28px 10px;text-align:center;font-size:10px;line-height:1.9;color:#c0c4cc}
    .as-lib-spin{width:16px;height:16px;margin:30px auto;border:2px solid #eee;border-top-color:#111;
        border-radius:50%;animation:as-lib-rot .7s linear infinite}
    @keyframes as-lib-rot{to{transform:rotate(360deg)}}
    `;

    const state = { opts: {}, loaded: false, loading: false, toggle: null, panel: null, body: null };
    const LS_KEY = 'assetSidebarTopPct';   // 用户拖过的位置，按视口高度百分比存

    function injectCSS() {
        if (document.getElementById('as-lib-style')) return;
        const s = document.createElement('style');
        s.id = 'as-lib-style';
        s.textContent = CSS;
        (document.head || document.documentElement).appendChild(s);
    }

    function toast(msg, ok) {
        if (window.SaveMaster && window.SaveMaster.toast) return window.SaveMaster.toast(msg, ok);
        let el = document.getElementById('as-lib-toast');
        if (!el) {
            el = document.createElement('div');
            el.id = 'as-lib-toast';
            el.style.cssText = 'position:fixed;left:50%;top:28px;transform:translateX(-50%);z-index:7000;' +
                'background:#111;color:#fff;font-size:11px;font-weight:700;padding:10px 16px;border-radius:999px;' +
                'box-shadow:0 10px 30px rgba(0,0,0,.2);transition:opacity .25s;opacity:0;pointer-events:none;' +
                'font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif';
            document.documentElement.appendChild(el);
        }
        el.textContent = msg;
        el.style.opacity = '1';
        clearTimeout(el._t);
        el._t = setTimeout(() => { el.style.opacity = '0'; }, 2200);
    }

    function build() {
        injectCSS();
        if (document.getElementById('asLibToggle')) {
            state.toggle = document.getElementById('asLibToggle');
            state.panel = document.getElementById('asLibPanel');
            state.body = document.getElementById('asLibBody');
            return;
        }

        const toggle = document.createElement('div');
        toggle.id = 'asLibToggle';
        toggle.className = 'as-lib-toggle';
        toggle.title = '打开素材库';
        toggle.textContent = '素材库';

        const panel = document.createElement('aside');
        panel.id = 'asLibPanel';
        panel.className = 'as-lib-panel';
        panel.innerHTML =
            '<div class="as-lib-head"><span class="as-lib-title">素材库</span>' +
            '<div><button id="asLibRefresh" title="刷新">↻</button><button id="asLibClose" title="收起">✕</button></div></div>' +
            '<p class="as-lib-hint" id="asLibHint">拖到页面里的图片框，或单击缩略图直接选用</p>' +
            '<div class="as-lib-body" id="asLibBody"><div class="as-lib-spin"></div></div>';

        // 挂到 <html>，防止 body 上有 transform 时 fixed 失效
        document.documentElement.appendChild(toggle);
        document.documentElement.appendChild(panel);

        state.toggle = toggle;
        state.panel = panel;
        state.body = panel.querySelector('#asLibBody');

        toggle.addEventListener('click', (e) => { if (suppressClick) { suppressClick = false; return; } open(); });
        panel.querySelector('#asLibClose').addEventListener('click', close);
        panel.querySelector('#asLibRefresh').addEventListener('click', () => { state.loaded = false; load(); });

        bindDrag(toggle);
        placeToggle();
        window.addEventListener('resize', () => { if (!readSaved()) placeToggle(); });
    }

    /* ---------- 定位：默认与左侧「角度控制」对齐，可拖动，双击复位 ---------- */
    let suppressClick = false;

    function readSaved() {
        const v = parseFloat(localStorage.getItem(LS_KEY) || '');
        return (isFinite(v) && v > 0 && v < 1) ? v : 0;
    }

    // 在父页面（画布）里找「角度控制」导航项，把它的中心 Y 换算到本 iframe 坐标
    function navAnchorY() {
        try {
            const frame = window.frameElement;
            if (!frame) return null;
            const pdoc = window.parent.document;
            let nav = pdoc.querySelector('[data-i18n="nav.angle"]');
            if (!nav) {
                const list = pdoc.querySelectorAll('.nav-text');
                for (let i = 0; i < list.length; i++) {
                    if ((list[i].textContent || '').trim() === '角度控制') { nav = list[i]; break; }
                }
            }
            if (!nav) return null;
            const navRect = nav.getBoundingClientRect();
            const frameRect = frame.getBoundingClientRect();
            if (!frameRect.height || !navRect.height) return null;
            const scale = frameRect.height / (frame.clientHeight || frameRect.height);
            const y = (navRect.top + navRect.height / 2 - frameRect.top) / (scale || 1);
            return (isFinite(y) && y > 40) ? y : null;
        } catch (_) { return null; }
    }

    function placeToggle() {
        const toggle = state.toggle;
        if (!toggle) return;
        const saved = readSaved();
        const top = saved ? Math.round(saved * window.innerHeight)
            : (navAnchorY() || Math.round(window.innerHeight * 0.34));
        toggle.style.top = top + 'px';
        toggle.style.transform = 'translateY(-50%)';
        toggle.title = '素材库\n拖动可换位置，双击复位到角度控制对齐';
    }

    function bindDrag(toggle) {
        let dragging = false, moved = false, startY = 0, startTop = 0;

        toggle.addEventListener('pointerdown', (e) => {
            if (state.panel.classList.contains('open')) return;
            dragging = true; moved = false;
            startY = e.clientY;
            startTop = parseFloat(toggle.style.top) || Math.round(window.innerHeight * 0.34);
            try { toggle.setPointerCapture(e.pointerId); } catch (_) { }
        });

        toggle.addEventListener('pointermove', (e) => {
            if (!dragging) return;
            const dy = e.clientY - startY;
            if (!moved && Math.abs(dy) < 4) return;
            moved = true;
            const top = Math.min(Math.max(28, startTop + dy), window.innerHeight - 28);
            toggle.style.top = top + 'px';
        });

        const end = (e) => {
            if (!dragging) return;
            dragging = false;
            try { toggle.releasePointerCapture(e.pointerId); } catch (_) { }
            if (moved) {
                suppressClick = true;
                const top = parseFloat(toggle.style.top) || Math.round(window.innerHeight * 0.34);
                try { localStorage.setItem(LS_KEY, (top / window.innerHeight).toFixed(4)); } catch (_) { }
            }
        };
        toggle.addEventListener('pointerup', end);
        toggle.addEventListener('pointercancel', end);

        toggle.addEventListener('dblclick', (e) => {
            e.preventDefault();
            try { localStorage.removeItem(LS_KEY); } catch (_) { }
            placeToggle();
            toast('已复位：与左侧「角度控制」对齐', true);
        });
    }

    function open() {
        state.panel.classList.add('open');
        state.toggle.style.display = 'none';
        load();
    }

    function close() {
        state.panel.classList.remove('open');
        state.toggle.style.display = '';
    }

    function itemEl(item) {
        const el = document.createElement('div');
        el.className = 'as-lib-item';
        el.draggable = true;
        el.title = (item.name || '') + '\n拖到图片框，或点击选用';

        const img = document.createElement('img');
        img.src = item.url;
        img.alt = item.name || '';
        img.loading = 'lazy';
        el.appendChild(img);

        const cap = document.createElement('div');
        cap.className = 'as-lib-name';
        cap.textContent = item.name || '';
        el.appendChild(cap);

        el.addEventListener('dragstart', (e) => {
            e.dataTransfer.effectAllowed = 'copy';
            try {
                e.dataTransfer.setData('application/x-asset-url', item.url);
                e.dataTransfer.setData('text/uri-list', item.url);
                e.dataTransfer.setData('text/plain', item.url);
            } catch (_) { }
        });
        el.addEventListener('click', () => useItem(item));
        return el;
    }

    function render(library) {
        const body = state.body;
        body.innerHTML = '';
        const libs = (library && library.libraries) || [];
        let total = 0;

        libs.forEach((lib) => {
            (lib.categories || []).forEach((cat) => {
                const items = (cat.items || []).filter((it) => {
                    const u = String(it.url || '');
                    return it.kind === 'image' || /\.(png|jpe?g|webp|gif|bmp)$/i.test(u.split('?')[0]);
                });
                if (!items.length) return;
                total += items.length;

                const h = document.createElement('div');
                h.className = 'as-lib-cat';
                h.textContent = (cat.name || '未分类') + ' · ' + items.length;
                body.appendChild(h);

                const grid = document.createElement('div');
                grid.className = 'as-lib-grid';
                items.forEach((it) => grid.appendChild(itemEl(it)));
                body.appendChild(grid);
            });
        });

        if (!total) {
            body.innerHTML = '<div class="as-lib-empty">素材库还是空的<br>先去生成几张图，或上传素材</div>';
        }
        state.loaded = true;
    }

    async function load() {
        if (state.loading) return;
        state.loading = true;
        state.body.innerHTML = '<div class="as-lib-spin"></div>';
        try {
            const res = await fetch('/api/asset-library', { cache: 'no-store' });
            if (!res.ok) throw new Error('HTTP ' + res.status);
            const data = await res.json();
            render(data.library || data);
        } catch (err) {
            state.body.innerHTML = '<div class="as-lib-empty">读取素材库失败<br>' + (err.message || err) + '</div>';
        } finally {
            state.loading = false;
        }
    }

    async function useItem(item) {
        if (!item || !item.url) return;
        if (typeof state.opts.onUse !== 'function') {
            toast('当前页面不支持直接选用，请拖拽', false);
            return;
        }
        toast('正在读取素材…', true);
        try {
            await useUrl(item.url, state.opts.onUse);
            toast('已选用：' + (item.name || ''), true);
        } catch (err) {
            toast('读取素材失败：' + (err.message || err), false);
        }
    }

    // 把素材 URL 拉成 File 交给回调（点选与拖放共用）
    async function useUrl(url, cb) {
        if (!url) throw new Error('没有拿到素材地址');
        const res = await fetch(url);
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const blob = await res.blob();
        const name = decodeURIComponent(String(url).split('?')[0].split('/').pop() || 'asset.png');
        const file = new File([blob], name, { type: blob.type || 'image/png' });
        return cb(file);
    }

    // 从拖放事件里取素材地址（dragover 阶段浏览器不允许读，只有 drop 时能读到）
    function assetUrlFrom(e) {
        const dt = e && e.dataTransfer;
        if (!dt) return '';
        let url = '';
        ['application/x-asset-url', 'text/uri-list', 'text/plain'].forEach((k) => {
            if (url) return;
            try { url = dt.getData(k) || ''; } catch (_) { }
        });
        url = String(url).split('\n')[0].trim();
        return /^\/(assets|output)\//.test(url) ? url : '';
    }

    window.AssetSidebar = {
        mount(opts) {
            state.opts = opts || {};
            build();
            if (state.opts.hint) {
                const h = state.panel.querySelector('#asLibHint');
                if (h) h.textContent = state.opts.hint;
            }
            // 支持 ?lib=1 直接展开
            if (/[?&]lib=1\b/.test(location.search)) setTimeout(open, 250);
            return window.AssetSidebar;
        },
        open,
        close,
        refresh() { state.loaded = false; load(); },
        useUrl,
        assetUrlFrom,
        // 给页面的拖放目标用：拿到素材就交给 cb，否则返回 false
        dropTo(e, cb) {
            const url = assetUrlFrom(e);
            if (!url) return false;
            useUrl(url, cb).catch((err) => toast('读取素材失败：' + (err.message || err), false));
            return true;
        }
    };
})();
