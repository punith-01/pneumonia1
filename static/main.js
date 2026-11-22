// Global variables
let selectedFile = null;
let isProcessing = false;

// DOM elements
const fileUpload = document.getElementById('file-upload');
const fileDrag = document.getElementById('file-drag');
const uploadCaption = document.getElementById('upload-caption');
const imagePreview = document.getElementById('image-preview');
const imageDisplay = document.getElementById('image-display');
const predResult = document.getElementById('pred-result');
const loader = document.getElementById('loader');
const submitBtn = document.getElementById('submit-btn');
const clearBtn = document.getElementById('clear-btn');

// Initialize event listeners when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    initializeEventListeners();
    updateUI();
});

// Initialize all event listeners
function initializeEventListeners() {
    // File input change event
    fileUpload.addEventListener('change', handleFileSelect);
    
    // Drag and drop events
    fileDrag.addEventListener('dragover', handleDragOver);
    fileDrag.addEventListener('dragenter', handleDragEnter);
    fileDrag.addEventListener('dragleave', handleDragLeave);
    fileDrag.addEventListener('drop', handleDrop);
    
    // Prevent default drag behaviors on document
    document.addEventListener('dragover', preventDefault);
    document.addEventListener('drop', preventDefault);
    
    // Button events
    submitBtn.addEventListener('click', submitImage);
    clearBtn.addEventListener('click', clearImage);
}

// Prevent default drag behaviors
function preventDefault(e) {
    e.preventDefault();
    e.stopPropagation();
}

// Handle drag over event
function handleDragOver(e) {
    preventDefault(e);
    fileDrag.classList.add('dragover');
}

// Handle drag enter event
function handleDragEnter(e) {
    preventDefault(e);
    fileDrag.classList.add('dragover');
}

// Handle drag leave event
function handleDragLeave(e) {
    preventDefault(e);
    fileDrag.classList.remove('dragover');
}

// Handle drop event
function handleDrop(e) {
    preventDefault(e);
    fileDrag.classList.remove('dragover');
    
    const files = e.dataTransfer.files;
    if (files.length > 0) {
        handleFile(files[0]);
    }
}

// Handle file selection from input
function handleFileSelect(e) {
    const files = e.target.files;
    if (files.length > 0) {
        handleFile(files[0]);
    }
}

// Process selected file
function handleFile(file) {
    // Validate file type
    if (!isValidImageFile(file)) {
        showError('Please select a valid image file (PNG, JPG, JPEG, GIF)');
        return;
    }
    
    // Validate file size (max 10MB)
    if (file.size > 10 * 1024 * 1024) {
        showError('File size must be less than 10MB');
        return;
    }
    
    selectedFile = file;
    displayImagePreview(file);
    updateUI();
}

// Validate image file type
function isValidImageFile(file) {
    const validTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif'];
    return validTypes.includes(file.type);
}

// Display image preview
function displayImagePreview(file) {
    const reader = new FileReader();
    
    reader.onload = function(e) {
        imagePreview.src = e.target.result;
        imagePreview.classList.remove('hidden');
        uploadCaption.style.opacity = '0';
    };
    
    reader.onerror = function() {
        showError('Error reading file');
    };
    
    reader.readAsDataURL(file);
}

// Submit image for prediction
function submitImage() {
    if (!selectedFile) {
        showError('Please select an image first');
        return;
    }
    
    if (isProcessing) {
        return;
    }
    
    isProcessing = true;
    updateUI();
    showLoader();
    clearPredictionResult();
    
    // Convert image to base64
    const reader = new FileReader();
    
    reader.onload = function(e) {
        const base64Data = e.target.result.split(',')[1]; // Remove data:image/jpeg;base64, prefix
        sendPredictionRequest(base64Data);
    };
    
    reader.onerror = function() {
        showError('Error processing image');
        isProcessing = false;
        updateUI();
        hideLoader();
    };
    
    reader.readAsDataURL(selectedFile);
}

// Send prediction request to server
function sendPredictionRequest(base64Data) {
    fetch('/predict', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ image: base64Data })
    })
    .then(response => {
        if (!response.ok) {
            // Try to get error message from response
            return response.json().then(data => {
                throw new Error(data.error || `HTTP error! status: ${response.status}`);
            }).catch(() => {
                throw new Error(`HTTP error! status: ${response.status}`);
            });
        }
        return response.json();
    })
    .then(data => {
        if (data.error) {
            showError(data.error);
            return;
        }

        displayPredictionResult(data);
        displayResultImage();
    })
    .catch(error => {
        console.error('Error:', error);
        showError(error.message || 'Error processing image. Please try again.');
    })
    .finally(() => {
        isProcessing = false;
        updateUI();
        hideLoader();
    });
}

// Display prediction result
function displayPredictionResult(resultData) {
    if (!resultData) {
        showError('No prediction data received.');
        return;
    }

    const { diagnosis, label, confidence_percent, mode } = resultData;

    predResult.textContent = diagnosis || 'Prediction unavailable.';
    predResult.classList.remove('hidden', 'normal', 'pneumonia', 'demo');

    // Add appropriate class based on result
    if (label && label.toLowerCase() === 'normal') {
        predResult.classList.add('normal');
    } else if (label && label.toLowerCase() === 'pneumonia') {
        predResult.classList.add('pneumonia');
    } else {
        predResult.classList.add('demo');
    }

    if (mode === 'demo') {
        predResult.textContent += ' (Demo mode)';
    }
    if (typeof confidence_percent === 'number') {
        predResult.setAttribute('data-confidence', `${confidence_percent}%`);
    }
    
    // Animate result appearance
    setTimeout(() => {
        predResult.style.animation = 'fadeIn 0.5s ease-in';
    }, 100);
}

