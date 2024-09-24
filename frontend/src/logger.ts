// logger.ts
export const log = (...args: any[]) => {
    if (process.env.REACT_APP_DEBUG === 'true') {
        console.log(...args);
    }
};