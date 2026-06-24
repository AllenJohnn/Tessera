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
    const clearFilesBtn = document.getElementById('clear-files-btn');
    const peersGrid = document.getElementById('peers-grid');
    const textStreamContainer = document.getElementById('text-stream-container');
    const displayNameField = document.getElementById('display-name');
    const editNameBtn = document.getElementById('edit-name-btn');
    const clearTextsBtn = document.getElementById('clear-texts-btn');
    const resetInputBtn = document.getElementById('reset-input-btn');

    let selectedPeerIp = null;
    let activeChannelSlot = "SLOT_01";
    let channelTimestamps = { "SLOT_01": 0, "SLOT_02": 0, "SLOT_03": 0 };
    let sessionCallsign = "";
    let sessionDeviceId = "";

    const safeStorage = {
        getItem: (key) => {
            try {
                return localStorage.getItem(key);
            } catch (e) {
                console.warn(`Failed to read from localStorage: ${e}`);
                return null;
            }
        },
        setItem: (key, value) => {
            try {
                localStorage.setItem(key, value);
            } catch (e) {
                console.warn(`Failed to write to localStorage: ${e}`);
            }
        }
    };

    sessionCallsign = safeStorage.getItem('tessera_callsign') || "";
    sessionDeviceId = safeStorage.getItem('tessera_device_id') || "";

    if (sessionDeviceId === "null" || sessionDeviceId === "undefined") {
        sessionDeviceId = "";
    }
    if (sessionCallsign === "null" || sessionCallsign === "undefined") {
        sessionCallsign = "";
    }

    if (!sessionDeviceId) {
        sessionDeviceId = 'dev_' + Math.random().toString(36).substring(2, 15) + Math.random().toString(36).substring(2, 15);
        safeStorage.setItem('tessera_device_id', sessionDeviceId);
    }

    // SECURITY ENHANCEMENT: Enforce strict HTML entity sanitization context to completely neutralize XSS payloads
    function escapeHTML(str) {
        if (!str) return '';
        return str.replace(/&/g, '&amp;')
                  .replace(/</g, '&lt;')
                  .replace(/>/g, '&gt;')
                  .replace(/"/g, '&quot;')
                  .replace(/'/g, '&#x27;');
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

    function flashSectionBorder(sectionId) {
        const targetSection = document.getElementById(sectionId);
        if (!targetSection) return;
        targetSection.style.transition = 'border-color 800ms cubic-bezier(0.16, 1, 0.3, 1)';
        targetSection.style.borderColor = '#10b981';
        setTimeout(() => { targetSection.style.borderColor = '#1c1c1c'; }, 800);
    }

    function compileBrutalistProgressBar(percent) {
        const totalBlocks = 10;
        const filledCount = Math.round((percent / 100) * totalBlocks);
        return `[${'█'.repeat(filledCount)}${'░'.repeat(totalBlocks - filledCount)}]`;
    }

    document.querySelectorAll('.slot-toggle-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            document.querySelectorAll('.slot-toggle-btn').forEach(b => {
                b.classList.remove('border-white', 'text-white', 'bg-neutral-900');
                b.classList.add('border-neutral-900', 'text-neutral-600');
            });
            this.classList.remove('border-neutral-900', 'text-neutral-600');
            this.classList.add('border-white', 'text-white', 'bg-neutral-900');
            
            activeChannelSlot = this.getAttribute('data-slot');
            showToast(`channel focus: ${activeChannelSlot}`);
            textStreamContainer.innerHTML = `<p class="text-[10px] text-neutral-600 uppercase tracking-wider py-1 mono empty-stream-msg">Synchronizing channel logs...</p>`;
            channelTimestamps[activeChannelSlot] = 0; 
            checkIncomingTextStreams();
        });
    });

    async function broadcastMobilePresence() {
        try {
            const response = await fetch('/api/ping', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ "hostname": sessionCallsign, "device_id": sessionDeviceId })
            });
            if (response.ok) {
                const data = await response.json();
                if (data.device_id && !sessionDeviceId) {
                    sessionDeviceId = data.device_id;
                    safeStorage.setItem('tessera_device_id', sessionDeviceId);
                }
                if (!sessionCallsign && data.assigned_name) {
                    sessionCallsign = data.assigned_name;
                    safeStorage.setItem('tessera_callsign', sessionCallsign);
                }
                if (displayNameField) displayNameField.textContent = escapeHTML(sessionCallsign);
            }
        } catch (err) { console.error("Presence fault"); }
    }

    async function queryLiveNetworkPeers() {
        try {
            const response = await fetch('/api/peers');
            if (!response.ok) return;
            const peers = await response.json();
            const peerEntries = Object.entries(peers).filter(([devId]) => devId !== sessionDeviceId);
            
            if (peerEntries.length === 0) {
                peersGrid.innerHTML = `<div class="col-span-1 sm:col-span-2 border border-neutral-900 p-4 text-center bg-[#070707] w-full"><p class="text-[10px] text-neutral-600 uppercase tracking-wider mono">WAITING FOR PEER DEVICES...</p></div>`;
                selectedPeerIp = null;
                return;
            }

            peersGrid.innerHTML = peerEntries.map(([devId, data]) => {
                const isSelected = selectedPeerIp === devId;
                const nodeLabel = `// ${escapeHTML(data.hostname).toUpperCase()}`;
                const statusLabel = 'ONLINE';
                const statusColor = 'text-emerald-400';
                const indicatorDot = `<span class="h-1 w-1 bg-emerald-400 rounded-full shadow-[0_0_8px_#10b981]"></span>`;

                return `
                    <div data-id="${devId}" class="peer-card border ${isSelected ? 'border-white bg-neutral-900/40' : 'border-neutral-900 bg-[#070707]'} p-3 flex justify-between items-center rounded-none select-none cursor-pointer hover:border-neutral-500 transition duration-100">
                        <span class="text-xs font-medium text-neutral-300 mono tracking-wider">${nodeLabel}</span>
                        <div class="flex items-center gap-2">
                            ${indicatorDot}
                            <span class="text-[9px] font-bold ${statusColor} tracking-widest uppercase mono">${statusLabel}</span>
                        </div>
                    </div>`;
            }).join('');

            document.querySelectorAll('.peer-card').forEach(card => {
                card.addEventListener('click', () => {
                    const targetId = card.getAttribute('data-id');
                    selectedPeerIp = (selectedPeerIp === targetId) ? null : targetId;
                    queryLiveNetworkPeers();
                    showToast(selectedPeerIp ? `route locked: ${selectedPeerIp}` : 'route: local storage');
                });
            });
        } catch (err) { console.error(err); }
    }

    async function loadAvailableFiles() {
        try {
            const response = await fetch('/api/files');
            if (!response.ok) return;
            const files = await response.json();
            
            if (files.length === 0) {
                filesList.innerHTML = `<p class="text-[10px] text-neutral-600 uppercase tracking-wider py-1" id="history-fallback">NO TRANSFERS TRACKED YET</p>`;
                return;
            }

            filesList.innerHTML = files.map(file => `
                <div class="flex items-center justify-between bg-[#070707] p-3 border border-neutral-900 hover:border-neutral-800 transition duration-100">
                    <div class="truncate max-w-[72%]">
                        <a href="/storage/${encodeURIComponent(file.name)}" class="text-neutral-300 text-xs truncate font-medium hover:text-white block" download>${escapeHTML(file.name)}</a>
                        <div class="flex items-center gap-3 text-[10px] text-neutral-600 mono mt-1">
                            <span>${escapeHTML(file.size)}</span>
                            <span class="text-amber-500/80 font-semibold select-none">${escapeHTML(file.ttl)}</span>
                        </div>
                    </div>
                    <a href="/storage/${encodeURIComponent(file.name)}" class="text-[9px] font-bold tracking-widest px-2.5 py-1.5 border border-neutral-800 text-neutral-400 hover:border-white hover:text-white transition duration-100 uppercase" download>GET</a>
                </div>`).join('');
        } catch (err) { console.error(err); }
    }

    async function checkIncomingTextStreams() {
        if (!textStreamContainer) return;
        try {
            const response = await fetch(`/api/clipboard/get?slot=${activeChannelSlot}`);
            if (!response.ok) return;
            const data = await response.json();

            if (data && data.content && data.timestamp > channelTimestamps[activeChannelSlot]) {
                channelTimestamps[activeChannelSlot] = data.timestamp;
                const emptyMsg = textStreamContainer.querySelector('.empty-stream-msg');
                if (emptyMsg) emptyMsg.remove();

                const textRow = document.createElement('div');
                textRow.className = "flex items-center justify-between bg-[#070707] p-3 border border-neutral-900 hover:border-neutral-800 transition duration-100 animate-fade-in";
                
                // SECURITY ENHANCEMENT: Enforce escaping parameters on dynamic text inserts
                const sanitizedContent = escapeHTML(data.content);
                const displayText = sanitizedContent.length > 40 ? sanitizedContent.substring(0, 40) + "..." : sanitizedContent;
                const senderTag = escapeHTML(data.sender).toUpperCase();

                textRow.innerHTML = `
                    <div class="truncate max-w-[72%]">
                        <p class="text-neutral-300 text-xs font-medium break-all select-all">${displayText}</p>
                        <p class="text-[9px] text-neutral-500 mono mt-1 uppercase tracking-wide">CH_${activeChannelSlot.split('_')[1]} // FROM // ${senderTag}</p>
                    </div>
                    <button type="button" class="copy-stream-btn text-[9px] font-bold tracking-widest px-2.5 py-1.5 border border-neutral-800 text-neutral-400 hover:border-white hover:text-white hover:bg-white hover:text-black transition duration-100 uppercase cursor-pointer" data-raw="${encodeURIComponent(data.content)}">COPY</button>`;

                textRow.querySelector('.copy-stream-btn').addEventListener('click', function() {
                    const rawContent = decodeURIComponent(this.getAttribute('data-raw'));
                    navigator.clipboard.writeText(rawContent).then(() => {
                        this.innerText = "COPIED!";
                        flashSectionBorder('received-streams-section');
                        setTimeout(() => this.innerText = "COPY", 1500);
                    }).catch(() => showToast('browser copy blocked', true));
                });

                textStreamContainer.insertBefore(textRow, textStreamContainer.firstChild);
                flashSectionBorder('received-streams-section');
            } else if (!data.content && textStreamContainer.querySelector('.empty-stream-msg')) {
                textStreamContainer.innerHTML = `<p class="text-[10px] text-neutral-600 uppercase tracking-wider py-1 mono empty-stream-msg">Channel ${activeChannelSlot.split('_')[1]} buffer stream empty...</p>`;
            }
        } catch (err) { console.error(err); }
    }

    if (editNameBtn) {
        editNameBtn.addEventListener('click', () => {
            const currentName = sessionCallsign || "ASSIGNING...";
            const inputPrompt = prompt("ENTER NEW STATION CALLSIGN:", currentName);
            if (inputPrompt !== null) {
                const sanitizedInput = inputPrompt.trim().replace(/[^a-zA-Z0-9-_ ]/g, "").toUpperCase();
                if (!sanitizedInput) {
                    showToast('Invalid station callsign input', true);
                    return;
                }
                sessionCallsign = sanitizedInput;
                safeStorage.setItem('tessera_callsign', sessionCallsign);
                if (displayNameField) displayNameField.textContent = escapeHTML(sessionCallsign);
                showToast(`callsign assigned: ${sessionCallsign}`);
                broadcastMobilePresence(); 
            }
        });
    }

    if (clearTextsBtn) {
        clearTextsBtn.addEventListener('click', () => {
            if (textStreamContainer) {
                textStreamContainer.innerHTML = `<p class="text-[10px] text-neutral-600 uppercase tracking-wider py-1 mono empty-stream-msg">No incoming text logs tracked...</p>`;
                showToast('text feed cleared');
            }
        });
    }

    if (resetInputBtn) {
        resetInputBtn.addEventListener('click', () => {
            if (clipboardInput) {
                clipboardInput.value = '';
                showToast('input buffer cleared');
            }
        });
    }

    clearFilesBtn.addEventListener('click', async () => {
        if (!confirm("CONFIRM COMMAND: PURGE ALL FILES INSIDE REPOSITORY HISTORIES?")) return;
        try {
            const response = await fetch('/api/clear_files', { method: 'POST' });
            if (response.ok) {
                showToast('storage wiped clean');
                loadAvailableFiles();
            } else { showToast('clear execution failed', true); }
        } catch (err) { showToast('communication exception', true); }
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
                body: JSON.stringify({ content, slot: activeChannelSlot, device_id: sessionDeviceId })
            });
            if (response.ok) {
                clipboardInput.value = '';
                flashSectionBorder('clipboard-sync-section');
                await checkIncomingTextStreams();
            } else { showToast('sync channel fault', true); }
        } catch (err) { showToast('communication error', true); }
    });

    dropZone.addEventListener('click', () => fileElement.click());
    fileElement.addEventListener('change', () => {
        if (fileElement.files.length > 0) { handleFileUpload(fileElement.files[0]); }
    });

    function handleFileUpload(file) {
        if (selectedPeerIp) {
            progressContainer.classList.remove('hidden');
            statusText.textContent = `SENDING CHUNKS VIA RAW SOCKET PIPELINES...`;
            progressBar.style.width = '0%';
            progressPercent.textContent = '0%';

            const formData = new FormData();
            formData.append('file', file);
            formData.append('device_id', sessionDeviceId);
            formData.append('target_peer', selectedPeerIp);

            const clientRequest = new XMLHttpRequest();
            clientRequest.open('POST', '/api/send_peer', true);

            clientRequest.upload.addEventListener('progress', (e) => {
                if (e.lengthComputable) {
                    const percent = Math.round((e.loaded / e.total) * 100);
                    statusText.textContent = `SENDING... ${compileBrutalistProgressBar(percent)}`;
                    progressBar.style.width = `${percent}%`;
                    progressPercent.textContent = `${percent}%`;
                }
            });

            clientRequest.onload = () => {
                if (clientRequest.status === 200) {
                    flashSectionBorder('file-transfer-section');
                    statusText.textContent = "COMPLETE";
                    loadAvailableFiles();
                } else {
                    let errorMessage = 'peer stream error';
                    try {
                        const responseData = JSON.parse(clientRequest.responseText || '{}');
                        errorMessage = responseData.error || errorMessage;
                    } catch (e) {}
                    showToast(errorMessage, true);
                }
                setTimeout(() => progressContainer.classList.add('hidden'), 2000);
                fileElement.value = ''; 
            };
            clientRequest.send(formData);
            return;
        }

        const formData = new FormData();
        formData.append('file', file);
        formData.append('device_id', sessionDeviceId);

        progressContainer.classList.remove('hidden');
        statusText.textContent = "UPLOADING... [░░░░░░░░░░]";
        progressBar.style.width = '0%';
        progressPercent.textContent = '0%';

        const clientRequest = new XMLHttpRequest();
        clientRequest.open('POST', '/api/upload', true);

        clientRequest.upload.addEventListener('progress', (e) => {
            if (e.lengthComputable) {
                const percent = Math.round((e.loaded / e.total) * 100);
                statusText.textContent = `UPLOADING... ${compileBrutalistProgressBar(percent)}`;
                progressBar.style.width = `${percent}%`;
                progressPercent.textContent = `${percent}%`;
            }
        });

        clientRequest.onload = () => {
            if (clientRequest.status === 200) {
                flashSectionBorder('file-transfer-section');
                statusText.textContent = "COMPLETE";
                loadAvailableFiles();
            } else {
                let errorMessage = 'pipeline channel crash';
                try {
                    const responseData = JSON.parse(clientRequest.responseText || '{}');
                    errorMessage = responseData.error || errorMessage;
                } catch (e) {}
                showToast(errorMessage, true);
            }
            setTimeout(() => progressContainer.classList.add('hidden'), 2000);
            fileElement.value = ''; 
        };
        clientRequest.send(formData);
    }

    async function initTessera() {
        await broadcastMobilePresence(); 
        await queryLiveNetworkPeers();   
        await loadAvailableFiles();      
        await checkIncomingTextStreams(); 
        
        setInterval(broadcastMobilePresence, 4000);
        setInterval(queryLiveNetworkPeers, 4000);
        setInterval(loadAvailableFiles, 10000);
        setInterval(checkIncomingTextStreams, 2000); 
    }

    initTessera();
});