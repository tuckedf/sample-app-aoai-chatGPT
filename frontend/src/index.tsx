import React, { useEffect } from 'react';
import { initializeIcons } from "@fluentui/react";
import { HashRouter, Routes, Route } from 'react-router-dom';
import ReactDOM from 'react-dom';

import "./index.css";

import Layout from "./pages/layout/Layout";
import NoPage from "./pages/NoPage";
import Chat from "./pages/chat/Chat";
import { AppStateProvider } from "./state/AppProvider";

initializeIcons();

function isLoggedIn() {
   // return sessionStorage.getItem('user') !== null;
      return false;
}
/*
export default function App() {
    // Check for service ticket in the URL on component mount
    useEffect(() => {
        const urlParams = new URLSearchParams(window.location.search);
        const ticket = urlParams.get('ticket');

        if (ticket) {
            // If a service ticket is found, send it to the backend for validation
            console.log('Validating ticket: ' + ticket);
            fetch('/api/validate?ticket=' + ticket)
                .then(response => response.json())
                .then(data => {
                    // Log the response data
                    console.log('Response from /api/validate:', data);
                    // Handle validation response
                })
                .catch(error => {
                    // Log any errors
                    console.error('Error with /api/validate fetch:', error);
                });
        } else if (!isLoggedIn()) {
            // If no service ticket is found and the user is not logged in, redirect to the CAS server
            window.location.href = 'https://login.dartmouth.edu/cas/login?service=' + encodeURIComponent(window.location.href);
        }
    }, []);

    */
    export default function App() {
        useEffect(() => {
            const urlParams = new URLSearchParams(window.location.search);
            const ticket = urlParams.get('ticket');
    
            // Always call /api/validate, whether or not a ticket is present
            fetch('/api/validate' + (ticket ? '?ticket=' + ticket : ''))
                .then(response => {
                    if (response.status === 200) {
                        return response.json();
                    } else if (response.status === 401) {
                        console.log('error 401')
                       
                        throw new Error('Unauthorized');
                    } else {
                        throw new Error('Unexpected response status: ' + response.status);
                    }
                })
                .then(data => {
                    console.log('Response from /api/validate:', data);
                })
                .catch(error => {
                    console.error('Error with /api/validate fetch:', error);
                });
        }, []);


    return (
        <AppStateProvider>
            <HashRouter>
                <Routes>
                    <Route path="/" element={<Layout />}>
                        <Route index element={<Chat />} />
                        <Route path="*" element={<NoPage />} />
                    </Route>
                </Routes>
            </HashRouter>
        </AppStateProvider>
    );
}

ReactDOM.render(
    <React.StrictMode>
        <App />
    </React.StrictMode>,
    document.getElementById("root")
);


/*
import React from "react";
import ReactDOM from "react-dom/client";
import { HashRouter, Routes, Route } from "react-router-dom";
import { initializeIcons } from "@fluentui/react";

import "./index.css";

import Layout from "./pages/layout/Layout";
import NoPage from "./pages/NoPage";
import Chat from "./pages/chat/Chat";
import { AppStateProvider } from "./state/AppProvider";

initializeIcons();

export default function App() {
    return (
        <AppStateProvider>
            <HashRouter>
                <Routes>
                    <Route path="/" element={<Layout />}>
                        <Route index element={<Chat />} />
                        <Route path="*" element={<NoPage />} />
                    </Route>
                </Routes>
            </HashRouter>
        </AppStateProvider>
    );
}

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
    <React.StrictMode>
        <App />
    </React.StrictMode>
);
*/