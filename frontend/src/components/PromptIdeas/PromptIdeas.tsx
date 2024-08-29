import React, { useEffect, useState, useRef, useContext } from 'react';
import chatComponent from '../../pages/chat/Chat';
//import { generatePromptIdeas } from '../../pages/chat/Chat';
import uuid from 'react-uuid';

import './PromptIdeas.css'
import CustomButton from './customButton';
import styles from './PromptSuggestions.module.css';
import { AppStateContext } from "../../state/AppProvider";

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

// Adjust the path as necessary

interface Idea {
    text: string;
    imageUrl: string;
}

interface PromptIdea {
    title: string;
    ideas: Idea[];
}

interface PromptIdeasProps {
    onIdeaClick: (idea: string) => void;
    conversationId: string | undefined;  // Add conversationId prop
}


const PromptIdeas: React.FC<PromptIdeasProps> = ({ onIdeaClick, conversationId }) => {
    const [promptIdeas, setPromptIdeas] = useState<PromptIdea[]>([]);
    const [error, setError] = useState<string | null>(null);
    const abortFuncs = useRef([] as AbortController[]);
    const appStateContext = useContext(AppStateContext); // Use the correct casing for the variable
    const [isPaused, setIsPaused] = useState(false);
    const intervalRef = useRef<number | null>(null);
    const [loading, setLoading] = useState(true); // State to track loading

    // State for current slide index and items per page
    const [currentIndex, setCurrentIndex] = useState(0);
    let itemsPerPage = 3;


    const [ASSISTANT, TOOL, ERROR] = ["assistant", "tool", "error"]

    useEffect(() => {
        console.log('useEffect called'); // Debugging line
    
        const fetchPromptIdeas = async () => {
            setLoading(true);  // Start loading
          try {
            console.log('Fetching prompt ideas'); // Debugging line
            const response = await generatePromptIdeas(); // Call the imported function
            console.log('API Response:', response); // Debugging line
            if (response && response) {
              setPromptIdeas(response);
            } else {
              setError('Invalid data format received from API');
            }
          } catch (error) {
            console.error('Error fetching prompt ideas:', error);
          } finally {
            setLoading(false);  // End loading
          }
        };
    
        fetchPromptIdeas();
      }, []);

    const handleIdeaClick = (idea: string) => {
        // Logic to send the idea to the chat
        console.log('Idea clicked:', idea);
        // Example: You can use a function to send the idea to the chat
        sendToChat(idea);
    };

    useEffect(() => {
        if (!isPaused && !loading) {
            intervalRef.current = window.setInterval(handleNext, 15000); // Change slide every 15 seconds
        } else if (intervalRef.current) {
            clearInterval(intervalRef.current);
        }

        return () => {
            if (intervalRef.current) {
                clearInterval(intervalRef.current);
            }
        };
    }, [currentIndex, isPaused, loading]);

    const togglePause = () => {
        setIsPaused(prev => !prev);
    };


    const generatePromptIdeas = async (conversationId?: string) => {
        console.log("generatePromptIdeas called with conversationId:", conversationId); // Debugging line
    
        const abortController = new AbortController();
        abortFuncs.current.unshift(abortController);
    
        // Fetch the prompt suggestions from the backend
        let question = "generate 3 prompt ideas based on the courses of your documents?";
        try {
            const response = await fetch('/api/prompt-suggestions');
            const data = await response.json();
            question = data.prompt_suggestions || question;
            itemsPerPage = data.prompt_suggestions_show_num || 1;
            console.log("Prompt suggestions fetched and num:", question, itemsPerPage); // Debugging line
        } catch (error) {
            console.error("Error fetching prompt suggestions:", error);
        }

        const userMessage: ChatMessage = {
            id: uuid(),
            role: "user",
            content: question,
            date: new Date().toISOString(),
        };
    
        let conversation: Conversation | null | undefined;
        if (!conversationId) {
            conversation = {
                id: conversationId ?? uuid(),
                title: question,
                messages: [userMessage],
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
    
        let result = {} as ChatResponse;
        let PROMPT_IDEAS: PromptIdea[] = [];
        try {
            const response = await conversationApi(request, abortController.signal);
            if (response?.body) {
                const reader = response.body.getReader();
    
                let runningText = "";
                let procText = "";
    
                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
    
                    var text = new TextDecoder("utf-8").decode(value);
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
                                        const context = processPromptIdeas(resultObj, userMessage, conversationId);
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
                                console.log("Incomplete message. Continuing...");
                            }
                        }
                    });
                }
    
                try {
                    if (!procText.trim().endsWith("}")) {
                        throw new Error("The JSON string is incomplete or malformed.");
                    }
    
                    const promptIdeasResponse = JSON.parse(procText);
    
                    if (!promptIdeasResponse.choices || !promptIdeasResponse.choices[0].messages || !promptIdeasResponse.choices[0].messages[0].content) {
                        throw new Error("The parsed JSON structure is not as expected.");
                    }
            
                    const questionString = question; // Replace with your actual question string

                    // Extract the maximum number from the question string
                    const numbers = questionString.match(/\d+/g);
                    const maxNumber = numbers ? Math.max(...numbers.map(Number)) : 0;

                    // Create a dynamic filter condition
                    const startsWithConditions = Array.from({ length: maxNumber }, (_, i) => `${i + 1}.`);

                    const ideas = promptIdeasResponse.choices[0].messages[0].content
                        .split("\n")
                        .filter((line: string) => startsWithConditions.some(condition => line.startsWith(condition)))
                        .map((idea: string) => ({
                            text: idea.substring(3).trim().replace(/\[doc\d+\]/g, ''), // Remove [doc1], [doc2], etc.
                            imageUrl: "/assets/mba-operations.jpeg", // Assuming a static image URL for all ideas
                        }));

                    PROMPT_IDEAS = [
                        {
                            title: "Course Content",
                            ideas: ideas
                        }
                    ];
    
                    console.log("PROMPT_IDEAS: ", PROMPT_IDEAS); // Debugging line
                } catch (error) {
                    console.error("Error generating prompt ideas:", error);
                }
    
            }
        } catch (error) {
            console.error("Error generating prompt ideas:", error);
        } finally {
            abortFuncs.current = abortFuncs.current.filter(a => a !== abortController);
        }
    
        return PROMPT_IDEAS;
    };

    // Example usage of itemsPerPage
    console.log("Items per page:", itemsPerPage);

    let assistantMessage = {} as ChatMessage
    let toolMessage = {} as ChatMessage
    let assistantContent = ""
    
    const processPromptIdeas= (resultMessage: ChatMessage, userMessage: ChatMessage, conversationId?: string) => {
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

    const sendToChat = (message: string) => {
        // Implement the logic to send the message to the chat
        console.log('Sending to chat:', message);
        // Example: You might have a function in your chat component to handle this
        // chatComponent.sendMessage(message);
    };

    const handleNext = () => {
        setCurrentIndex((prevIndex) =>
            prevIndex === Math.ceil(promptIdeas.flatMap(category => category.ideas).length / itemsPerPage) - 1
                ? 0
                : prevIndex + 1
        );
    };
    

    const handlePrev = () => {
        setCurrentIndex((prevIndex) =>
            prevIndex === 0
                ? Math.ceil(promptIdeas.flatMap(category => category.ideas).length / itemsPerPage) - 1
                : prevIndex - 1
        );
    };

    const startIndex = currentIndex * itemsPerPage;
    const endIndex = startIndex + itemsPerPage;
    const currentIdeas = promptIdeas.flatMap(category => category.ideas).slice(startIndex, endIndex);

    return (
        <div className="prompt-ideas-container">
            {loading ? (
                <div className="progress-bar-container">
                    <div className="progress-bar"></div>
                </div>
            ) : (
                <>
                    <div className="slideshow-container">
                        <button className="prev" onClick={handlePrev}>&#10094;</button>
                        <button className="next" onClick={handleNext}>&#10095;</button>
                        {currentIdeas.map((idea, idx) => (
                            <div className="slide active" key={idx}>
                                <CustomButton
                                    onIdeaClick={onIdeaClick}
                                    conversationId={conversationId}
                                >
                                    {idea.text}
                                </CustomButton>
                            </div>
                        ))}
                    </div>
                    <div className="controls-container">
                        <div className="dots-container">
                            {promptIdeas.flatMap(category => category.ideas).map((_, idx) => (
                                <span
                                    key={idx}
                                    className={`dot ${currentIndex === Math.floor(idx / itemsPerPage) ? "active-dot" : ""}`}
                                    onClick={() => setCurrentIndex(Math.floor(idx / itemsPerPage))}
                                />
                            ))}
                        </div>
                        <button className="pause-button" onClick={togglePause}>
                        {isPaused ? '▶' : '⏸'}
                        </button>
                    </div>
                </>
            )}
        </div>
    );
}

export default PromptIdeas;