// Display result image
function displayResultImage() {
    if (selectedFile) {
        const reader = new FileReader();
        reader.onload = function(e) {
            imageDisplay.src = e.target.result;
            imageDisplay.style.display = 'block';
        };
        reader.readAsDataURL(selectedFile);
    }
}

// Clear image and reset form
function clearImage() {
    selectedFile = null;
    fileUpload.value = '';
    
    // Reset preview
    imagePreview.classList.add('hidden');
    imagePreview.src = '';
    uploadCaption.style.opacity = '1';
    
    // Reset results
    imageDisplay.style.display = 'none';
    imageDisplay.src = '';
    clearPredictionResult();
    
    // Reset drag area
    fileDrag.classList.remove('dragover');
    
    updateUI();
}

// Clear prediction result
function clearPredictionResult() {
    predResult.classList.add('hidden');
    predResult.classList.remove('normal', 'pneumonia', 'demo');
    predResult.textContent = '';
    predResult.style.animation = '';
}

// Show loading spinner
function showLoader() {
    loader.classList.remove('hidden');
}

// Hide loading spinner
function hideLoader() {
    loader.classList.add('hidden');
}

// Show error message
function showError(message) {
    // Create or update error display
    let errorDiv = document.getElementById('error-message');
    
    if (!errorDiv) {
        errorDiv = document.createElement('div');
        errorDiv.id = 'error-message';
        errorDiv.style.cssText = `
            background: linear-gradient(135deg, #f44336, #d32f2f);
            color: white;
            padding: 1rem 2rem;
            border-radius: 15px;
            margin: 1rem 0;
            text-align: center;
            font-weight: 600;
            box-shadow: 0 4px 15px rgba(244, 67, 54, 0.4);
            animation: fadeIn 0.3s ease-in;
        `;
        
        // Insert after the panel
        const panel = document.querySelector('.panel');
        panel.parentNode.insertBefore(errorDiv, panel.nextSibling);
    }
    
    errorDiv.textContent = message;
    errorDiv.style.display = 'block';
    
    // Auto-hide after 5 seconds
    setTimeout(() => {
        if (errorDiv) {
            errorDiv.style.animation = 'fadeOut 0.3s ease-out';
            setTimeout(() => {
                if (errorDiv && errorDiv.parentNode) {
                    errorDiv.parentNode.removeChild(errorDiv);
                }
            }, 300);
        }
    }, 5000);
}

// Update UI state based on current conditions
function updateUI() {
    // Update submit button state
    if (submitBtn) {
        submitBtn.disabled = !selectedFile || isProcessing;
        submitBtn.style.opacity = submitBtn.disabled ? '0.6' : '1';
        submitBtn.style.cursor = submitBtn.disabled ? 'not-allowed' : 'pointer';
        
        if (isProcessing) {
            submitBtn.value = 'Processing...';
        } else {
            submitBtn.value = 'Submit';
        }
    }
    
    // Update clear button state
    if (clearBtn) {
        clearBtn.disabled = isProcessing;
        clearBtn.style.opacity = clearBtn.disabled ? '0.6' : '1';
        clearBtn.style.cursor = clearBtn.disabled ? 'not-allowed' : 'pointer';
    }
    
    // Update upload area state
    if (fileDrag) {
        fileDrag.style.pointerEvents = isProcessing ? 'none' : 'auto';
        fileDrag.style.opacity = isProcessing ? '0.6' : '1';
    }
}


// Add keyboard accessibility
document.addEventListener('keydown', function(e) {
    // Enter key on upload area
    if (e.key === 'Enter' && e.target === fileDrag) {
        fileUpload.click();
    }
    
    // Escape key to clear
    if (e.key === 'Escape' && !isProcessing) {
        clearImage();
    }
    
    // Space or Enter to submit
    if ((e.key === ' ' || e.key === 'Enter') && e.target === submitBtn && !submitBtn.disabled) {
        e.preventDefault();
        submitImage();
    }
});

// Add touch support for mobile devices
let touchStartY = 0;
let touchEndY = 0;

fileDrag.addEventListener('touchstart', function(e) {
    touchStartY = e.changedTouches[0].screenY;
});

fileDrag.addEventListener('touchend', function(e) {
    touchEndY = e.changedTouches[0].screenY;
    // Simple swipe up gesture to trigger file selection
    if (touchStartY - touchEndY > 50) {
        fileUpload.click();
    }
});

// Performance optimization: Debounce resize events
let resizeTimeout;
window.addEventListener('resize', function() {
    clearTimeout(resizeTimeout);
    resizeTimeout = setTimeout(function() {
        // Adjust UI for new screen size if needed
        updateUI();
    }, 250);
});

console.log('Pneumonia Detection App - Frontend Loaded Successfully!');
