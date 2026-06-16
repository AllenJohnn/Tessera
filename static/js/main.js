document.addEventListener('DOMContentLoaded', () => {
    const clipboardInput = document.getElementById('clipboard-input');
    const syncTextBtn = document.getElementById('sync-text-btn');
    const dropZone = document.getElementById('drop-zone');
    const fileElement = document.getElementById('file-element');
    const progressContainer = document.getElementById('progress-container');
    const progressBar = document.getElementById('progress-bar');
    const progressPercent = document.getElementById('progress-percent');
    const statusText = document.getElementById('status-text');
    
    const filesList = document.getElementById('files-list');
    const refreshFilesBtn = document.getElementById('refresh-files-btn');
    const clearFilesBtn = document.getElementById('clear-files-btn'); // New element binding
    const nodeIpDisplay = document.getElementById('node-ip');
    const peersGrid = document.getElementById('peers-grid');

    let selectedPeerIp = null;

    const dynamicDeviceName = (window.innerWidth < 640) ? "Mobile Phone" : "Laptop Client";

    if (nodeIpDisplay) {
        nodeIpDisplay.textContent = window.location.hostname;
    }

    function showToast(message, isError = false) {
        const toast = document.getElementById('toast');
        toast.textContent = message.toUpperCase();
        toast.style.borderColor = isError ? '#551111' : '#2c2c2c';
        toast.style.transform = 'translateY(0)';
        toast.style.opacity = '1';
        
        setTimeout(() => {
            toast.style.transform = 'translateY(20px)';
            toast.style.opacity = '0';
        }, 3000);
    }

    // Ping background server registry
    async function broadcastMobilePresence() {
        try {
            await fetch('/api/ping', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ "hostname": dynamicDeviceName })
            });
        } catch (err) {
            console.error("Presence beacon dropped");
        }
    }

    // Pull network map from endpoint cache
    async function queryLiveNetworkPeers() {
        try {
            const response = await fetch('/api/peers');
            if (!response.ok) return;
            const peers = await response.json();
            const peerEntries = Object.entries(peers);
            
            if (peerEntries.length === 0) {
                peersGrid.innerHTML = `
                    <div class="col-span-2 border border-[#1c1c1c] p-4 text-center bg-[#070707]">
                        <p class="text-[10px] text-neutral-600 italic mono uppercase tracking-wider">NO DEVICES DETECTED</p>
                    </div>`;
                selectedPeerIp = null;
                return;
            }

            peersGrid.innerHTML = peerEntries.map(([ip, data]) => {
                const isSelected = selectedPeerIp === ip;
                return `
                    <div data-ip="${ip}" class="peer-card border ${isSelected ? 'border-white bg-neutral-900/40' : 'border-[#1c1c1c] bg-[#070707]'} p-3.5 cursor-pointer hover:border-neutral-500 transition duration-100 flex items-center justify-between">
                        <div class="truncate">
                            <p class="text-xs font-semibold tracking-tight truncate ${isSelected ? 'text-white' : 'text-neutral-400'}">${data.hostname}</p>
                            <p class="text-[10px] text-neutral-600 mono mt-1">${ip} // ${data.type.toUpperCase()}</p>
                        </div>
                        <div class="h-2 w-2 rounded-none border ${isSelected ? 'bg-white border-white' : 'border-neutral-800'} shrink-0"></div>
                    </div>
                `;
            }).join('');

            document.querySelectorAll('.peer-card').forEach(card => {
                card.addEventListener('click', () => {
                    const targetIp = card.getAttribute('data-ip');
                    selectedPeerIp = (selectedPeerIp === targetIp) ? null : targetIp;
                    queryLiveNetworkPeers();
                    showToast(selectedPeerIp ? `route locked: ${selectedPeerIp}` : 'route: local storage');
                });
            });
        } catch (err) {
            console.error(err);
        }
    }

    // Pull direct local workspace storage indices
    async function loadAvailableFiles() {
        try {
            const response = await fetch('/api/files');
            if (!response.ok) return;
            const files = await response.json();
            
            if (files.length === 0) {
                filesList.innerHTML = `<p class="text-[10px] text-neutral-600 italic py-3 uppercase tracking-wider">HISTORY EMPTY</p>`;
                return;
            }

            filesList.innerHTML = files.map(file => `
                <div class="flex items-center justify-between bg-[#070707] p-3 border border-[#1c1c1c] hover:border-neutral-800 transition duration-100">
                    <div class="truncate max-w-[72%]">
                        <a href="/storage/${encodeURIComponent(file.name)}" class="text-neutral-300 text-xs truncate font-medium hover:text-white block" download>${file.name}</a>
                        <p class="text-[10px] text-neutral-600 mono mt-1">${file.size}</p>
                    </div>
                    <a href="/storage/${encodeURIComponent(file.name)}" class="text-[9px] font-bold tracking-widest px-2.5 py-1.5 border border-neutral-800 text-neutral-400 hover:border-white hover:text-white transition duration-100 uppercase" download>GET</a>
                </div>
            `).join('');
        } catch (err) {
            console.error(err);
        }
    }

    // ADDED: Clear action dispatcher pipeline hook
    clearFilesBtn.addEventListener('click', async () => {
        if (!confirm("CONFIRM COMMAND: PURGE ALL FILES INSIDE REPOSITORY HISTORIES?")) return;
        try {
            const response = await fetch('/api/clear_files', { method: 'POST' });
            if (response.ok) {
                showToast('storage wiped clean');
                loadAvailableFiles();
            } else {
                showToast('clear execution failed', true);
            }
        } catch (err) {
            showToast('communication exception', true);
        }
    });

    refreshFilesBtn.addEventListener('click', loadAvailableFiles);

    syncTextBtn.addEventListener('click', async (e) => {
        e.preventDefault(); 
        const content = clipboardInput.value.trim();
        if (!content) return showToast('Buffer input empty.', true);

        try {
            const response = await fetch('/api/clipboard', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content })
            });
            if (response.ok) {
                showToast('clipboard updated');
                clipboardInput.value = '';
            } else {
                showToast('sync channel fault', true);
            }
        } catch (err) {
            showToast('communication error', true);
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
            statusText.textContent = `SENDING DATA CHUNKS OVER RAW SOCKETS...`;
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
                    showToast('socket operation successful');
                    statusText.textContent = "COMPLETE";
                } else {
                    showToast('socket stream aborted', true);
                }
                setTimeout(() => progressContainer.classList.add('hidden'), 2000);
                loadAvailableFiles();
            });
            fileElement.value = '';
            return;
        }

        const formData = new FormData();
        formData.append('file', file);

        progressContainer.classList.remove('hidden');
        statusText.textContent = "UPLOADING FILE BLOCKS TO SYSTEM DISK...";
        progressBar.style.width = '0%';
        progressPercent.textContent = '0%';

        const clientRequest = new XMLHttpRequest();
        clientRequest.open('POST', '/api/upload', true);

        clientRequest.upload.addEventListener('progress', (e) => {
            if (e.lengthComputable) {
                const percent = Math.round((e.loaded / e.total) * 100);
                progressBar.style.width = `${percent}%`;
                progressPercent.textContent = `${percent}%`;
            }
        });

        clientRequest.onload = () => {
            if (clientRequest.status === 200) {
                showToast('transfer complete');
                statusText.textContent = "COMPLETE";
                loadAvailableFiles();
            } else {
                showToast('pipeline channel crash', true);
            }
            setTimeout(() => progressContainer.classList.add('hidden'), 2000);
            fileElement.value = ''; 
        };
        clientRequest.send(formData);
    }

    // FIXED IMEDIATE EXECUTION RUNTIMES: Fires ping + fetch immediately to remove latency
    async function initTessera() {
        await broadcastMobilePresence(); // Register instantly
        await queryLiveNetworkPeers();   // Load data matrix instantly
        await loadAvailableFiles();      // Fetch list instantly
        
        // Fallback polling interval clocks setup afterward
        setInterval(broadcastMobilePresence, 4000);
        setInterval(queryLiveNetworkPeers, 4000);
    }

    initTessera();
});