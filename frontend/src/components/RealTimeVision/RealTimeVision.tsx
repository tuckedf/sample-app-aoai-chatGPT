import React, { useRef, useEffect } from 'react';
import * as cocoSsd from '@tensorflow-models/coco-ssd';
import '@tensorflow/tfjs';

const RealTimeVision: React.FC = () => {
    const videoRef = useRef<HTMLVideoElement>(null);
    const canvasRef = useRef<HTMLCanvasElement>(null);

    useEffect(() => {
        const setupCamera = async () => {
            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                console.error("Browser API navigator.mediaDevices.getUserMedia not available");
                return;
            }

            const stream = await navigator.mediaDevices.getUserMedia({
                video: true,
            });

            if (videoRef.current) {
                videoRef.current.srcObject = stream;
                videoRef.current.onloadedmetadata = () => {
                    videoRef.current?.play();
                };
            }
        };

        const detectFrame = async (model: cocoSsd.ObjectDetection) => {
            if (!videoRef.current || !canvasRef.current) return;

            const predictions = await model.detect(videoRef.current);
            renderPredictions(predictions);

            requestAnimationFrame(() => detectFrame(model));
        };

        const renderPredictions = (predictions: cocoSsd.DetectedObject[]) => {
            if (!canvasRef.current || !videoRef.current) return;

            const ctx = canvasRef.current.getContext('2d');
            if (!ctx) return;

            ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);

            ctx.drawImage(videoRef.current, 0, 0, ctx.canvas.width, ctx.canvas.height);

            predictions.forEach(prediction => {
                ctx.beginPath();
                ctx.rect(...prediction.bbox);
                ctx.lineWidth = 2;
                ctx.strokeStyle = 'red';
                ctx.fillStyle = 'red';
                ctx.stroke();
                ctx.fillText(
                    `${prediction.class} (${Math.round(prediction.score * 100)}%)`,
                    prediction.bbox[0],
                    prediction.bbox[1] > 10 ? prediction.bbox[1] - 5 : 10
                );
            });
        };

        const run = async () => {
            await setupCamera();

            const model = await cocoSsd.load();
            detectFrame(model);
        };

        run();
    }, []);

    return (
        <div>
            <video ref={videoRef} style={{ display: 'none' }} />
            <canvas ref={canvasRef} width="640" height="480" />
        </div>
    );
};

export default RealTimeVision;