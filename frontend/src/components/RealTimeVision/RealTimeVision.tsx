import React, { useRef, useEffect, useState, useContext } from 'react';
import * as cocoSsd from '@tensorflow-models/coco-ssd';
import '@tensorflow/tfjs';
import uuid from 'react-uuid';
import { AppStateContext } from "../../state/AppProvider";
import { log } from '../../logger'; // Import the logging utility

import {
    ChatMessage,
    ConversationRequest,
    conversationApi,
    Citation,
    ToolMessageContent,
    ChatResponse,
    getUserInfo,
    Conversation,
    historyGenerate,
    historyUpdate,
    historyClear,
    ChatHistoryLoadingState,
    CosmosDBStatus,
    ErrorMessage
} from "../../api";

const RealTimeVision: React.FC = () => {
    const videoRef = useRef<HTMLVideoElement>(null);  // Used for camera input, but hidden from the user
    const canvasRef = useRef<HTMLCanvasElement>(null); // Used to display the video feed and predictions
    const [description, setDescription] = useState<string>('');
    const [error, setError] = useState<string>('');
    const [isCameraReady, setIsCameraReady] = useState<boolean>(false);
    const abortFuncs = useRef<AbortController[]>([]);
    const appStateContext = useContext(AppStateContext);

    const isIphone = () => {
        return /iPhone|iPad|iPod/i.test(navigator.userAgent);
    };

    const checkCameraPermissions = async () => {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ video: true });
            stream.getTracks().forEach(track => track.stop()); // Stop the stream immediately after checking permissions
            return true;
        } catch (error) {
            console.error("Camera permissions check failed:", error);
            return false;
        }
    };

    const setupCamera = async () => {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            setError("Browser API navigator.mediaDevices.getUserMedia not available");
            return;
        }

        try {
            const stream = await navigator.mediaDevices.getUserMedia({
                video: {
                    facingMode: isIphone() ? 'environment' : 'user', // Use rear camera for iPhone, front camera for others
                },
            });

            if (videoRef.current) {
                videoRef.current.srcObject = stream;
                videoRef.current.onloadedmetadata = () => {
                    videoRef.current?.play();
                    setIsCameraReady(true);
                    runModel(); // Start object detection when the camera is ready
                };
            }
        } catch (error) {
            console.error("Error accessing camera:", error);
            setError("Error accessing camera. Please ensure camera permissions are granted.");
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

        // Ensure the canvas has the same dimensions as the video
        canvasRef.current.width = videoRef.current.videoWidth;
        canvasRef.current.height = videoRef.current.videoHeight;

        // Clear the canvas
        ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);

        // Draw the video frame to the canvas
        ctx.drawImage(videoRef.current, 0, 0, ctx.canvas.width, ctx.canvas.height);

        // Draw the predictions (bounding boxes and labels)
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

    const runModel = async () => {
        try {
            const model = await cocoSsd.load();
            detectFrame(model);
        } catch (error) {
            console.error("Error loading model:", error);
            setError("Error loading model.");
        }
    };

    const captureImage = async () => {
        if (!canvasRef.current || !videoRef.current) return;

        const ctx = canvasRef.current.getContext('2d');
        if (!ctx) return;

        const abortController = new AbortController();
        abortFuncs.current.unshift(abortController);

        ctx.drawImage(videoRef.current, 0, 0, canvasRef.current.width, canvasRef.current.height);
        const imageData = canvasRef.current.toDataURL('image/png');

        const userMessage = {
            id: uuid(),
            role: "user",
            content: `Describe the following image, but do not include any descriptions of people`,
            imageData: imageData, // Add the imageData as a separate field in the object
            date: new Date().toISOString(),
        };

        const systemMessage = {
            id: uuid(),
            role: "system",
            content: "You are a helpful assistant that describes images.",
            date: new Date().toISOString(),
        };


        const conversationId = appStateContext?.state?.currentChat?.id;

        let conversation: Conversation | null | undefined;
        if (!conversationId) {
            conversation = {
                id: conversationId ?? uuid(),
                title: "Image Description",
                messages: [userMessage, systemMessage],
                date: new Date().toISOString(),
            };
        } else {
            conversation = appStateContext?.state?.currentChat;
            if (!conversation) {
                console.error("Conversation not found.");
                abortFuncs.current = abortFuncs.current.filter(a => a !== abortController);
                return [];
            }
        }

        const request: ConversationRequest = {
            messages: [...conversation.messages.filter((answer) => answer.role !== error)]
        };

        //add log of request if DEBUG is enabled
        if (process.env.REACT_APP_DEBUG
            && process.env.REACT_APP_DEBUG === "true")
            {
            log("Request to conversationApi:", request);
            }

        // log messages with log(
        log("Request to conversationApi:", request);

        let result = {} as ChatResponse;
        try {
            const response = await conversationApi(request, abortController.signal);
            if (response?.body) {
                const reader = response.body.getReader();
                // log the reader
                log("Reader:", reader);
            }
        } catch (error) {
            console.error("Error generating prompt ideas:", error);
        } finally {
            abortFuncs.current = abortFuncs.current.filter(a => a !== abortController);
        }                       


        // fetch('/conversation', { // Updated URL
        //     method: 'POST',
        //     headers: {
        //         'Content-Type': 'application/json',
        //     },
        //     body: JSON.stringify({request}),
        // })
        //     .then(response => {
        //         if (!response.ok) {
        //             throw new Error('Network response was not ok');
        //         }
        //         return response.json();
        //     })
        //     .then(data => {
        //         if (data.description) {
        //             setDescription(data.description);
        //         } else {
        //             throw new Error('Description not found in response');
        //         }
        //     })
        //     .catch(error => {
        //         console.error('Error fetching description:', error);
        //         setError('Error fetching description. Please try again.');
        //     });
    };

    useEffect(() => {
        const initializeCamera = async () => {
            const hasPermissions = await checkCameraPermissions();
            if (!hasPermissions) {
                setError("Camera permissions are not granted. Please allow camera access.");
                return;
            }

            await setupCamera();
        };

        initializeCamera();
    }, []);

    return (
        <div>
            {error && <p style={{ color: 'red' }}>{error}</p>}

            {/* Hide the video element (used only as a video source for the canvas) */}
            <video ref={videoRef} style={{ display: 'none' }} />

            {/* Canvas for both video display and object detection */}
            <canvas ref={canvasRef} width="640" height="480" style={{ display: isCameraReady ? 'block' : 'none' }} />
            
            {/* Controls */}
            {isCameraReady && (
                <>
                    <button onClick={captureImage}>Capture Image</button>
                    {description && <p>{description}</p>}
                </>
            )}
        </div>
    );
};

export default RealTimeVision;