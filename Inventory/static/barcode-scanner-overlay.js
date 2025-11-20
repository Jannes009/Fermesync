class BarcodeScannerOverlay extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this.isOpen = false;
    this.isScanning = false;
    this.codeReader = null;
    this.activeStream = null;
    this.currentBarcode = null;
    this.resolveScan = null;
    this.rejectScan = null;
    this.videoElem = null;
    this.noDetectionCount = 0;
    this._escapeHandler = null;
    this._overlayClickHandler = null;
  }

  // Public method to open the scanner
  async open() {
    if (this.isOpen) return Promise.reject('Scanner already open');

    return new Promise((resolve, reject) => {
      this.resolveScan = resolve;
      this.rejectScan = reject;
      this.show();
    });
  }

  // Public method to close the scanner
  close() {
    this.hide();
    this.cleanup();
    if (this.rejectScan) {
      try { this.rejectScan('Scanner closed'); } catch (e) {}
      this.rejectScan = null;
    }
  }

  connectedCallback() {
    this.render();
    try {
      this.setupEventListeners();
    } catch (err) {
      // Defensive: log but don't completely break the page
      console.error('Error setting up barcode scanner listeners:', err);
    }
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        /* ... (keep your existing styles) ... */
        .scanner-overlay {
          position: fixed;
          top: 0;
          left: 0;
          width: 100%;
          height: 100%;
          background: rgba(0, 0, 0, 0.9);
          z-index: 10000;
          display: none;
          flex-direction: column;
          justify-content: center;
          align-items: center;
          font-family: Arial, sans-serif;
        }
        .scanner-overlay.open { display: flex; }
        .scanner-container { width: 95%; max-width: 500px; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3); }
        .scanner-header { padding: 16px; background: #007bff; color: white; display: flex; justify-content: space-between; align-items: center; }
        .scanner-header h3 { margin: 0; font-size: 18px; }
        .close-btn { background: none; border: none; color: white; font-size: 24px; cursor: pointer; padding: 0; width: 30px; height: 30px; display: flex; align-items: center; justify-content: center; }
        .scanner-preview { position: relative; width: 100%; height: 300px; background: #000; }
        video { width: 100%; height: 100%; object-fit: cover; }
        .scanner-guide { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); border: 2px dashed #00ff00; width: 60%; height: 40%; border-radius: 8px; pointer-events: none; box-shadow: 0 0 0 10000px rgba(0, 0, 0, 0.4); }
        .scanner-result { padding: 16px; background: #f8f9fa; border-top: 1px solid #dee2e6; display: none; }
        .scanner-result.show { display: block; }
        .barcode-value { font-family: monospace; font-size: 16px; background: white; padding: 12px; border: 2px solid #28a745; border-radius: 6px; margin-bottom: 12px; text-align: center; font-weight: bold; color: #155724; }
        .result-actions { display: flex; gap: 8px; }
        .btn { padding: 10px 16px; border: none; border-radius: 6px; cursor: pointer; font-size: 14px; font-weight: 500; flex: 1; transition: all 0.2s; }
        .btn-confirm { background: #28a745; color: white; }
        .btn-rescan { background: #ffc107; color: black; }
        .scanner-hint { color: white; text-align: center; margin-top: 16px; font-size: 14px; padding: 0 10px; }
        .loading-message { color: white; text-align: center; padding: 20px; display: none; }
        .loading-message.show { display: block; }
        .camera-permission { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); color: white; text-align: center; z-index: 15; background: rgba(0,0,0,0.8); padding: 20px; border-radius: 10px; display: none; }
        .camera-permission.show { display: block; }
        .permission-btn { background: #007bff; color: white; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer; margin-top: 10px; }
      </style>

      <div class="scanner-overlay" id="overlay">
        <div class="scanner-container" id="container">
          <div class="scanner-header">
            <h3>Scan Barcode</h3>
            <button id="close-btn" class="close-btn" aria-label="Close scanner">&times;</button>
          </div>

          <div class="scanner-preview">
            <video id="video" playsinline></video>
            <div class="scanner-guide"></div>
            <div class="camera-permission" id="camera-permission">
              <p>Camera permission required</p>
              <button class="permission-btn" id="request-permission">Allow Camera</button>
            </div>
          </div>

          <div class="scanner-result" id="scanner-result">
            <div class="barcode-value" id="barcode-value"></div>
            <div class="result-actions">
              <button class="btn btn-rescan" id="rescan-btn">Scan Again</button>
              <button class="btn btn-confirm" id="confirm-btn">Use This Code</button>
            </div>
          </div>
        </div>

        <div class="scanner-hint" id="scanner-hint">Align barcode within the green frame</div>
        <div class="loading-message" id="loading-message">Starting camera...</div>
      </div>
    `;
  }

  setupEventListeners() {
    try {
      console.log('BarcodeScannerOverlay: setting up event listeners');

      if (!this.shadowRoot) {
        console.warn('BarcodeScannerOverlay: shadowRoot is not available');
        return;
      }

      // Set videoElem early so other functions can rely on it
      this.videoElem = this.shadowRoot.querySelector('video');

      // get elements
      const closeBtn = this.shadowRoot.getElementById('close-btn');
      const confirmBtn = this.shadowRoot.getElementById('confirm-btn');
      const rescanBtn = this.shadowRoot.getElementById('rescan-btn');
      const requestPermissionBtn = this.shadowRoot.getElementById('request-permission');
      const overlay = this.shadowRoot.getElementById('overlay');
      const container = this.shadowRoot.getElementById('container');

      console.debug('scanner elements:', { closeBtn, confirmBtn, rescanBtn, requestPermissionBtn, overlay, container, videoElem: this.videoElem });

      if (closeBtn) {
        closeBtn.addEventListener('click', () => this.close());
      } else {
        console.warn('BarcodeScannerOverlay: closeBtn not found');
      }

      if (confirmBtn) {
        confirmBtn.addEventListener('click', () => this.confirmBarcode());
      } else {
        console.warn('BarcodeScannerOverlay: confirmBtn not found');
      }

      if (rescanBtn) {
        rescanBtn.addEventListener('click', () => this.rescan());
      } else {
        console.warn('BarcodeScannerOverlay: rescanBtn not found');
      }

      if (requestPermissionBtn) {
        requestPermissionBtn.addEventListener('click', () => this.requestCameraPermission());
      } else {
        console.warn('BarcodeScannerOverlay: requestPermissionBtn not found');
      }

      // click outside container to close (backdrop)
      this._overlayClickHandler = (e) => {
        if (!container) return;
        if (e.target === overlay) {
          this.close();
        }
      };
      if (overlay) {
        overlay.addEventListener('click', this._overlayClickHandler);
      } else {
        console.warn('BarcodeScannerOverlay: overlay element not found');
      }

      // ESC key to close
      this._escapeHandler = (e) => {
        if (e.key === 'Escape') {
          this.close();
        }
      };
      window.addEventListener('keydown', this._escapeHandler);
    } catch (err) {
      console.error('BarcodeScannerOverlay.setupEventListeners error:', err);
    }
  }

  show() {
    this.isOpen = true;
    const overlay = this.shadowRoot.querySelector('.scanner-overlay');
    if (overlay) overlay.classList.add('open');
    // Auto-start scanner when opened
    this.startScanner();
  }

  hide() {
    this.isOpen = false;
    const overlay = this.shadowRoot.querySelector('.scanner-overlay');
    if (overlay) overlay.classList.remove('open');
    this.hideResult();
    this.stopScanner();
  }

  async startScanner() {
    if (this.isScanning) return;
    if (!this.videoElem) {
      console.warn('startScanner called but video element is not ready');
      // try to set it again
      this.videoElem = this.shadowRoot.querySelector('video');
      if (!this.videoElem) return this.showError('Video element not available');
    }

    this.showLoading('Starting camera...');

    try {
      // create reader
      if (!ZXing || !ZXing.BrowserMultiFormatReader) {
        throw new Error('ZXing library missing');
      }

      this.codeReader = new ZXing.BrowserMultiFormatReader();

      const hints = new Map();
      hints.set(ZXing.DecodeHintType.POSSIBLE_FORMATS, [
        ZXing.BarcodeFormat.CODE_128,
        ZXing.BarcodeFormat.CODE_39,
        ZXing.BarcodeFormat.EAN_13,
        ZXing.BarcodeFormat.EAN_8,
        ZXing.BarcodeFormat.UPC_A,
        ZXing.BarcodeFormat.UPC_E
      ]);
      hints.set(ZXing.DecodeHintType.TRY_HARDER, false);
      try { this.codeReader.hints = hints; } catch (e) { /* ignore if library doesn't accept direct assignment */ }

      const stream = await this.getCameraStream();
      if (!stream) {
        this.hideLoading();
        this.showCameraPermissionRequest();
        return;
      }

      const track = stream.getVideoTracks()[0];
      const settings = track && track.getSettings ? track.getSettings() : {};
      const deviceId = settings && settings.deviceId ? settings.deviceId : undefined;

      // define scan region (safe fallback values)
      const scanRegion = this.getScanRegion(this.videoElem) || undefined;

      // call decodeFromVideoDevice - pass deviceId if available, otherwise undefined (library will choose)
      try {
        this.codeReader.decodeFromVideoDevice(
          deviceId,
          this.videoElem,
          (result, error) => {
            if (result) {
              try {
                this.handleBarcodeDetected(result.getText());
              } catch (e) {
                console.error('Error handling detected barcode:', e);
              }
            } else {
              this.noDetectionCount++;
            }

            if (error && !(error instanceof ZXing.NotFoundException)) {
              console.debug('Scan error:', error);
            }
          },
          scanRegion
        );
      } catch (err) {
        // Some library builds accept only (deviceId, callback) or (videoElement, callback)
        // Try a fallback: use decodeFromVideoElement (if available) or decodeFromVideoDevice with undefined deviceId
        console.warn('decodeFromVideoDevice failed, attempting fallback', err);
        if (this.codeReader && typeof this.codeReader.decodeFromVideoElement === 'function') {
          // pass the video element only
          this.codeReader.decodeFromVideoElement(this.videoElem, (result, error) => {
            if (result) this.handleBarcodeDetected(result.getText());
          });
        } else {
          // final fallback: try decodeFromVideoDevice without region
          try {
            this.codeReader.decodeFromVideoDevice(deviceId, this.videoElem, (result, error) => {
              if (result) this.handleBarcodeDetected(result.getText());
            });
          } catch (e2) {
            throw e2;
          }
        }
      }

      this.isScanning = true;
      this.hideLoading();
      this.updateScannerHint('Point camera at barcode within the green frame');
    } catch (err) {
      console.error('Scanner error:', err);
      this.hideLoading();
      this.showError('Scanner error: ' + (err.message || err));
      this.stopScanner();
    }
  }

  // Lower resolution camera
  async getCameraStream() {
    try {
      const constraints = {
        video: {
          facingMode: { ideal: "environment" },
          width: { ideal: 640 },
          height: { ideal: 480 },
          frameRate: { ideal: 15 }
        },
        audio: false
      };

      const stream = await navigator.mediaDevices.getUserMedia(constraints);
      this.activeStream = stream;
      if (this.videoElem) {
        this.videoElem.srcObject = stream;
        // wait until metadata loaded
        await new Promise((resolve) => {
          const onLoaded = () => {
            if (this.videoElem) {
              try { this.videoElem.removeEventListener('loadedmetadata', onLoaded); } catch (e) {}
            }
            resolve();
          };
          this.videoElem.addEventListener('loadedmetadata', onLoaded);
          // also set a fallback timeout so we don't hang forever
          setTimeout(resolve, 1200);
        });
        try { await this.videoElem.play(); } catch (e) { /* non-fatal */ }
      }
      return stream;
    } catch (err) {
      console.warn('Camera access failed:', err);
      return null;
    }
  }

    getScanRegion(videoElem) {
    console.log("Changed width again")
    const videoWidth = (videoElem && videoElem.videoWidth) || 640;
    const videoHeight = (videoElem && videoElem.videoHeight) || 480;
    
    // Move scan region to left side (20% from left, 30% from top)
    const regionWidth = videoWidth * 0.6;
    const regionHeight = videoHeight * 0.4;
    const regionX = videoWidth * 0.5;  // 10% from left instead of center
    const regionY = videoHeight * 0.5; // 30% from top
    
    return {
        x: Math.floor(regionX),
        y: Math.floor(regionY),
        width: Math.floor(regionWidth),
        height: Math.floor(regionHeight)
    };
    }


  stopScanner() {
    if (this.codeReader) {
      try {
        if (typeof this.codeReader.reset === 'function') this.codeReader.reset();
      } catch (e) {
        console.warn('Error stopping reader:', e);
      }
      try { this.codeReader = null; } catch(e) {}
    }
    this.cleanupStream();
    this.isScanning = false;
    this.noDetectionCount = 0;
  }

  cleanupStream() {
    try {
      if (this.activeStream) {
        this.activeStream.getTracks().forEach(track => {
          try { track.stop(); } catch (e) {}
        });
        this.activeStream = null;
      }
      if (this.videoElem) {
        try { this.videoElem.pause(); } catch (e) {}
        try { this.videoElem.srcObject = null; } catch (e) {}
      }
    } catch (e) {
      console.warn('Cleanup error:', e);
    }
  }

  handleBarcodeDetected(barcode) {
    this.currentBarcode = barcode;
    this.showResult(barcode);
    this.stopScanner(); // Stop scanning when we get a result
  }

  showResult(barcode) {
    const barcodeValue = this.shadowRoot.getElementById('barcode-value');
    const scannerResult = this.shadowRoot.getElementById('scanner-result');
    if (barcodeValue) barcodeValue.textContent = barcode;
    if (scannerResult) scannerResult.classList.add('show');
    this.updateScannerHint('Barcode detected! Confirm or scan again.');
  }

  hideResult() {
    this.currentBarcode = null;
    const scannerResult = this.shadowRoot.getElementById('scanner-result');
    if (scannerResult) scannerResult.classList.remove('show');
    this.updateScannerHint('Align barcode within the green frame');
  }

  confirmBarcode() {
    if (this.currentBarcode && this.resolveScan) {
      try { this.resolveScan(this.currentBarcode); } catch (e) {}
      this.resolveScan = null;
      this.hide();
    }
  }

  rescan() {
    this.hideResult();
    // small delay to ensure resources released
    setTimeout(() => this.startScanner(), 120);
  }

  showCameraPermissionRequest() {
    const el = this.shadowRoot.getElementById('camera-permission');
    if (el) el.classList.add('show');
  }

  hideCameraPermissionRequest() {
    const el = this.shadowRoot.getElementById('camera-permission');
    if (el) el.classList.remove('show');
  }

  async requestCameraPermission() {
    this.hideCameraPermissionRequest();
    this.showLoading('Requesting camera permission...');
    try {
      const stream = await this.getCameraStream();
      this.hideLoading();
      if (stream) {
        this.startScanner();
      } else {
        this.showCameraPermissionRequest();
      }
    } catch (err) {
      this.hideLoading();
      this.showCameraPermissionRequest();
    }
  }

  showLoading(message) {
    const loading = this.shadowRoot.getElementById('loading-message');
    if (loading) {
      loading.textContent = message;
      loading.classList.add('show');
    }
  }

  hideLoading() {
    const loading = this.shadowRoot.getElementById('loading-message');
    if (loading) loading.classList.remove('show');
  }

  updateScannerHint(message) {
    const hint = this.shadowRoot.getElementById('scanner-hint');
    if (hint) hint.textContent = message;
  }

  showError(message) {
    this.updateScannerHint(message);
    setTimeout(() => {
      this.updateScannerHint('Align barcode within the green frame');
    }, 3000);
  }

  cleanup() {
    this.stopScanner();
    this.hideResult();
    this.hideLoading();
    this.hideCameraPermissionRequest();
    this.currentBarcode = null;
    this.noDetectionCount = 0;

    // remove global listeners
    if (this._escapeHandler) {
      window.removeEventListener('keydown', this._escapeHandler);
      this._escapeHandler = null;
    }
    const overlay = this.shadowRoot.getElementById('overlay');
    if (overlay && this._overlayClickHandler) {
      overlay.removeEventListener('click', this._overlayClickHandler);
      this._overlayClickHandler = null;
    }
  }

  disconnectedCallback() {
    this.cleanup();
  }
}

customElements.define('barcode-scanner-overlay', BarcodeScannerOverlay);
