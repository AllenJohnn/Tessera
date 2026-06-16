document.addEventListener('DOMContentLoaded', () => {
    const clipboardInput = document.getElementById('clipboard-input');
    const syncTextBtn = document.getElementById('sync-text-btn');
    const dropZone = document.getElementById('drop-zone');
    const fileElement = document.getElementById('file-element');
    const progressContainer = document.getElementById('progress-container');
    const progressBar = document.getElementById('progress-bar');
    const progressPercent = document.getElementById('progress-percent');
    const statusText = document.getElementById('status-text');

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
});