// Main JavaScript for Excel to DB application

document.addEventListener('DOMContentLoaded', function() {
    // Auto-hide flash messages after 5 seconds
    const flashMessages = document.querySelector('.alert');
    if (flashMessages) {
        setTimeout(function() {
            flashMessages.style.opacity = '0';
            setTimeout(function() {
                flashMessages.style.display = 'none';
            }, 500);
        }, 5000);
    }
    
    // File input validation
    const fileInput = document.getElementById('file');
    if (fileInput) {
        fileInput.addEventListener('change', function() {
            const fileName = this.value.split('\\').pop();
            const fileExt = fileName.split('.').pop().toLowerCase();
            
            if (!['xlsx', 'xls', 'csv'].includes(fileExt)) {
                alert('请选择有效的Excel文件 (.xlsx, .xls) 或 CSV 文件 (.csv)');
                this.value = '';
            }
        });
    }
    
    // Table name validation
    const tableNameInput = document.getElementById('table_name');
    if (tableNameInput) {
        tableNameInput.addEventListener('input', function() {
            // Replace spaces and special characters with underscores
            this.value = this.value.replace(/[^a-zA-Z0-9_]/g, '_');
        });
    }
    
    // Add loading indicator for form submissions
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        form.addEventListener('submit', function() {
            // Don't show loading for delete operations
            if (!this.action.includes('delete_table')) {
                const submitBtn = this.querySelector('button[type="submit"]');
                if (submitBtn) {
                    const originalText = submitBtn.innerHTML;
                    submitBtn.disabled = true;
                    submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> 处理中...';
                    
                    // Reset button after 30 seconds in case of error
                    setTimeout(function() {
                        submitBtn.disabled = false;
                        submitBtn.innerHTML = originalText;
                    }, 30000);
                }
            }
        });
    });
    
    // Add tooltip for table names in the list
    const tableLinks = document.querySelectorAll('td:first-child');
    tableLinks.forEach(link => {
        link.title = '点击查看表数据';
        link.style.cursor = 'pointer';
        link.addEventListener('click', function() {
            const viewLink = this.nextElementSibling.querySelector('.btn-info');
            if (viewLink) {
                window.location.href = viewLink.href;
            }
        });
    });
});
