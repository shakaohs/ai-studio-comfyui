(function(){
    'use strict';

    /* 一次性注入预览框样式 —— 所有页面共用同一套外观 */
    function injectStyles(){
        if(document.getElementById('studio-image-preview-css')) return;
        const style = document.createElement('style');
        style.id = 'studio-image-preview-css';
        style.textContent = `
            .studio-preview-frame {
                position: relative;
                width: min(1280px, 92vw);
                height: min(820px, 78vh);
                max-width: 100%;
                border-radius: 24px;
                overflow: hidden;
                background: rgba(241,245,249,.72);
                border: 1px solid rgba(15,23,42,.08);
                box-shadow: 0 30px 90px rgba(15,23,42,.18);
                cursor: grab;
                user-select: none;
                touch-action: none;
            }
            .studio-preview-frame.panning { cursor: grabbing; }
            .studio-preview-frame.panning .studio-preview-img { transition: none; }
            .studio-preview-img {
                display: block;
                width: 100%;
                height: 100%;
                object-fit: contain;
                transition: transform .12s ease-out;
                transform-origin: 0 0;
                -webkit-user-drag: none;
                user-select: none;
                pointer-events: none;
                background: transparent;
            }
            html.theme-dark .studio-preview-frame,
            body.theme-dark .studio-preview-frame,
            .theme-dark .studio-preview-frame {
                background: #020617;
                border-color: rgba(148,163,184,.24);
                box-shadow: 0 30px 90px rgba(0,0,0,.45);
            }
        `;
        document.head.appendChild(style);
    }

    /**
     * 给一个容器绑定滚轮缩放 + 拖拽平移
     * @param {HTMLElement} container - 外框（必须 overflow:hidden）
     * @param {Object} [options]
     * @param {HTMLImageElement} [options.img] - 容器内的图片，默认取 .studio-preview-img 或第一个 img
     * @param {number} [options.minZoom=1]
     * @param {number} [options.maxZoom=6]
     * @returns {{reset:Function, apply:Function, getZoom:Function}|null}
     */
    function attach(container, options){
        if(!container) return null;
        options = options || {};
        const img = options.img
            || container.querySelector('.studio-preview-img')
            || container.querySelector('img');
        if(!img) return null;
        const minZoom = options.minZoom || 1;
        const maxZoom = options.maxZoom || 6;

        let zoom = 1;
        let pan = { x:0, y:0 };
        let drag = null;

        function apply(){
            img.style.transform = `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`;
            img.style.transformOrigin = '0 0';
        }
        function reset(){
            zoom = 1;
            pan = { x:0, y:0 };
            drag = null;
            container.classList.remove('panning');
            apply();
        }

        function onWheel(e){
            e.preventDefault();
            e.stopPropagation();
            const rect = container.getBoundingClientRect();
            const lx = e.clientX - rect.left;
            const ly = e.clientY - rect.top;
            const before = {
                x: (lx - pan.x) / zoom,
                y: (ly - pan.y) / zoom
            };
            const factor = e.deltaY > 0 ? 0.9 : 1.1;
            const nz = Math.max(minZoom, Math.min(maxZoom, zoom * factor));
            zoom = nz;
            pan = nz <= 1.001 ? { x:0, y:0 } : {
                x: lx - before.x * nz,
                y: ly - before.y * nz
            };
            apply();
        }

        function onDown(e){
            if(e.button !== 0 || zoom <= 1.001) return;
            if(e.target.closest('[data-no-pan], button, a, input, textarea')) return;
            drag = { sx:e.clientX, sy:e.clientY, ox:pan.x, oy:pan.y };
            container.classList.add('panning');
            e.preventDefault();
            e.stopPropagation();
        }
        function onMove(e){
            if(!drag) return;
            pan = {
                x: drag.ox + e.clientX - drag.sx,
                y: drag.oy + e.clientY - drag.sy
            };
            apply();
        }
        function onUp(){
            if(!drag) return;
            drag = null;
            container.classList.remove('panning');
        }

        /* 双击复位 —— 缩放后双击图片直接还原 */
        function onDblClick(e){
            if(zoom <= 1.001) return;
            e.preventDefault();
            e.stopPropagation();
            reset();
        }

        container.addEventListener('wheel', onWheel, { passive:false });
        container.addEventListener('mousedown', onDown);
        container.addEventListener('dblclick', onDblClick);
        window.addEventListener('mousemove', onMove);
        window.addEventListener('mouseup', onUp);

        return {
            reset,
            apply,
            getZoom: () => zoom
        };
    }

    /**
     * 把浮层（lightbox / 各种 fixed 弹层）挂到 <html> 下。
     *
     * 背景：theme.js 的「界面缩放」会给 body 加 transform:scale()，而 body 一旦有
     * transform 就会成为内部 position:fixed 的包含块 —— 浮层不再相对视口，而是相对
     * 整页高度定位：图片被垂直居中到页面中段（小屏要滚很久才看见），关闭键也会跟着漂。
     * 挂到 documentElement 下即可恢复真正的视口定位。
     *
     * @param {HTMLElement|string} target 元素或 id
     * @returns {HTMLElement|null}
     */
    function lift(target){
        const el = typeof target === 'string' ? document.getElementById(target) : target;
        if(!el) return null;
        if(el.parentElement !== document.documentElement){
            document.documentElement.appendChild(el);
        }
        return el;
    }

    /**
     * 给「左原图 / 右处理后」的分界对比框绑定：拖动分界 + 滚轮缩放 + 放大后拖动平移 + 双击复位。
     *
     * 与 attach() 的区别：对比框里有两张图，必须共用同一套 transform 才能保证放大后
     * 左右两侧仍然像素对齐；且放大状态下拖动要让位给平移，否则会把分界线拖乱。
     *
     * @param {Object} opts
     * @param {HTMLElement} opts.container 外层框（overflow:hidden）
     * @param {HTMLImageElement} opts.gen 右侧「处理后」图
     * @param {HTMLImageElement} opts.orig 左侧「原图」
     * @param {HTMLElement} [opts.wrapper] 原图的裁剪容器（clipPath 挂这里）
     * @param {HTMLElement} [opts.slider] 分界线
     * @param {HTMLElement} [opts.pill] 倍数角标
     * @param {number} [opts.maxZoom=8]
     * @returns {{reset:Function, apply:Function, getZoom:Function}|null}
     */
    function attachCompare(opts){
        opts = opts || {};
        const container = opts.container;
        if(!container) return null;

        const gen = opts.gen || null;
        const orig = opts.orig || null;
        const wrapper = opts.wrapper || null;
        const slider = opts.slider || null;
        const pill = opts.pill || null;
        const MAX_ZOOM = opts.maxZoom || 8;

        let zoom = 1, panX = 0, panY = 0;
        let isDragging = false, isPanning = false, panStart = null;

        if(gen) { gen.style.transformOrigin = '50% 50%'; gen.style.willChange = 'transform'; }
        if(orig) { orig.style.transformOrigin = '50% 50%'; orig.style.willChange = 'transform'; }

        function apply(){
            const t = 'translate(' + panX.toFixed(2) + 'px, ' + panY.toFixed(2) + 'px) scale(' + zoom.toFixed(4) + ')';
            if(gen) gen.style.transform = t;
            if(orig) orig.style.transform = t;   // 两图必须同变换，否则放大后左右对不上
            if(pill){
                pill.textContent = zoom.toFixed(1) + 'x';
                pill.style.opacity = zoom > 1.005 ? '1' : '0';
            }
            container.style.cursor = isPanning ? 'grabbing' : (zoom > 1.005 ? 'grab' : '');
        }

        function updateSlider(clientX){
            if(!slider || !wrapper) return;
            const rect = container.getBoundingClientRect();
            const percent = Math.max(0, Math.min(100, (clientX - rect.left) / rect.width * 100));
            wrapper.style.clipPath = 'inset(0 ' + (100 - percent) + '% 0 0)';
            slider.style.left = percent + '%';
        }

        // 平移上限按「图片 contain 后的实际显示尺寸」算，图比容器窄的方向直接锁 0，不拖出白边
        function clampPan(){
            const rect = container.getBoundingClientRect();
            let dispW = rect.width, dispH = rect.height;
            const nw = gen && gen.naturalWidth || 0, nh = gen && gen.naturalHeight || 0;
            if(nw && nh){
                const s = Math.min(rect.width / nw, rect.height / nh);
                dispW = nw * s;
                dispH = nh * s;
            }
            const lx = Math.max(0, (dispW * zoom - rect.width) / 2);
            const ly = Math.max(0, (dispH * zoom - rect.height) / 2);
            panX = Math.max(-lx, Math.min(lx, panX));
            panY = Math.max(-ly, Math.min(ly, panY));
        }

        function reset(){
            zoom = 1; panX = 0; panY = 0;
            isDragging = false; isPanning = false; panStart = null;
            apply();
        }

        container.addEventListener('wheel', function(e){
            if(container.classList.contains('hidden')) return;
            e.preventDefault();
            const rect = container.getBoundingClientRect();
            const cx = e.clientX - rect.left - rect.width / 2;
            const cy = e.clientY - rect.top - rect.height / 2;
            const next = Math.min(MAX_ZOOM, Math.max(1, zoom * (e.deltaY < 0 ? 1.12 : 1 / 1.12)));
            if(Math.abs(next - zoom) < 1e-4) return;
            const k = next / zoom;
            // 反向补偿平移，让光标下的那个像素缩放前后停在原地
            panX = cx - (cx - panX) * k;
            panY = cy - (cy - panY) * k;
            zoom = next;
            if(zoom <= 1.001){ zoom = 1; panX = 0; panY = 0; }
            clampPan();
            apply();
        }, { passive: false });

        container.addEventListener('dblclick', function(e){
            if(zoom <= 1.001) return;
            e.preventDefault();
            reset();
        });

        container.addEventListener('mousedown', function(e){
            if(e.detail >= 2) return;                                  // 双击留给复位
            if(slider && slider.contains(e.target)) return;             // 抓手柄/竖线只拖分界
            if(zoom > 1.005){                                          // 放大状态拖动 = 平移
                isPanning = true;
                panStart = { x: e.clientX, y: e.clientY, px: panX, py: panY };
                apply();
                e.preventDefault();
                return;
            }
            updateSlider(e.clientX);
            isDragging = true;
            e.preventDefault();
        });

        if(slider){
            slider.addEventListener('mousedown', function(e){ isDragging = true; e.preventDefault(); });
            slider.addEventListener('touchstart', function(e){ isDragging = true; e.preventDefault(); }, { passive: false });
        }

        container.addEventListener('touchstart', function(e){
            if(slider && slider.contains(e.target)) return;
            if(zoom > 1.005 && e.touches.length === 1){
                isPanning = true;
                panStart = { x: e.touches[0].clientX, y: e.touches[0].clientY, px: panX, py: panY };
                apply();
            }
        }, { passive: true });

        window.addEventListener('mousemove', function(e){
            if(isPanning && panStart){
                panX = panStart.px + (e.clientX - panStart.x);
                panY = panStart.py + (e.clientY - panStart.y);
                clampPan();
                apply();
                return;
            }
            if(isDragging) updateSlider(e.clientX);
        });

        window.addEventListener('touchmove', function(e){
            if(!e.touches.length) return;
            if(isPanning && panStart){
                panX = panStart.px + (e.touches[0].clientX - panStart.x);
                panY = panStart.py + (e.touches[0].clientY - panStart.y);
                clampPan();
                apply();
                return;
            }
            if(isDragging) updateSlider(e.touches[0].clientX);
        }, { passive: false });

        function onUp(){
            isDragging = false;
            if(isPanning){ isPanning = false; panStart = null; apply(); }
        }
        window.addEventListener('mouseup', onUp);
        window.addEventListener('touchend', onUp);

        return { reset: reset, apply: apply, getZoom: function(){ return zoom; } };
    }

    injectStyles();
    window.StudioImagePreview = { attach: attach, attachCompare: attachCompare, lift: lift };
})();
