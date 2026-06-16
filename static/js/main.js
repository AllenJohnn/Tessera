document.addEventListener('DOMContentLoaded', () => {
    const clipboardInput = document.getElementById('clipboard-input');
    const syncTextBtn = document.getElementById('sync-text-btn');
    const dropZone = document.getElementById('drop-zone');
    const fileElement = document.getElementById('file-element');
    const progressContainer = document.getElementById('progress-container');
    const progressBar = document.getElementById('progress-bar');
    const progressPercent = document.getElementById('progress-percent');
    const statusText = document.getElementById('status-text');
    
    // History UI hooks
    const historyList = document.getElementById('history-list');
    const refreshHistoryBtn = document.getElementById('refresh-history-btn');

    function showToast(message, isError = false) {
        const toast = document.getElementById('toast');
        toast.textContent = message;
        toast.className = `fixed bottom-5 text-white font-medium text-sm px-6 py-3 rounded-xl shadow-2xl transition-all duration-300 ${isError ? 'bg-rose-600' : 'bg-emerald-600'}`;
        toast.style.transform = 'translateY(0)';
        toast.style.opacity = '1';
        
        setTimeout(() => {
            toast.style.transform = 'translateY(20px)';
            toast.style.opacity = '0';
        }, 3000);
    }

    // NEW FEATURE: Fetch and build the transfer history logs from SQLite
    async function loadTransferHistory() {
        try {
            const response = await fetch('/api/history');
            if (!response.ok) return;
            const history = await response.json();
            
            if (history.length === 0) {
                historyList.innerHTML = `<p class="text-xs text-slate-500 italic">No transfers logged yet.</p>`;
                return;
            }

            historyList.innerHTML = history.map(item => `
                <div class="flex justify-between items-center bg-slate-900/60 p-2.5 rounded-xl border border-slate-700/30">
                    <div class="truncate max-w-[70%]">
                        <p class="text-slate-200 font-medium text-xs truncate">${item.filename}</p>
                        <p class="text-[10px] text-slate-500">${item.peer_ip}</p>
                    </div>
                    <span class="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-md ${
                        item.status === 'completed' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-amber-500/10 text-amber-400'
                    }">${item.status}</span>
                </div>
            `).join('');
        } catch (err) {
            console.error('Failed to load history metrics:', err);
        }
    }

    // Attach load listener to refresh button
    refreshHistoryBtn.addEventListener('click', loadTransferHistory);

    // Process Text Commit Actions
    syncTextBtn.addEventListener('click', async () => {
        const content = clipboardInput.value.trim();
        if (!content) return showToast('Please write out content block first.', true);

        try {
            const response = await fetch('/api/clipboard', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content })
            });
            const data = await response.json();
            if (response.ok) {
                showToast(data.message);
                clipboardInput.value = '';
            } else {
                showToast(data.error || 'Interface Sync Execution Failed', true);
            }
        } catch (err) {
            showToast('Unable to talk to target host node daemon', true);
        }
    });

    dropZone.addEventListener('click', () => fileElement.click());
    fileElement.addEventListener('change', () => {
        if (fileElement.files.length > 0) {
            handleFileUpload(fileElement.files[0]);
        }
    });

    // Handle Network File IO Stream Ingestion using raw XHR trackers
    function handleFileUpload(file) {
        const formData = new FormData();
        formData.append('file', file);

        progressContainer.classList.remove('hidden');
        statusText.textContent = "Streaming packets...";
        progressBar.style.width = '0%';
        progressPercent.textContent = '0%';

        const xhr = new XMLHttpRequest();
        xhr.open('POST', '/api/upload', true);

        xhr.upload.addEventListener('progress', (e) => {
            if (e.lengthComputable) {
                const percent = Math.round((e.loaded / e.total) * 100);
                progressBar.style.width = `${percent}%`;
                progressPercent.textContent = `${percent}%`;
            }
        });

        xhr.onload = () => {
            if (xhr.status === 200) {
                const res = JSON.parse(xhr.responseText);
                showToast(res.message || 'Stream block finalized!');
                statusText.textContent = "Success!";
                // Reload dashboard logs on file upload completion event
                loadTransferHistory();
            } else {
                const err = JSON.parse(xhr.responseText);
                showToast(err.error || 'Stream execution interrupted', true);
                statusText.textContent = "Pipeline Error.";
            }
            setTimeout(() => progressContainer.classList.add('hidden'), 2000);
            fileElement.value = ''; 
        };

        xhr.onerror = () => {
            showToast('Local Area Interface encountered a socket execution fault', true);
            progressContainer.classList.add('hidden');
        };

        xhr.send(formData);
    }

    // Initial load call execution on application boot
    loadTransferHistory();
});