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
                        window.location.href = 'https://login.dartmouth.edu/cas/login?service=' + encodeURIComponent(window.location.href);
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