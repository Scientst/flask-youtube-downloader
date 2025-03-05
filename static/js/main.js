document.addEventListener('DOMContentLoaded', () => {
    const videoForm = document.getElementById('videoForm');
    const downloadBtn = document.getElementById('downloadBtn');
    const downloadPlaylistBtn = document.getElementById('downloadPlaylistBtn');
    const formatSelect = document.getElementById('formatSelect');
    const qualitySelect = document.getElementById('qualitySelect');

    if (!videoForm || !downloadBtn || !downloadPlaylistBtn || !formatSelect || !qualitySelect) {
        console.error('One or more elements not found:', {
            videoForm, downloadBtn, downloadPlaylistBtn, formatSelect, qualitySelect
        });
    } else {
        console.log('All required elements found');
    }

    // Show/hide quality select based on format
    formatSelect.addEventListener('change', () => {
        if (formatSelect.value === 'mp4') {
            qualitySelect.classList.remove('hidden');
        } else {
            qualitySelect.classList.add('hidden');
        }
    });

    videoForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        console.log('Form submitted');
        
        const url = document.getElementById('url').value;
        const videoInfo = document.getElementById('videoInfo');
        const videoTitle = document.getElementById('videoTitle');
        const videoThumbnail = document.getElementById('videoThumbnail');

        console.log('Fetching video info for:', url);
        try {
            const response = await fetch('http://127.0.0.1:5000/check_video', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: `url=${encodeURIComponent(url)}`
            });

            if (!response.ok) {
                throw new Error(`HTTP error! Status: ${response.status}`);
            }

            const data = await response.json();
            console.log('Response data:', data);
            
            if (data.success) {
                videoTitle.textContent = data.title;
                videoThumbnail.src = data.thumbnail;
                videoInfo.classList.remove('hidden');
                videoInfo.style.display = 'block';
                
                if (data.is_playlist) {
                    downloadPlaylistBtn.classList.remove('hidden');
                    downloadBtn.classList.add('hidden');
                    qualitySelect.classList.add('hidden'); // Hide quality for playlists
                } else {
                    downloadBtn.classList.remove('hidden');
                    downloadPlaylistBtn.classList.add('hidden');
                    if (formatSelect.value === 'mp4') {
                        qualitySelect.classList.remove('hidden');
                    }
                }
            } else {
                alert('Error: ' + data.error);
            }
        } catch (error) {
            console.error('Fetch error:', error);
            alert('An error occurred: ' + error.message);
        }
    });

    // Direct download in the browser
    function triggerDownload(url, isPlaylist) {
        const format = formatSelect.value;
        const quality = qualitySelect.value;
        const downloadUrl = `http://127.0.0.1:5000/download?url=${encodeURIComponent(url)}&format=${format}&quality=${quality}&is_playlist=${isPlaylist}`;
        console.log('Triggering download:', downloadUrl);

        // Open the download link in a new tab
        window.open(downloadUrl, '_blank');
    }

    downloadBtn.addEventListener('click', () => {
        const url = document.getElementById('url').value;
        console.log('Downloading single video:', url);
        triggerDownload(url, false);
    });

    downloadPlaylistBtn.addEventListener('click', () => {
        const url = document.getElementById('url').value;
        console.log('Downloading playlist:', url);
        triggerDownload(url, true);
    });
});