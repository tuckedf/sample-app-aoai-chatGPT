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
    const [descriptionImage, setDescriptionImage] = useState<string>('');
    const [error, setError] = useState<string>('');
    const [isCameraReady, setIsCameraReady] = useState<boolean>(false);
    const abortFuncs = useRef<AbortController[]>([]);
    const appStateContext = useContext(AppStateContext);
    const [response, setResponse] = useState<string>('');

    const [ASSISTANT, TOOL, ERROR] = ["assistant", "tool", "error"]

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

    log("Request to conversationApi:", request);

    let buffer = ''; // Buffer to accumulate incomplete JSON data
    try {
        const response = await conversationApi(request, abortController.signal);
        let result = {} as ChatResponse;
        //log response in json format
        //setResponse(JSON.stringify(response, null, 2));
        //log("Response from conversationApi:", response);
        if (response?.body) {
            const reader = response.body.getReader();
    
            let runningText = "";
            let procText = "";

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                var text = new TextDecoder("utf-8").decode(value);
                log("Text from conversationApi:", text);
                console.log("Text from conversationApi:", text);
                const objects = text.split("\n");
                objects.forEach((obj) => {
                    try {
                        if (obj !== "" && obj !== "{}") {
                            runningText += obj;
                            result = JSON.parse(runningText);
                            if (result.choices?.length > 0) {
                                result.choices[0].messages.forEach((msg) => {
                                    msg.id = result.id;
                                    msg.date = new Date().toISOString();
                                });
                                result.choices[0].messages.forEach((resultObj) => {
                                    const context = processRealTimeDescription(resultObj, userMessage, conversationId);
                                });
                            }
                            runningText = "";
                            procText = JSON.stringify(result);
                        } else if (result.error) {
                            throw Error(result.error);
                        }
                    } catch (e) {
                        if (!(e instanceof SyntaxError)) {
                            console.error(e);
                            throw e;
                        } else {
                            log("Incomplete message. Continuing...");
                        }
                    }
                });
            }
        }
    } catch (error) {
        console.error("Error generating prompt ideas or parsing JSON:", error);
        console.error("Response received:", buffer);
    } finally {
        abortFuncs.current = abortFuncs.current.filter(a => a !== abortController);
    }
};

let assistantMessage = {} as ChatMessage
let toolMessage = {} as ChatMessage
let assistantContent = ""


const processRealTimeDescription= (resultMessage: ChatMessage, userMessage: ChatMessage, conversationId?: string) => {
    if (resultMessage.role === ASSISTANT) {

    if (resultMessage.role === ASSISTANT) {
        assistantContent += resultMessage.content
        assistantMessage = resultMessage
        assistantMessage.content = assistantContent

        if (resultMessage.context) {
            toolMessage = {
                id: uuid(),
                role: TOOL,
                content: resultMessage.context,
                date: new Date().toISOString(),
            }
        }
    }


    if (resultMessage.role === TOOL) toolMessage = resultMessage
    }
}
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
                </>
            )}

            {/* Display the response at the bottom of the screen */}
            {descriptionImage && (
                <div style={{ marginTop: '20px', padding: '10px', border: '1px solid #ccc', borderRadius: '5px', backgroundColor: '#f9f9f9' }}>
                    <h2>Image Description:</h2>
                    <p>{descriptionImage}</p>
                </div>
            )}
        </div>
    );
};

export default RealTimeVision;