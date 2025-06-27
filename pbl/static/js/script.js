document.addEventListener('DOMContentLoaded', () => {
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const messageDiv = document.getElementById('message');

    // ドラッグオーバー時の処理
    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropZone.classList.add('dragover');
    });

    // ドラッグが離れた時の処理
    dropZone.addEventListener('dragleave', (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropZone.classList.remove('dragover');
    });

    // ドロップ時の処理
    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropZone.classList.remove('dragover');

        const files = e.dataTransfer.files;
        if (files.length > 0) {
            handleFiles(files);
        }
    });

    // ファイル選択ボタンの処理
    fileInput.addEventListener('change', () => {
        if (fileInput.files.length > 0) {
            handleFiles(fileInput.files);
        }
    });

    // ファイル処理とアップロード
    function handleFiles(files) {
        messageDiv.innerHTML = ''; // 前回のメッセージをクリア
        Array.from(files).forEach(file => {
            if (file.type === 'text/csv' || file.name.endsWith('.csv')) {
                uploadFile(file);
            } else {
                displayMessage(`ファイル形式が不正です: ${file.name}`, 'danger');
            }
        });
    }

    function uploadFile(file) {
        const formData = new FormData();
        formData.append('file', file);

        fetch('/upload', {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                displayMessage(`${file.name}: ${data.success}`, 'success');
            } else {
                displayMessage(`${file.name}: ${data.error}`, 'danger');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            displayMessage(`${file.name}: アップロード中にエラーが発生しました。`, 'danger');
        });
    }

    function displayMessage(message, type) {
        const wrapper = document.createElement('div');
        wrapper.className = `alert alert-${type} mt-2`;
        wrapper.textContent = message;
        messageDiv.appendChild(wrapper);
    }
});
