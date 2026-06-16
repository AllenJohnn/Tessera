document.addEventListener('DOMContentLoaded', () => {
    const clipboardInput = document.getElementById('clipboard-input');
    const syncTextBtn = document.getElementById('sync-text-btn');
    const dropZone = document.getElementById('drop-zone');
    const fileElement = document.getElementById('file-element');
    const progressContainer = document.getElementById('progress-container');
    const progressBar = document.getElementById('progress-bar');
    const progressPercent = document.getElementById('progress-percent');
    const statusText = document.getElementById('status-text');
    
    const historyList = document.getElementById('history-list');
    const refreshHistoryBtn = document.getElementById('refresh-history-btn');
    const nodeIpDisplay = document.getElementById('node-ip');
    const peersGrid = document.getElementById('peers-grid');

    let selectedPeerIp = null;

    if (nodeIpDisplay) {
        nodeIpDisplay.textContent = window.location.hostname;
    }

    // Stark Notification Banner Component
    function showToast(message, isError = false) {
        const toast = document.getElementById('toast');
        toast.textContent = message;
        toast.style.borderColor = isError ? '#551111' : '#333333';
        toast.style.transform = 'translateY(0)';
        toast.style.opacity = '1';
        
        setTimeout(() => {
            toast.style.transform = 'translateY(20px)';
            toast.style.opacity = '0';
        }, 3000);
    }

    // Queries local subnets and generates clean minimalist device selections
    async function queryLiveNetworkPeers() {
        try {
            const response = await fetch('/api/peers');
            if (!response.ok) return;
            const peers = await response.json();
            const peerEntries = Object.entries(peers);
            
            if (peerEntries.length === 0) {
                peersGrid.innerHTML = `
                    <div class="col-span-2 border border-[#222222] p-3 text-center bg-black">
                        <p class="text-[11px] text-neutral-600 italic mono">No active network nodes detected.</p>
                    </div>`;
                selectedPeerIp = null;
                return;
            }

            peersGrid.innerHTML = peerEntries.map(([ip, data]) => {
                const isSelected = selectedPeerIp === ip;
                return `
                    <div data-ip="${ip}" class="peer-card border ${isSelected ? 'border-white bg-neutral-900' : 'border-[#222222] bg-black'} p-3 cursor-pointer hover:border-neutral-500 transition duration-100 flex items-center justify-between">
                        <div class="truncate">
                            <p class="text-xs font-medium tracking-tight truncate ${isSelected ? 'text-white' : 'text-neutral-300'}">${data.hostname}</p>
                            <p class="text-[10px] text-neutral-600 mono mt-0.5">${ip}</p>
                        </div>
                        <div class="h-2 w-2 rounded-none border ${isSelected ? 'bg-white border-white' : 'border-neutral-700'} shrink-0"></div>
                    </div>
                `;
            }).join('');

            document.querySelectorAll('.peer-card').forEach(card => {
                card.addEventListener('click', () => {
                    const targetIp = card.getAttribute('data-ip');
                    selectedPeerIp = (selectedPeerIp === targetIp) ? null : targetIp;
                    queryLiveNetworkPeers();
                    showToast(selectedPeerIp ? `route: ${selectedPeerIp}` : 'route: local drop folder');
                });
            });
        } catch (err) {
            console.error(err);
        }
    }

    // Maps recent transactions out to plain minimalist data cards
    async function loadTransferHistory() {
        try {
            const response = await fetch('/api/history');
            if (!response.ok) return;
            const history = await response.json();
            
            if (history.length === 0) {
                historyList.innerHTML = `<p class="text-[11px] text-neutral-600 italic py-4">No logged events.</p>`;
                return;
            }

            historyList.innerHTML = history.map(item => `
                <div class="flex items-center justify-between bg-black p-2.5 border border-[#222222]">
                    <div class="truncate max-w-[75%]">
                        <p class="text-neutral-200 text-xs truncate font-medium">${item.filename}</p>
                        <p class="text-[10px] text-neutral-600 mt-0.5">${item.peer_ip}</p>
                    </div>
                    <span class="text-[9px] uppercase font-bold tracking-wider px-1.5 py-0.5 border ${
                        item.status === 'completed' ? 'border-neutral-800 text-neutral-400' : 'border-amber-900 text-amber-500'
                    }">${item.status}</span>
                </div>
            `).join('');
        } catch (err) {
            console.error(err);
        }
    }

    refreshHistoryBtn.addEventListener('click', loadTransferHistory);

    // Text Sync Thread Dispatch Logic
    syncTextBtn.addEventListener('click', async (e) => {
        // ALWAYS STOP THE BROWSER FROM RELOADING THE PAGE RIGHT AWAY
        e.preventDefault(); 
        
        const content = clipboardInput.value.trim();
        if (!content) return showToast('Input text string block empty.', true);

        try {
            const response = await fetch('/api/clipboard', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content })
            });
            if (response.ok) {
                showToast('PC clipboard updated');
                clipboardInput.value = '';
            } else {
                showToast('Sync pipeline failed', true);
            }
        } catch (err) {
            showToast('Connection error', true);
        }
    });

    dropZone.addEventListener('click', () => fileElement.click());
    fileElement.addEventListener('change', () => {
        if (fileElement.files.length > 0) {
            handleFileUpload(fileElement.files[0]);
        }
    });

    function handleFileUpload(file) {
        if (selectedPeerIp) {
            progressContainer.classList.remove('hidden');
            statusText.textContent = `Pushing to remote node...`;
            progressBar.style.width = '100%';
            progressPercent.textContent = 'SOCKET';

            fetch('/api/send_peer', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ "target_ip": selectedPeerIp, "file_path": file.name })
            })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'success') {
                    showToast('Socket sync complete');
                    statusText.textContent = "Complete";
                } else {
                    showToast('Socket dropped', true);
                }
                setTimeout(() => progressContainer.classList.add('hidden'), 2000);
                loadTransferHistory();
            });
            fileElement.value = '';
            return;
        }

        const formData = new FormData();
        formData.append('file', file);

        progressContainer.classList.remove('hidden');
        statusText.textContent = "Streaming to local disk...";
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
                showToast('Drop folder stream finalized');
                statusText.textContent = "Complete";
                loadTransferHistory();
            } else {
                showToast('Pipeline crash', true);
            }
            setTimeout(() => progressContainer.classList.add('hidden'), 2000);
            fileElement.value = ''; 
        };
        xhr.send(formData);
    }

    loadTransferHistory();
    queryLiveNetworkPeers();
    setInterval(queryLiveNetworkPeers, 5000);

    const filesList = document.getElementById('files-list');
    const refreshFilesBtn = document.getElementById('refresh-files-btn');

    async function loadAvailableFiles() {
        try {
            const response = await fetch('/api/files');
            if (!response.ok) return;
            const files = await response.json();
            
            if (files.length === 0) {
                filesList.innerHTML = `<p class="text-[11px] text-neutral-600 italic py-4">No files in storage.</p>`;
                return;
            }

            filesList.innerHTML = files.map(file => `
                <div class="flex items-center justify-between bg-black p-2.5 border border-[#222222]">
                    <div class="truncate max-w-[70%]">
                        <a href="/storage/${encodeURIComponent(file.name)}" class="text-neutral-200 text-xs truncate font-medium hover:underline hover:text-blue-400" download>${file.name}</a>
                        <p class="text-[10px] text-neutral-600 mt-0.5">${file.size}</p>
                    </div>
                    <a href="/storage/${encodeURIComponent(file.name)}" class="text-[9px] uppercase font-bold tracking-wider px-1.5 py-0.5 border border-neutral-700 text-neutral-400 hover:border-white hover:text-white" download>GET</a>
                </div>
            `).join('');
        } catch (err) {
            console.error(err);
        }
    }

    refreshFilesBtn.addEventListener('click', loadAvailableFiles);
    // Call automatically on load
    loadAvailableFiles();
});