/**
 * Save Master —— 把预览中的生成结果保存到交付目录（后端 /api/save-master，默认 D:\AI-Work\交付成品）。
 * 服务端不可用时回退为浏览器下载，并且任何情况都会给出可见提示，不会静默失败。
 */
(function () {
    let toastEl = null;
    let hideTimer = null;

    function toast(text, ok) {
        if (!toastEl) {
            toastEl = document.createElement('div');
            toastEl.style.cssText = 'position:fixed;left:50%;bottom:34px;transform:translateX(-50%);z-index:99999;' +
                'max-width:82vw;padding:12px 20px;border-radius:999px;font-size:12px;font-weight:600;line-height:1.6;' +
                'box-shadow:0 10px 34px rgba(0,0,0,.22);transition:opacity .25s;color:#fff;' +
                'white-space:pre-wrap;word-break:break-all;pointer-events:none;';
            document.body.appendChild(toastEl);
        }
        toastEl.textContent = text;
        toastEl.style.background = ok ? 'rgba(17,17,17,.93)' : 'rgba(185,28,28,.95)';
        toastEl.style.opacity = '1';
        clearTimeout(hideTimer);
        if (ok && !/^正在/.test(text)) {
            hideTimer = setTimeout(function () { toastEl.style.opacity = '0'; }, 5600);
        }
    }

    // 把相对/绝对地址统一成本站路径（后端只接受 /assets 或 /output 下的文件）
    function toLocalPath(raw) {
        if (!raw) return '';
        try {
            const u = new URL(raw, location.origin);
            if (u.origin !== location.origin) return '';
            return u.pathname;
        } catch (e) {
            return '';
        }
    }

    async function save(rawUrl, opts) {
        const options = opts || {};
        const prefix = options.fallback || 'Master';
        const path = toLocalPath(rawUrl);
        if (!path) {
            toast('没有找到可保存的图片，请重新打开预览', false);
            return false;
        }
        const name = decodeURIComponent(path.split('/').pop() || 'master.png');

        toast('正在保存到交付目录…', true);
        try {
            const res = await fetch('/api/save-master', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: path, name: name })
            });
            let data = {};
            try { data = await res.json(); } catch (e) { }
            if (!res.ok) throw new Error(data.detail || ('HTTP ' + res.status));
            toast('已保存到：' + data.path, true);
            return true;
        } catch (err) {
            const reason = (err && err.message) ? err.message : String(err);
            try {
                const ext = (name.split('.').pop() || 'png').toLowerCase();
                const a = document.createElement('a');
                a.href = path;
                a.download = prefix + '-' + Date.now() + '.' + ext;
                document.body.appendChild(a);
                a.click();
                a.remove();
                toast('服务端保存失败（' + reason + '），已改为浏览器下载', false);
            } catch (e2) {
                toast('保存失败：' + reason, false);
            }
            return false;
        }
    }

    window.SaveMaster = { save: save, toast: toast, toLocalPath: toLocalPath };
})();
