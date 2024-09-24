import React, { useRef, useEffect } from 'react';

const CameraModule: React.FC = () => {
    const videoRef = useRef<HTMLVideoElement>(null);

    useEffect(() => {
        const setupCamera = async () => {
            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                console.error("Browser API navigator.mediaDevices.getUserMedia not available");
                return;
            }

            try {
                const stream = await navigator.mediaDevices.getUserMedia({
                    video: {
                        facingMode: 'environment', // Use the rear camera
                    },
                });

                if (videoRef.current) {
                    videoRef.current.srcObject = stream;
                    videoRef.current.onloadedmetadata = () => {
                        videoRef.current?.play();
                    };
                }
            } catch (error) {
                console.error("Error accessing camera:", error);
            }
        };

        setupCamera();
    }, []);

    return (
        <div>
            <video ref={videoRef} style={{ width: '100%', height: 'auto' }} autoPlay playsInline></video>
        </div>
    );
};

export default CameraModule;