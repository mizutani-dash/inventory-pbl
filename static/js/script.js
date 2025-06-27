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
            if (data.status === 'confirm') {
                // サーバーから確認を求められた場合
                if (confirm(data.message)) {
                    forceUpload(data.filename, data.file_hash);
                } else {
                    displayMessage('アップロードはキャンセルされました。', 'info');
                }
            } else if (data.success) {
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

    // 強制アップロード処理
    function forceUpload(filename, file_hash) {
        const formData = new FormData();
        formData.append('filename', filename);
        formData.append('file_hash', file_hash);

        fetch('/confirm_upload', {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                displayMessage(`${filename}: ${data.success}`, 'success');
            } else {
                displayMessage(`${filename}: ${data.error}`, 'danger');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            displayMessage(`${filename}: 強制アップロード中にエラーが発生しました。`, 'danger');
        });
    }


    function displayMessage(message, type) {
        const wrapper = document.createElement('div');
        // メッセージタイプに応じてクラスを設定
        let alertClass = 'alert-secondary';
        if (type === 'success') alertClass = 'alert-success';
        if (type === 'danger') alertClass = 'alert-danger';
        if (type === 'info') alertClass = 'alert-info';

        wrapper.className = `alert ${alertClass} mt-2`;
        wrapper.textContent = message;
        messageDiv.appendChild(wrapper);
    }
});
