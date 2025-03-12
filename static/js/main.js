document.addEventListener('DOMContentLoaded', () => {
    const videoForm = document.getElementById('videoForm');
    const downloadBtn = document.getElementById('downloadBtn');
    const downloadPlaylistBtn = document.getElementById('downloadPlaylistBtn');
    const cancelBtn = document.getElementById('cancelBtn');
    const formatSelect = document.getElementById('formatSelect');
    const qualitySelect = document.getElementById('qualitySelect');
    const progressBar = document.getElementById('downloadProgress');
    const progressText = document.getElementById('progressText');
    const progressContainer = document.querySelector('.progress-container');
    const loadingSpinner = document.getElementById('loadingSpinner');
    const darkModeToggle = document.getElementById('darkModeToggle');
    const downloadStatus = document.getElementById('downloadStatus');
    const mobileNotification = document.getElementById('mobileNotification');
    const queueList = document.getElementById('queueList');
    const downloadQueue = document.getElementById('downloadQueue');
    let downloadInProgress = false;
    let videoTitles = [];

    // Mobile Detection and Notification
    const isMobile = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent);
    if (isMobile) {
        mobileNotification.classList.remove('hidden');
        setTimeout(() => mobileNotification.classList.add('hidden'), 5000);
    }

    // Dark Mode Toggle
    darkModeToggle.addEventListener('click', () => {
        document.body.classList.toggle('dark-mode');
        darkModeToggle.textContent = document.body.classList.contains('dark-mode') ? '☀️' : '🌙';
    });

    // Format selection
    formatSelect.addEventListener('change', () => {
        qualitySelect.classList.toggle('hidden', formatSelect.value !== 'mp4');
    });

    // Form submission
    videoForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        if (downloadInProgress) return;

        const url = document.getElementById('url').value;
        const videoInfo = document.getElementById('videoInfo');
        const videoTitle = document.getElementById('videoTitle');
        const videoThumbnail = document.getElementById('videoThumbnail');

        loadingSpinner.classList.remove('hidden');
        try {
            const response = await fetch('http://localhost:5000/check_video', {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: `url=${encodeURIComponent(url)}`
            });

            if (!response.ok) throw new Error(`HTTP error! Status: ${response.status}`);
            const data = await response.json();

            if (data.success) {
                videoTitle.textContent = data.title;
                videoThumbnail.src = data.thumbnail;
                videoThumbnail.alt = `Thumbnail for ${data.title}`;
                videoInfo.classList.remove('hidden');
                videoInfo.style.display = 'block';

                downloadBtn.classList.toggle('hidden', data.is_playlist);
                downloadPlaylistBtn.classList.toggle('hidden', !data.is_playlist);
                qualitySelect.classList.toggle('hidden', formatSelect.value !== 'mp4');
                cancelBtn.classList.add('hidden');
                progressContainer.classList.add('hidden');
                downloadQueue.classList.add('hidden');
                queueList.innerHTML = '';

                videoTitles = data.is_playlist ? await fetchPlaylistTitles(url) : [data.title];
            } else {
                alert(`Error: ${data.error}`);
            }
        } catch (error) {
            alert(`An error occurred: ${error.message}. Please ensure the server is running at http://localhost:5000.`);
        } finally {
            loadingSpinner.classList.add('hidden');
        }
    });

    // Fetch playlist titles
    async function fetchPlaylistTitles(url) {
        try {
            const response = await fetch('http://localhost:5000/get_playlist_titles', {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: `url=${encodeURIComponent(url)}`
            });
            const data = await response.json();
            return data.success ? data.titles : [];
        } catch (error) {
            console.error('Error fetching playlist titles:', error);
            return [];
        }
    }

    // Update queue display
    function updateQueue(currentIndex = -1) {
        queueList.innerHTML = '';
        videoTitles.forEach((title, index) => {
            const li = document.createElement('li');
            li.textContent = title;
            if (index === currentIndex) li.classList.add('downloading');
            else if (index < currentIndex) li.classList.add('completed');
            queueList.appendChild(li);
        });
        downloadQueue.classList.remove('hidden');
    }

    // Progress update (simplified for mobile)
    function updateProgress(progress) {
        progressBar.value = progress;
        progressText.textContent = `${Math.round(progress)}%`;
        progressContainer.classList.toggle('hidden', progress === 0 || progress === 100);
    }

    // Notify user
    function notifyUser(message, type = 'info') {
        downloadStatus.textContent = message;
        downloadStatus.classList.remove('hidden');
        downloadStatus.style.color = type === 'success' ? '#28a745' : type === 'error' ? '#e74c3c' : '#007BFF';
        if (type !== 'info') setTimeout(() => downloadStatus.classList.add('hidden'), 3000);
    }

    // Download function
    function triggerDownload(url, isPlaylist) {
        if (downloadInProgress) return;
        downloadInProgress = true;

        const format = formatSelect.value;
        const quality = qualitySelect.value;
        const downloadUrl = `http://localhost:5000/download?url=${encodeURIComponent(url)}&format=${format}&quality=${quality}&is_playlist=${isPlaylist}`;

        updateProgress(0);
        cancelBtn.classList.remove('hidden');
        downloadStatus.classList.add('hidden');
        updateQueue(isPlaylist ? 0 : -1);
        notifyUser('Preparing download...');

        // Use window.open for local compatibility
        const downloadWindow = window.open(downloadUrl, '_blank');
        if (!downloadWindow) {
            alert('Please allow pop-ups to start the download.');
            downloadInProgress = false;
            cancelBtn.classList.add('hidden');
            return;
        }

        // Simulate progress
        let progress = 0;
        const progressInterval = setInterval(() => {
            progress += 10;
            updateProgress(progress);
            if (progress >= 100) {
                clearInterval(progressInterval);
                downloadInProgress = false;
                cancelBtn.classList.add('hidden');
                updateQueue(isPlaylist ? videoTitles.length : -1);
                notifyUser('Download started successfully!', 'success');
            }
        }, 500);
    }

    downloadBtn.addEventListener('click', () => triggerDownload(document.getElementById('url').value, false));
    downloadPlaylistBtn.addEventListener('click', () => triggerDownload(document.getElementById('url').value, true));
    cancelBtn.addEventListener('click', () => {
        downloadInProgress = false;
        updateProgress(0);
        cancelBtn.classList.add('hidden');
        updateQueue(-1);
        notifyUser('Download preparation cancelled.', 'error');
    });
});